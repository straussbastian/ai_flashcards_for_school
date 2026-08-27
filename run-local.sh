#!/usr/bin/env bash
set -euo pipefail

# Startet den Container lokal, so wie er spaeter auch in Coolify laeuft:
# ein Container, Datenbank und Webserver darin, Daten in einem Volume.
#
# ACHTUNG: Die Passwoerter hier unten sind ENTWICKLUNGSPASSWOERTER. Sie
# stehen absichtlich im Klartext im Repository, weil dieser Container nur
# an localhost lauscht (Bindung an 127.0.0.1 erzwingt diese Beschraenkung)
# und keine echten Daten enthaelt. Fuer den Betrieb werden die Werte in
# Coolify gesetzt und tauchen nirgends im Git auf.

NAME=flashcards-lokal
DATEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/daten"

mkdir -p "$DATEN"

docker build -t flashcards .

# Den alten Container geordnet beenden statt hart abschiessen. Bei einem
# SIGKILL (docker rm -f) kommt PostgreSQL nicht mehr dazu, seine Sperrdatei
# postmaster.pid zu entfernen; der naechste Start muss sie dann erst
# aufraeumen (docker/entrypoint.sh tut das). Sauberer ist, sie gar nicht
# erst entstehen zu lassen: Mit SIGTERM faehrt PostgreSQL mit einem
# Abschluss-Checkpoint herunter, statt beim naechsten Start per
# Crash-Recovery aus dem WAL hochzukommen.
#
# Die Frist gehoert zu docker/supervisord.conf: Dort hat postgres
# stopwaitsecs=30 fuer diesen Checkpoint und app stopwaitsecs=5, und
# supervisord beendet die Programme nacheinander. 45 Sekunden lassen dafuer
# Luft. Wird die Frist ueberschritten, schickt Docker doch noch SIGKILL -
# das bleibt folgenlos, weil der naechste Start die Sperrdatei wegraeumt.
if docker inspect "$NAME" >/dev/null 2>&1; then
    echo "Beende den laufenden Container geordnet (Frist: 45 Sekunden) ..."
    docker stop -t 45 "$NAME" >/dev/null || true
    docker rm -f "$NAME" >/dev/null 2>&1 || true
fi

docker run -d --name "$NAME" \
    -v "$DATEN:/data" \
    -e POSTGRES_PASSWORD=nur-lokal-entwicklung \
    -e DATABASE_URL='postgresql+psycopg://flashcards:nur-lokal-entwicklung@localhost:5432/flashcards' \
    -e APP_SECRET=nur-lokal-entwicklung-kein-echtes-geheimnis \
    -e TEACHER_PASSWORD=nur-lokal-entwicklung \
    -e BASE_URL=http://localhost:8000 \
    -p 127.0.0.1:8000:8000 \
    flashcards

echo "Container laeuft. Logs: docker logs -f $NAME"
echo "Pruefen:                 curl -s http://localhost:8000/healthz"
echo "Stoppen (geordnet):      docker stop -t 45 $NAME && docker rm $NAME"
