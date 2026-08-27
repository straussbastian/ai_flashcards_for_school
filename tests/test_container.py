import json
import shutil
import subprocess
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker ist nicht verfuegbar"
)

IMAGE = "flashcards-test"


def _laufen(*befehl: str, pruefen: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(befehl, capture_output=True, text=True, check=pruefen)


@pytest.fixture(scope="module")
def image():
    _laufen("docker", "build", "-t", IMAGE, ".")
    return IMAGE


def test_ohne_volume_bricht_der_container_mit_klartext_ab(image):
    ergebnis = _laufen("docker", "run", "--rm", image, pruefen=False)
    assert ergebnis.returncode != 0
    assert "/data" in (ergebnis.stdout + ergebnis.stderr)


def test_mit_volume_wird_die_seite_erreichbar_und_daten_ueberleben(image, tmp_path):
    name = f"flashcards-{uuid.uuid4().hex[:8]}"
    volume = tmp_path / "daten"
    volume.mkdir()

    def starten() -> None:
        _laufen(
            "docker", "run", "-d", "--name", name,
            "-v", f"{volume}:/data",
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "DATABASE_URL=postgresql+psycopg://flashcards:test@localhost:5432/flashcards",
            "-e", "APP_SECRET=test",
            "-e", "TEACHER_PASSWORD=test",
            "-e", "BASE_URL=http://localhost:8000",
            "-p", "18000:8000",
            image,
        )

    def warten_bis_gesund() -> dict:
        for _ in range(60):
            ergebnis = _laufen(
                "docker", "exec", name,
                "python", "-c",
                "import urllib.request,sys;"
                "sys.stdout.write(urllib.request.urlopen('http://localhost:8000/healthz').read().decode())",
                pruefen=False,
            )
            if ergebnis.returncode == 0 and '"ok"' in ergebnis.stdout:
                return json.loads(ergebnis.stdout)
            time.sleep(2)
        logs = _laufen("docker", "logs", name, pruefen=False)
        pytest.fail(f"Container wurde nicht gesund. Logs:\n{logs.stdout}\n{logs.stderr}")

    try:
        starten()
        gesundheit = warten_bis_gesund()
        assert gesundheit["datenbank"] == "ok"

        # Eine Zeile schreiben, Container neu starten, Zeile muss noch da sein.
        _laufen(
            "docker", "exec", name, "psql", "-U", "flashcards", "-d", "flashcards",
            "-c", "INSERT INTO bundles (id, slug, titel) "
                  "VALUES (gen_random_uuid(), 'rote-katze-springt', 'Test')",
        )
        _laufen("docker", "restart", name)
        warten_bis_gesund()
        zaehlung = _laufen(
            "docker", "exec", name, "psql", "-U", "flashcards", "-d", "flashcards",
            "-tAc", "SELECT count(*) FROM bundles WHERE slug = 'rote-katze-springt'",
        )
        assert zaehlung.stdout.strip() == "1"
    finally:
        _laufen("docker", "rm", "-f", name, pruefen=False)
