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
        # Wie in tests/test_migrations.py: Jeder Kindprozess bekommt eine
        # Obergrenze. Ein haengender Import wuerde die Suite sonst unbegrenzt
        # blockieren - in der CI bis zum Jobtimeout von 45 Minuten - statt
        # rot zu werden. Ein reiner Import braucht Sekundenbruchteile; 60
        # Sekunden sind auch auf einem ausgelasteten Runner reichlich.
        timeout=60,
    )

    assert ergebnis.returncode == 0, ergebnis.stderr


async def test_engine_zuruecksetzen_gibt_eine_frische_engine(monkeypatch):
    """Das Gegenstueck zu den lru_cache-Dekoratoren in app/db.py.

    get_engine() und get_session_factory() sind gecacht. Ohne Ruecknahme
    traegt die Engine des ersten Tests, der eine echte Engine anfasst, ihre
    Konfiguration in alle folgenden weiter: Ein spaeterer Test mit anderer
    DATABASE_URL bekaeme stillschweigend die alte Verbindung. Ab Plan 2 gibt
    es solche Tests; die Ruecknahme muss vorher stehen.

    Es wird nur erzeugt, nicht verbunden - create_async_engine baut keine
    Verbindung auf. Die URL zeigt deshalb absichtlich ins Leere.
    """
    from app.config import get_settings
    from app.db import engine_zuruecksetzen, get_engine, get_session_factory

    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://u:p@localhost:59999/nirgendwo"
    )
    monkeypatch.setenv("APP_SECRET", "x")
    monkeypatch.setenv("TEACHER_PASSWORD", "x")
    monkeypatch.setenv("BASE_URL", "http://localhost:8000")

    get_settings.cache_clear()
    await engine_zuruecksetzen()
    try:
        erste = get_engine()
        assert get_engine() is erste, "der lru_cache muss dieselbe Engine liefern"
        erste_fabrik = get_session_factory()

        await engine_zuruecksetzen()

        assert get_engine() is not erste, "nach der Ruecknahme muss sie frisch sein"
        assert get_session_factory() is not erste_fabrik
    finally:
        # Weder Engine noch Einstellungen dieses Tests duerfen in andere
        # Tests lecken - der Cache ist prozessweit.
        await engine_zuruecksetzen()
        get_settings.cache_clear()
