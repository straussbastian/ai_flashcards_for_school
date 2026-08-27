#!/usr/bin/env bash
set -euo pipefail

# Coolifys Datenbank-Backups greifen nicht, weil Postgres im App-Container laeuft.
# Deshalb ein eigener Dump ins selbe Volume, das Deployments ueberlebt.
# Ueber den lokalen Socket (kein -h localhost): siehe app-start.sh dazu, warum
# eine Verbindung ueber -h localhost hier ein Passwort verlangen wuerde.
ZIEL="/data/backups/flashcards-$(date +%Y-%m-%d-%H%M).sql.gz"
pg_dump -U flashcards flashcards | gzip > "$ZIEL"
echo "Backup geschrieben: $ZIEL"

# Nur die sieben juengsten behalten.
ls -1t /data/backups/flashcards-*.sql.gz | tail -n +8 | xargs -r rm --
