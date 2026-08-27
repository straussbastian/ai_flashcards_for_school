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

# --- Verwaiste Sperrdatei aus einem frueheren Lauf entfernen ----------------
# Wird der Container hart gestoppt - docker rm -f, eine ueberschrittene
# Stop-Frist in Coolify, ein Stromausfall -, bekommt PostgreSQL kein Signal
# mehr und laesst seine Sperrdatei postmaster.pid liegen. Beim naechsten Start
# liest PostgreSQL die dort vermerkte Prozessnummer und prueft, ob sie noch
# lebt. In einem frischen Container beginnen die Prozessnummern wieder bei 1,
# die vermerkte Nummer ist deshalb haeufig wieder vergeben - dann haelt
# PostgreSQL einen voellig fremden Prozess fuer einen zweiten Server und
# verweigert den Start:
#
#   FATAL:  lock file "postmaster.pid" already exists
#   HINT:   Is another postmaster (PID 13) running in data directory ...
#
# supervisord versucht es viermal, gibt auf, und der Container bleibt
# dauerhaft ungesund. Er heilt sich auch durch weitere Neustarts nicht,
# solange die Datei liegen bleibt.
#
# Das Entfernen ist hier sicher - anders als auf einem gewoehnlichen Server:
# Der Container hat einen eigenen, frischen Prozessraum. Ein Prozess aus einem
# frueheren Lauf kann darin unmoeglich noch laufen. Eine Sperrdatei, die beim
# Start des Containers schon vorliegt, ist deshalb immer verwaist. Auf einem
# gewoehnlichen Server waere derselbe Griff falsch: Dort kann dieselbe Datei
# einen tatsaechlich laufenden zweiten Server bedeuten.
#
# Bewusst nur genau diese eine Datei und nicht das Datenverzeichnis: Die Daten
# selbst sind unversehrt. PostgreSQL faehrt nach einem harten Stopp aus dem
# WAL per Crash-Recovery sauber hoch - das ist der vorgesehene Weg und
# braucht nichts weiter als die Daten, die ohnehin da sind.
#
# Und nicht still: Ein unbemerkter Eingriff in ein Datenverzeichnis ist das
# Letzte, was jemand bei der Fehlersuche gebrauchen kann.
if [ -e "$PGDATA/postmaster.pid" ]; then
    vermerkte_pid=$(head -n 1 "$PGDATA/postmaster.pid" 2>/dev/null || true)
    echo "Verwaiste Sperrdatei gefunden: $PGDATA/postmaster.pid (vermerkte PID: ${vermerkte_pid:-unbekannt})."
    echo "Sie stammt aus einem frueheren, hart beendeten Lauf und wird entfernt."
    echo "Das ist unbedenklich: Dieser Container hat einen frischen Prozessraum," \
         "in dem kein PostgreSQL aus einem frueheren Lauf mehr laufen kann."
    echo "Die Daten bleiben unangetastet; PostgreSQL faehrt per Crash-Recovery hoch."
    rm -f "$PGDATA/postmaster.pid"
fi

exec supervisord -c /app/docker/supervisord.conf
