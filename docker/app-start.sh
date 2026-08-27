#!/usr/bin/env bash
set -euo pipefail

# Gewartet wird auf die Bedingung, die wirklich zaehlt: eine echte Verbindung
# mit den Zugangsdaten der Anwendung (DATABASE_URL). Das deckt alles ab, was
# vorher einzeln geprueft wurde - Server oben, Rolle da, Datenbank da,
# Passwort passend - und haengt an keinem Hilfszustand ausserhalb der
# Datenbank.
#
# Damit faellt auch auf, wenn db-init.sh scheitert: Frueher war das eine
# reine Logzeile ohne Wirkung, die App lief mit dem alten Passwort weiter und
# der Passwortabgleich war still ausgefallen. Und es fangt den Fall ab, dass
# supervisord die App zwar nach db-init startet (priority), aber nicht auf
# deren Ende wartet - bei einer Passwortrotation kann Alembic sonst mit dem
# neuen Passwort verbinden wollen, bevor ALTER ROLE durch ist.
echo "Warte auf die Datenbank (Verbindung mit den Zugangsdaten der Anwendung) ..."
python - <<'PY'
import sys
import time

from sqlalchemy import create_engine, text

try:
    from app.config import get_settings

    url = get_settings().database_url
except Exception as fehler:  # noqa: BLE001
    print("FEHLER: Die Konfiguration konnte nicht gelesen werden.", file=sys.stderr)
    print(f"Grund: {type(fehler).__name__}: {fehler}", file=sys.stderr)
    print(
        "Pruefe DATABASE_URL, APP_SECRET, TEACHER_PASSWORD und BASE_URL.",
        file=sys.stderr,
    )
    sys.exit(1)

FRIST_SEKUNDEN = 90
ende = time.monotonic() + FRIST_SEKUNDEN
letzter_fehler = None

while True:
    # create_engine gehoert mit in den try-Block: Eine DATABASE_URL, die zwar
    # durch die Pydantic-Pruefung kommt, aber von SQLAlchemy nicht getragen
    # wird - etwa postgres:// statt postgresql+psycopg:// -, liesse den
    # Aufruf sonst mit einem unbehandelten Fehler fliegen. Es gaebe einen
    # Python-Traceback statt der Klartextmeldung weiter unten.
    maschine = None
    try:
        maschine = create_engine(url, connect_args={"connect_timeout": 3})
        with maschine.connect() as verbindung:
            verbindung.execute(text("SELECT 1"))
        print("Datenbank ist erreichbar.")
        sys.exit(0)
    except Exception as fehler:  # noqa: BLE001
        letzter_fehler = fehler
    finally:
        if maschine is not None:
            maschine.dispose()
    if time.monotonic() >= ende:
        break
    time.sleep(1)

print(
    f"FEHLER: Nach {FRIST_SEKUNDEN} Sekunden keine Verbindung zur Datenbank.",
    file=sys.stderr,
)
print("", file=sys.stderr)
print("Wahrscheinliche Gruende:", file=sys.stderr)
print("  - PostgreSQL im Container ist nicht hochgekommen", file=sys.stderr)
print(
    "  - Rolle oder Datenbank 'flashcards' fehlen (db-init.sh ist nicht "
    "durchgelaufen - siehe dessen Meldungen weiter oben im Log)",
    file=sys.stderr,
)
print(
    "  - das Passwort in DATABASE_URL passt nicht zu POSTGRES_PASSWORD",
    file=sys.stderr,
)
print(
    "  - Host oder Port in DATABASE_URL zeigen nicht auf die Datenbank im "
    "Container (erwartet wird localhost:5432)",
    file=sys.stderr,
)
print(
    "  - das Schema in DATABASE_URL wird von SQLAlchemy nicht getragen "
    "(erwartet wird postgresql+psycopg://, nicht postgres://)",
    file=sys.stderr,
)
print("", file=sys.stderr)
print(f"Letzter Fehler: {type(letzter_fehler).__name__}: {letzter_fehler}", file=sys.stderr)
sys.exit(1)
PY

echo "Fuehre Migrationen aus."
alembic upgrade head

echo "Starte Webserver."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
