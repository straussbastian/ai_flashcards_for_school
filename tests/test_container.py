import json
import shutil
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
PORT = 18000


def _laufen(*befehl: str, pruefen: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(befehl, capture_output=True, text=True, check=pruefen)


@pytest.fixture(scope="module")
def image():
    _laufen("docker", "build", "-t", IMAGE, ".")
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

    def starten(name: str) -> None:
        _laufen(
            "docker", "run", "-d", "--name", name,
            "-v", f"{volume}:/data",
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "DATABASE_URL=postgresql+psycopg://flashcards:test@localhost:5432/flashcards",
            "-e", "APP_SECRET=test",
            "-e", "TEACHER_PASSWORD=test",
            "-e", "BASE_URL=http://localhost:8000",
            "-p", f"{PORT}:8000",
            image,
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
        gesundheit = _warten_bis_gesund(PORT, name_1)
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

        name_2 = f"flashcards-{uuid.uuid4().hex[:8]}"
        try:
            starten(name_2)
            _warten_bis_gesund(PORT, name_2)
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
