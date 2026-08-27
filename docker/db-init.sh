#!/usr/bin/env bash
set -euo pipefail

# Laeuft als OS-Benutzer postgres (siehe supervisord.conf). Der App-Prozess
# laeuft unprivilegiert (user=app) und kann kein su postgres mehr, deshalb
# dieser eigene Programmschritt fuer Rollen-/Datenbankanlage.
#
# Dieses Skript ist bewusst WIEDERHOLBAR: Es fragt bei jedem Start den
# Cluster selbst, ob Rolle und Datenbank schon existieren, und legt nur an,
# was fehlt. Es gibt deshalb keine Markierungsdatei mehr, die den "ist neu"-
# Zustand ausserhalb der Datenbank fuehren und mit ihr synchron gehalten
# werden muesste.

# POSTGRES_PASSWORD ausdruecklich in der Shell pruefen, bevor psql startet:
# psqls \getenv setzt die Variable bei fehlender Umgebungsvariable einfach
# nicht, :'pw' bliebe als Literal stehen und psql meldete nur einen
# Syntaxfehler. Hier gibt es stattdessen Klartext.
if [ -z "${POSTGRES_PASSWORD:-}" ]; then
    echo "FEHLER: POSTGRES_PASSWORD ist nicht gesetzt." >&2
    echo "" >&2
    echo "Ohne dieses Passwort koennen Rolle und Datenbank nicht angelegt" >&2
    echo "und das Passwort der Rolle flashcards nicht abgeglichen werden." >&2
    echo "In Coolify unter 'Environment Variables' POSTGRES_PASSWORD setzen" >&2
    echo "- passend zum Passwort in DATABASE_URL." >&2
    exit 1
fi

echo "Warte auf PostgreSQL (db-init) ..."
for _ in $(seq 1 60); do
    if pg_isready -h localhost -q; then break; fi
    sleep 1
done
pg_isready -h localhost -q || { echo "PostgreSQL ist nicht hochgekommen (db-init)." >&2; exit 1; }

# Alle Wartungsverbindungen ueber den lokalen Socket, nicht ueber
# -h localhost: initdb laeuft mit --auth-host=scram-sha-256, eine Verbindung
# ueber localhost braeuchte also ein Passwort, das der Systembenutzer
# postgres nicht hat. --auth-local=trust erlaubt den Socket-Weg ohne.

# Rolle anlegen, falls sie fehlt. CREATE ROLE kennt kein IF NOT EXISTS,
# deshalb der DO-Block mit Blick in pg_roles. Das Passwort steht bewusst
# NICHT hier drin: psql ersetzt seine Variablen (:'pw') nicht innerhalb
# dollar-gequoteter Bloecke - das erledigt das ALTER ROLE unten.
echo "Stelle sicher, dass die Rolle flashcards existiert."
psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'flashcards') THEN
        CREATE ROLE flashcards LOGIN;
    END IF;
END
$$;
SQL

# Passwort bei JEDEM Start abgleichen, nicht nur beim Erststart: Sonst laeuft
# ein spaeter geaendertes POSTGRES_PASSWORD an der schon bestehenden Rolle
# vorbei, Rolle und DATABASE_URL fallen auseinander und die App kommt nicht
# mehr hoch. Erst hier, nachdem die Rolle sicher existiert.
#
# \getenv liest POSTGRES_PASSWORD direkt aus der Prozessumgebung von psql,
# :'pw' laesst psql selbst korrekt fuer SQL quoten. Damit landet das Passwort
# nie als Text in einer Shell-Kommandozeile oder direkt interpoliert in einer
# SQL-Anweisung - ein Passwort mit einem einfachen Anfuehrungszeichen wuerde
# eine direkte String-Interpolation syntaktisch aufbrechen.
echo "Gleiche das Passwort der Rolle flashcards ab."
psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'
\getenv pw POSTGRES_PASSWORD
ALTER ROLE flashcards WITH LOGIN PASSWORD :'pw';
SQL

# Datenbank anlegen, falls sie fehlt. CREATE DATABASE kennt ebenfalls kein
# IF NOT EXISTS und darf nicht in einem Transaktionsblock (und damit nicht in
# einem DO-Block) stehen - deshalb erst pg_database fragen, dann bei Bedarf
# genau einen Befehl absetzen.
vorhanden=$(psql -U postgres -v ON_ERROR_STOP=1 -tAc \
    "SELECT 1 FROM pg_database WHERE datname = 'flashcards'")
if [ "$vorhanden" = "1" ]; then
    echo "Datenbank flashcards ist vorhanden."
else
    echo "Lege Datenbank flashcards an."
    psql -U postgres -v ON_ERROR_STOP=1 \
        -c "CREATE DATABASE flashcards OWNER flashcards"
fi

echo "db-init abgeschlossen."
