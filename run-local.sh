#!/usr/bin/env bash
set -euo pipefail

# Startet den Container lokal, so wie er spaeter auch in Coolify laeuft:
# ein Container, Datenbank und Webserver darin, Daten in einem Volume.
#
# ACHTUNG: Die Passwoerter hier unten sind ENTWICKLUNGSPASSWOERTER. Sie
# stehen absichtlich im Klartext im Repository, weil dieser Container nur
# an localhost lauscht und keine echten Daten enthaelt. Fuer den Betrieb
# werden die Werte in Coolify gesetzt und tauchen nirgends im Git auf.

NAME=flashcards-lokal
DATEN="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/daten"

mkdir -p "$DATEN"

docker build -t flashcards .
docker rm -f "$NAME" 2>/dev/null || true

docker run -d --name "$NAME" \
    -v "$DATEN:/data" \
    -e POSTGRES_PASSWORD=nur-lokal-entwicklung \
    -e DATABASE_URL='postgresql+psycopg://flashcards:nur-lokal-entwicklung@localhost:5432/flashcards' \
    -e APP_SECRET=nur-lokal-entwicklung-kein-echtes-geheimnis \
    -e TEACHER_PASSWORD=nur-lokal-entwicklung \
    -e BASE_URL=http://localhost:8000 \
    -p 8000:8000 \
    flashcards

echo "Container laeuft. Logs:  docker logs -f $NAME"
echo "Pruefen:                 curl -s http://localhost:8000/healthz"
echo "Stoppen:                 docker rm -f $NAME"
