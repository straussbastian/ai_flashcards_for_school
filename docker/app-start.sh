#!/usr/bin/env bash
set -euo pipefail

echo "Warte auf PostgreSQL ..."
for _ in $(seq 1 60); do
    if pg_isready -h localhost -q; then break; fi
    sleep 1
done
pg_isready -h localhost -q || { echo "PostgreSQL ist nicht hochgekommen." >&2; exit 1; }

if [ -f /data/.cluster-neu ]; then
    echo "Lege Rolle und Datenbank an."
    # Ueber den lokalen Socket, nicht ueber -h localhost: initdb wurde mit
    # --auth-host=scram-sha-256 aufgerufen, eine Verbindung ueber -h localhost
    # braeuchte also ein Passwort - das der Systembenutzer postgres nicht hat.
    # --auth-local=trust erlaubt den Socket-Weg ohne Passwort.
    su postgres -c "psql -U postgres -v ON_ERROR_STOP=1" <<SQL
CREATE ROLE flashcards LOGIN PASSWORD '${POSTGRES_PASSWORD}';
CREATE DATABASE flashcards OWNER flashcards;
SQL
    rm -f /data/.cluster-neu
fi

echo "Fuehre Migrationen aus."
alembic upgrade head

echo "Starte Webserver."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
