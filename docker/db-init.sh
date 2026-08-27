#!/usr/bin/env bash
set -euo pipefail

# Laeuft als OS-Benutzer postgres (siehe supervisord.conf) - kein su noetig,
# anders als frueher. Der App-Prozess laeuft inzwischen unprivilegiert
# (user=app) und kann kein su postgres mehr, deshalb dieser eigene
# Programmschritt fuer Rollen-/Datenbankanlage.
echo "Warte auf PostgreSQL (db-init) ..."
for _ in $(seq 1 60); do
    if pg_isready -h localhost -q; then break; fi
    sleep 1
done
pg_isready -h localhost -q || { echo "PostgreSQL ist nicht hochgekommen (db-init)." >&2; exit 1; }

if [ -f /data/.cluster-neu ]; then
    echo "Lege Rolle und Datenbank an."
    # Ueber den lokalen Socket, nicht ueber -h localhost: initdb laeuft mit
    # --auth-host=scram-sha-256, eine Verbindung ueber -h localhost braeuchte
    # also ein Passwort - das der Systembenutzer postgres nicht hat.
    # --auth-local=trust erlaubt den Socket-Weg ohne Passwort.
    #
    # \getenv liest POSTGRES_PASSWORD direkt aus der Prozessumgebung von
    # psql und legt es als psql-Variable ab; :'pw' laesst psql selbst
    # korrekt fuer SQL quoten. Damit landet das Passwort nie als Text in
    # einer Shell-Kommandozeile oder direkt interpoliert in einer
    # SQL-Anweisung - ein Passwort mit einem einfachen Anfuehrungszeichen
    # wuerde eine direkte String-Interpolation syntaktisch aufbrechen.
    psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'
\getenv pw POSTGRES_PASSWORD
CREATE ROLE flashcards LOGIN PASSWORD :'pw';
CREATE DATABASE flashcards OWNER flashcards;
SQL
    rm -f /data/.cluster-neu
fi

# Passwort bei JEDEM Start synchronisieren, nicht nur beim Erststart: Sonst
# laeuft ein spaeter geaendertes POSTGRES_PASSWORD an der schon bestehenden
# Rolle vorbei, Rolle und DATABASE_URL fallen auseinander und die App kommt
# nicht mehr hoch, ohne dass irgendwo offensichtlich etwas rot wird.
psql -U postgres -v ON_ERROR_STOP=1 <<'SQL'
\getenv pw POSTGRES_PASSWORD
ALTER ROLE flashcards WITH PASSWORD :'pw';
SQL

echo "db-init abgeschlossen."
