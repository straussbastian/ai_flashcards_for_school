#!/usr/bin/env bash
set -euo pipefail

# Der Start der Anwendung: auf die Datenbank warten, Migrationen einspielen,
# uvicorn starten. Das ist alles, was in diesem Container passiert - einen
# Prozessverwalter gibt es nicht mehr, und einen Datenbankserver auch nicht
# (siehe compose.yml, Dienst "db").
#
# Gewartet wird auf die Bedingung, die wirklich zaehlt: eine echte Verbindung
# mit den Zugangsdaten der Anwendung (DATABASE_URL). Das deckt alles ab, was
# man sonst einzeln pruefen muesste - Server oben, Rolle da, Datenbank da,
# Passwort passend - und haengt an keinem Hilfszustand ausserhalb der
# Datenbank.
#
# Das ist kein doppelter Boden zu "depends_on: service_healthy" in
# compose.yml, sondern deckt einen anderen Fall ab: depends_on gilt nur beim
# Start des Verbunds. Wird der db-Dienst spaeter neu gestartet - ein
# Deployment, ein Neustart des Hosts -, faehrt diese Wartezeit die Anwendung
# wieder sauber hoch, statt sie in einer Neustartschleife scheitern zu lassen.
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
print(
    "  - der Dienst 'db' ist nicht hochgekommen (docker compose logs db)",
    file=sys.stderr,
)
print(
    "  - das Passwort in DATABASE_URL passt nicht zu POSTGRES_PASSWORD",
    file=sys.stderr,
)
print(
    "  - Host oder Port in DATABASE_URL zeigen nicht auf den db-Dienst "
    "(erwartet wird db:5432, nicht localhost)",
    file=sys.stderr,
)
print(
    "  - Benutzer oder Datenbankname in DATABASE_URL weichen von "
    "POSTGRES_USER/POSTGRES_DB ab; das postgres-Abbild legt genau die an",
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
