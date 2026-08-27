import json
import re
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker ist nicht verfuegbar"
)

# Eindeutig statt fest, damit parallele/vorherige Laeufe sich nicht in die
# Quere kommen; die Fixture raeumt das Image am Ende wieder auf.
IMAGE = f"flashcards-container-test-{uuid.uuid4().hex[:8]}"

# Jeder docker-Aufruf bekommt eine Obergrenze: Ein haengender Aufruf ohne
# timeout wuerde die gesamte Suite unbegrenzt blockieren, statt rot zu
# werden. Der Build darf laenger brauchen als der Rest.
ZEITGRENZE = 120
ZEITGRENZE_BUILD = 900


def _laufen(
    *befehl: str, pruefen: bool = True, zeitgrenze: int = ZEITGRENZE
) -> subprocess.CompletedProcess:
    return subprocess.run(
        befehl, capture_output=True, text=True, check=pruefen, timeout=zeitgrenze
    )


def _freier_port() -> int:
    # Einen festen Port zu belegen laesst den Test scheitern, sobald auf der
    # Maschine schon irgendetwas darauf lauscht (oder ein zweiter Lauf
    # parallel laeuft). Das Betriebssystem einen freien nennen lassen.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as buchse:
        buchse.bind(("127.0.0.1", 0))
        return buchse.getsockname()[1]


def _im_volume(volume, image: str, befehl: str) -> subprocess.CompletedProcess:
    # Ein Wegwerf-Container schaut ins Volume, statt der Testprozess direkt.
    # /data/pgdata gehoert der containerinternen postgres-UID; auf einem
    # Linux-Host koennte der Testprozess dort weder lesen noch schreiben.
    return _laufen(
        "docker", "run", "--rm", "-v", f"{volume}:/data",
        "--entrypoint", "sh", image, "-c", befehl,
        pruefen=False,
    )


# Ob der Fehler "lock file postmaster.pid already exists" auftritt, hing bisher
# vom Zufall ab: PostgreSQL entfernt eine liegen gebliebene Sperrdatei selbst,
# wenn die dort vermerkte Prozessnummer im neuen Container gerade NICHT belegt
# ist - und meldet nur dann FATAL, wenn sie belegt ist. Der Test schwieg also
# ausgerechnet dann, wenn es darauf ankam.
#
# Hier wird diese Bedingung deshalb gezielt hergestellt, statt auf sie zu
# hoffen. Der Vorspann laeuft im zweiten Container VOR dem Einstiegspunkt und
# ersetzt in der echt liegen gebliebenen Sperrdatei nur die erste Zeile - die
# Prozessnummer - durch eine, die in diesem Container garantiert belegt ist:
#
#   * setpriv fuehrt sleep unter der Kennung postgres aus und ersetzt sich
#     dabei selbst, $! ist also die Nummer des schlafenden Prozesses.
#   * Die Kennung postgres ist noetig, nicht bloss irgendein lebender Prozess:
#     PostgreSQL prueft mit kill(pid, 0). Gehoert der Prozess einem anderen
#     Benutzer (etwa PID 1 als root), antwortet der Kern mit EPERM, und
#     PostgreSQL wertet das ausdruecklich als "kann kein zweiter Server sein"
#     und raeumt die Datei selbst weg. Nachgemessen: Mit PID 1 kommt der
#     Container hoch, mit einer postgres-eigenen Nummer nicht.
#
# Alles Uebrige - Datei, Inhalt, Zeitpunkt - bleibt echt: Sie stammt aus dem
# harten Stopp des ersten Containers.
SABOTAGE = """set -eu
setpriv --reuid=postgres --regid=postgres --clear-groups sleep 3600 &
belegte_pid=$!
{ echo "$belegte_pid"; tail -n +2 /data/pgdata/postmaster.pid; } > /tmp/sperrdatei
cat /tmp/sperrdatei > /data/pgdata/postmaster.pid
echo "TEST-VORSPANN: Sperrdatei zeigt jetzt auf die belegte PID $belegte_pid"
exec /app/docker/entrypoint.sh
"""


@pytest.fixture(scope="module")
def image():
    _laufen("docker", "build", "-t", IMAGE, ".", zeitgrenze=ZEITGRENZE_BUILD)
    yield IMAGE
    _laufen("docker", "rmi", "-f", IMAGE, pruefen=False)


def test_ohne_volume_bricht_der_container_mit_klartext_ab(image):
    ergebnis = _laufen("docker", "run", "--rm", image, pruefen=False)
    assert ergebnis.returncode != 0
    ausgabe = ergebnis.stdout + ergebnis.stderr
    # Nicht nur "/data" pruefen - das waere auch bei einem ganz anderen
    # Fehler gruen, der zufaellig "/data" erwaehnt. Ein aussagekraeftiger
    # Teil der tatsaechlichen Abbruchmeldung aus entrypoint.sh.
    assert "kein gemountetes Volume" in ausgabe


def _healthz_von_aussen(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/healthz", timeout=3
        ) as antwort:
            return json.loads(antwort.read().decode())
    except (urllib.error.URLError, OSError):
        return None


def _warten_bis_gesund(port: int, name: str) -> dict:
    # Pruefung von aussen ueber die veroeffentlichte Portweiterleitung -
    # genau das ist "die Seite ist erreichbar", nicht ein docker exec, der
    # innerhalb des Containers auf localhost zugreift.
    for _ in range(60):
        gesundheit = _healthz_von_aussen(port)
        if gesundheit is not None and gesundheit.get("datenbank") == "ok":
            return gesundheit
        time.sleep(2)
    logs = _laufen("docker", "logs", name, pruefen=False)
    pytest.fail(f"Container wurde nicht gesund. Logs:\n{logs.stdout}\n{logs.stderr}")


def test_mit_volume_wird_die_seite_erreichbar_und_daten_ueberleben(image, tmp_path):
    volume = tmp_path / "daten"
    volume.mkdir()
    port = _freier_port()

    def starten(name: str, *zusatzbefehl: str) -> None:
        _laufen(
            "docker", "run", "-d", "--name", name,
            "-v", f"{volume}:/data",
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "DATABASE_URL=postgresql+psycopg://flashcards:test@localhost:5432/flashcards",
            "-e", "APP_SECRET=test",
            "-e", "TEACHER_PASSWORD=test",
            "-e", "BASE_URL=http://localhost:8000",
            "-p", f"{port}:8000",
            image,
            *zusatzbefehl,
        )

    def aufraeumen() -> None:
        # Der Container legt /data/pgdata unter der internen postgres-UID
        # an; ohne das raeumt pytests tmp_path-Fixture auf einem Linux-Host
        # mit PermissionError nicht auf, weil der Testprozess eine andere
        # UID hat. Ein Wegwerf-Container als root (Default-User des Images)
        # loescht sie sauber weg.
        _laufen(
            "docker", "run", "--rm", "-v", f"{volume}:/data",
            "--entrypoint", "rm", image, "-rf", "/data/pgdata",
            pruefen=False,
        )

    name_1 = f"flashcards-{uuid.uuid4().hex[:8]}"
    try:
        starten(name_1)
        gesundheit = _warten_bis_gesund(port, name_1)
        assert gesundheit["status"] == "ok"
        assert gesundheit["datenbank"] == "ok"

        _laufen(
            "docker", "exec", name_1, "psql", "-U", "flashcards", "-d", "flashcards",
            "-c", "INSERT INTO bundles (id, slug, titel) "
                  "VALUES (gen_random_uuid(), 'rote-katze-springt', 'Test')",
        )

        # Das Risiko aus der Spezifikation ist nicht ein Neustart desselben
        # Containers (das ueberlebt trivial jeder Bind-Mount, ohne dass
        # irgendetwas bewiesen waere) - es ist ein komplett NEUER Container
        # auf demselben Volume. Genau das macht Coolify bei jedem
        # Deployment: alter Container weg, neuer hoch, gleiches Volume.
        _laufen("docker", "rm", "-f", name_1, pruefen=False)

        # Der harte Stopp laesst PostgreSQL keine Zeit, seine Sperrdatei zu
        # entfernen. Erst festhalten, dass sie wirklich liegen bleibt - das
        # ist der Ausgangspunkt des Fehlers, um den es hier geht.
        assert _im_volume(volume, image, "cat /data/pgdata/postmaster.pid").stdout.strip(), (
            "Nach 'docker rm -f' sollte PostgreSQLs Sperrdatei im Volume liegen "
            "bleiben. Fehlt sie, prueft dieser Test den Fehlerfall nicht mehr."
        )

        name_2 = f"flashcards-{uuid.uuid4().hex[:8]}"
        try:
            starten(name_2, "bash", "-c", SABOTAGE)
            _warten_bis_gesund(port, name_2)
            # Der Container darf nicht bloss zufaellig hochgekommen sein.
            # Zwei Nachweise aus dem Protokoll:
            #   1. Der Vorspann hat die Sperrdatei wirklich auf eine belegte
            #      Prozessnummer gezeigt - der Fehlerfall lag also vor und
            #      wurde nicht still uebersprungen.
            #   2. Der Einstiegspunkt hat genau diese Datei gefunden und
            #      entfernt, und zwar nicht stillschweigend.
            protokoll = _laufen("docker", "logs", name_2, pruefen=False).stdout
            protokoll += _laufen("docker", "logs", name_2, pruefen=False).stderr
            belegte = re.search(r"TEST-VORSPANN: .*belegte PID (\d+)", protokoll)
            entfernte = re.search(r"Verwaiste Sperrdatei gefunden: .*PID: (\d+)", protokoll)
            assert belegte, f"Der Test-Vorspann ist nicht gelaufen. Protokoll:\n{protokoll}"
            assert entfernte, (
                "Der Einstiegspunkt hat die verwaiste Sperrdatei nicht gemeldet - "
                f"er raeumt sie entweder nicht weg oder tut es still. Protokoll:\n{protokoll}"
            )
            assert belegte.group(1) == entfernte.group(1), (
                "Entfernt wurde eine andere Sperrdatei als die praeparierte - "
                "der Test prueft dann nicht mehr den gemeinten Fall."
            )
            zaehlung = _laufen(
                "docker", "exec", name_2, "psql", "-U", "flashcards", "-d", "flashcards",
                "-tAc", "SELECT count(*) FROM bundles WHERE slug = 'rote-katze-springt'",
            )
            assert zaehlung.stdout.strip() == "1"
        finally:
            _laufen("docker", "rm", "-f", name_2, pruefen=False)
    finally:
        _laufen("docker", "rm", "-f", name_1, pruefen=False)
        aufraeumen()
