#!/usr/bin/env bash
set -euo pipefail

echo "Warte auf PostgreSQL ..."
for _ in $(seq 1 60); do
    if pg_isready -h localhost -q; then break; fi
    sleep 1
done
pg_isready -h localhost -q || { echo "PostgreSQL ist nicht hochgekommen." >&2; exit 1; }

# Rolle und Datenbank werden von db-init.sh angelegt, das als OS-Benutzer
# postgres laeuft. Dieser Prozess hier laeuft als unprivilegierter Benutzer
# app (siehe supervisord.conf) und kann kein su postgres mehr - deshalb nur
# warten, bis die Markierungsdatei aus dem Erststart verschwunden ist.
echo "Warte auf Rollen-/Datenbankanlage ..."
for _ in $(seq 1 60); do
    [ -f /data/.cluster-neu ] || break
    sleep 1
done
if [ -f /data/.cluster-neu ]; then
    echo "Rolle/Datenbank wurden nicht rechtzeitig angelegt." >&2
    exit 1
fi

echo "Fuehre Migrationen aus."
alembic upgrade head

echo "Starte Webserver."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
