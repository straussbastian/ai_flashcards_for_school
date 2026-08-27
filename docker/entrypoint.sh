#!/usr/bin/env bash
set -euo pipefail

# --- Die kritische Pruefung -------------------------------------------------
# Ohne persistentes Volume waeren alle Lernseiten beim naechsten Deploy weg.
# Lieber gar nicht starten als still Daten verlieren.
if ! mountpoint -q /data; then
    if [ "${ALLOW_EPHEMERAL_DATA:-0}" != "1" ]; then
        echo "FEHLER: /data ist kein gemountetes Volume." >&2
        echo "" >&2
        echo "Die Datenbank liegt in /data. Ohne persistentes Volume waeren alle" >&2
        echo "Lernseiten nach dem naechsten Deployment verloren." >&2
        echo "" >&2
        echo "In Coolify unter 'Persistent Storage' ein Volume auf /data anlegen." >&2
        echo "Nur zum lokalen Ausprobieren: ALLOW_EPHEMERAL_DATA=1 setzen." >&2
        exit 1
    fi
    echo "WARNUNG: /data ist kein Volume. Daten gehen beim Stoppen verloren." >&2
fi

mkdir -p /data/pgdata
chown -R postgres:postgres /data/pgdata
chmod 700 /data/pgdata

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Erststart: Datenbank-Cluster wird angelegt."
    su postgres -c "initdb -D '$PGDATA' --encoding=UTF8 --locale=C.UTF-8 --auth-local=trust --auth-host=scram-sha-256"
    echo "listen_addresses = 'localhost'" >> "$PGDATA/postgresql.conf"
fi

# Bewusst KEINE Markierungsdatei fuer "Cluster ist neu": Sie waere Zustand
# ausserhalb der Datenbank, der mit der Datenbank synchron gehalten werden
# muesste. db-init.sh fragt stattdessen den Cluster selbst (pg_roles,
# pg_database) und darf deshalb bei jedem Start unveraendert durchlaufen.

exec supervisord -c /app/docker/supervisord.conf
