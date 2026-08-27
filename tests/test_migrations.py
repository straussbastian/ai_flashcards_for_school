import os
import subprocess
import sys
from pathlib import Path

PROJEKTVERZEICHNIS = Path(__file__).resolve().parent.parent


def test_datenbank_url_mit_prozentzeichen_verursacht_keinen_interpolationsfehler():
    """Regressionstest fuer WICHTIG 2 aus der Fix-Runde zu Task 4.

    migrations/env.py reichte die Datenbank-URL bisher ueber
    config.set_main_option("sqlalchemy.url", ...) durch. Alembics Config ist
    intern ein ConfigParser mit BasicInterpolation, die '%' als
    Interpolationszeichen behandelt. Ein Datenbankpasswort mit '%' (bei
    URL-kodierten Passwoertern der Normalfall, z.B. '%40' fuer '@') liess
    set_main_option() deshalb sofort mit einem ValueError
    ("invalid interpolation syntax") scheitern - noch bevor ueberhaupt ein
    Verbindungsversuch stattfand. Im Container laeuft die Migration beim
    Start; das haette den Start beim Kunden gekippt, nie bei uns (unser
    Entwicklungspasswort enthaelt kein '%').

    Die URL hier zeigt bewusst auf einen nicht erreichbaren Port
    (Connection Refused statt DNS-Timeout, damit der Test schnell bleibt):
    Es geht nicht darum, dass die Migration gelingt, sondern dass sie an
    der Datenbankverbindung scheitert - niemals an der Alembic-Konfiguration
    selbst. Vor dem Fix brach der Prozess schon vor dem Verbindungsversuch
    mit einem ValueError/InterpolationSyntaxError ab; nach dem Fix (URL wird
    direkt in das Dict fuer async_engine_from_config eingetragen statt ueber
    den ConfigParser geschleust, siehe migrations/env.py) kommt die URL
    unveraendert bei psycopg an, und der Fehlschlag ist ein gewoehnlicher
    Verbindungsfehler.
    """
    passwort_mit_prozentzeichen = "geheim%40mit%25prozent"
    url = (
        f"postgresql+psycopg://nutzer:{passwort_mit_prozentzeichen}"
        "@localhost:59999/nicht_erreichbar"
    )

    umgebung = dict(os.environ)
    umgebung["DATABASE_URL"] = url
    umgebung["APP_SECRET"] = "x"
    umgebung["TEACHER_PASSWORD"] = "x"

    ergebnis = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJEKTVERZEICHNIS,
        env=umgebung,
        capture_output=True,
        text=True,
        timeout=30,
    )

    ausgabe = ergebnis.stdout + ergebnis.stderr

    # Der eigentliche Bug: set_main_option() scheiterte an '%' im Passwort,
    # bevor irgendein Verbindungsversuch stattfand.
    assert "interpolation" not in ausgabe.lower(), ausgabe
    assert "InterpolationSyntaxError" not in ausgabe, ausgabe

    # Der erwartete, unvermeidliche Fehlschlag: die Verbindung selbst.
    assert ergebnis.returncode != 0
    assert "OperationalError" in ausgabe or "Connection refused" in ausgabe
