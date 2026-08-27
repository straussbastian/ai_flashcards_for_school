import os
import subprocess
import sys

from sqlalchemy import text


async def test_datenbank_antwortet(session):
    ergebnis = await session.scalar(text("SELECT 1"))
    assert ergebnis == 1


def test_app_db_importierbar_ohne_datenbank_umgebung(tmp_path):
    """app.db und app.main duerfen beim blossen Import an keiner Umgebungsvariable haengen.

    Vorher wertete app/db.py beim Import get_settings().database_url aus -
    ein Pflichtfeld ohne Default. Auf einem frischen Checkout ohne .env
    (z.B. in CI) scheiterte damit schon der Import von tests/conftest.py mit
    einer ValidationError, und das Einsammeln aller Tests brach ab - auch
    von tests/test_config.py, das bewusst ohne jede Konfiguration laufen
    soll. app/db.py erzeugt die Engine seither erst lazy (get_engine(),
    get_session_factory(), beide lru_cache), sodass nur die tatsaechliche
    Nutzung an DATABASE_URL haengt, nicht der Import.

    Der Test laeuft in einem eigenen Subprozess mit einem Arbeitsverzeichnis
    ohne .env-Datei: Nur so wird echtes Verhalten eines frischen Checkouts
    geprueft. Ein blosses importlib.reload im laufenden Testprozess wuerde
    das Ergebnis verfaelschen, weil get_settings() prozessweit gecacht ist
    (lru_cache) - eine fruehere Testausfuehrung koennte die Cache-Instanz
    schon gefuellt haben, egal was gerade in os.environ steht.
    """
    umgebung = {
        schluessel: wert
        for schluessel, wert in os.environ.items()
        if schluessel
        not in {
            "DATABASE_URL",
            "TEST_DATABASE_URL",
            "APP_SECRET",
            "TEACHER_PASSWORD",
            "BASE_URL",
        }
    }

    ergebnis = subprocess.run(
        [sys.executable, "-c", "import app.db; import app.main"],
        cwd=tmp_path,
        env=umgebung,
        capture_output=True,
        text=True,
    )

    assert ergebnis.returncode == 0, ergebnis.stderr
