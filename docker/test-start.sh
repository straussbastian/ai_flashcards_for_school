#!/usr/bin/env bash
set -euo pipefail

# Die Suite im Container, gegen genau den Stapel, der spaeter auch laeuft:
# dasselbe Abbild wie im Betrieb (Dockerfile, Stufe "test" baut auf "betrieb"
# auf), dasselbe PostgreSQL 17 im Dienst daneben.
#
# Der Container beendet sich mit dem Rueckgabewert von pytest. Das ist der
# Punkt, an dem die CI haengt: Ein roter Lauf ist ein roter Container.
#
# Auf den db-Dienst zu warten ist hier eigentlich schon erledigt -
# compose.test.yml haelt diesen Container ueber "depends_on:
# service_healthy" zurueck, bis pg_isready durchgeht. Die Wartezeit bleibt
# trotzdem: Sie kostet im Normalfall nichts und macht den Unterschied
# zwischen einer Klartextmeldung und einem Wust aus Verbindungsfehlern
# quer durch die halbe Suite, falls jemand diesen Container einmal ohne
# compose startet.

echo "═══ Warte auf die Datenbank ═══"
python - <<'PY'
import sys
import time

import psycopg

# Aus der SQLAlchemy-Form (postgresql+psycopg://) die Form machen, die
# psycopg selbst versteht (postgresql://). Beide URLs stehen in
# compose.test.yml und zeigen auf denselben Server.
URL = "postgresql://flashcards:test-nur-fuer-diesen-lauf@db:5432/postgres"

ende = time.monotonic() + 60
letzter_fehler = None
while time.monotonic() < ende:
    try:
        with psycopg.connect(URL, connect_timeout=3):
            print("Datenbank ist erreichbar.")
            sys.exit(0)
    except Exception as fehler:  # noqa: BLE001
        letzter_fehler = fehler
        time.sleep(1)

print(f"FEHLER: Die Datenbank kam in 60 Sekunden nicht hoch: {letzter_fehler}", file=sys.stderr)
sys.exit(1)
PY

# Die Testdatenbank. Eigene Datenbank im selben Cluster und nicht ein eigener
# Server: Die Suite legt ihr Schema darin bei jedem Lauf neu an
# (Base.metadata.drop_all/create_all in tests/conftest.py) und darf dabei der
# Datenbank der Anwendung nicht in die Quere kommen.
#
# Ueber psycopg und nicht ueber createdb: Dann braucht das Testabbild kein
# postgresql-client-Paket. Angelegt wird nur, was fehlt - "docker compose
# run --rm test" darf beliebig oft laufen.
echo "═══ Lege die Testdatenbank an ═══"
python - <<'PY'
import psycopg

URL = "postgresql://flashcards:test-nur-fuer-diesen-lauf@db:5432/postgres"

# autocommit ist Pflicht: CREATE DATABASE darf nicht in einem
# Transaktionsblock stehen, und psycopg oeffnet sonst von sich aus einen.
with psycopg.connect(URL, autocommit=True) as verbindung:
    vorhanden = verbindung.execute(
        "select 1 from pg_database where datname = 'flashcards_test'"
    ).fetchone()
    if vorhanden:
        print("Testdatenbank flashcards_test ist vorhanden.")
    else:
        verbindung.execute("create database flashcards_test owner flashcards")
        print("Testdatenbank flashcards_test angelegt.")
PY

# Die Migrationen gegen die Datenbank der Anwendung - genau der Weg, den
# docker/app-start.sh im Betrieb bei jedem Start geht. Scheitert er, faellt
# es hier auf und nicht beim Deployment.
echo "═══ Migrationen einspielen ═══"
alembic upgrade head

# "alembic check" schlaegt an, sobald Modelle und Migrationen auseinander
# laufen - also sobald jemand ein Modell aendert und die Migration vergisst.
# Dieser Schritt hat einen eigenen Absatz verdient, weil er sonst still
# verloren ginge: Er stand frueher als eigener Schritt in der CI, und KEIN
# Test deckt ihn ab (tests/test_migrations.py sagt das in seinem Docstring
# ausdruecklich). Ohne diese Zeile waere die Deckungsgleichheit von Modellen
# und Migrationen wieder etwas, das nur von Hand geprueft wird.
echo "═══ Migrationen gegen die Modelle pruefen ═══"
alembic check

# Argumente durchreichen: "docker compose -f compose.test.yml run --rm test
# -k oauth -x" laesst genau diese Auswahl laufen und sonst nichts. Ohne
# Argumente laeuft die vollstaendige Suite - und zwar in zwei Durchgaengen.
if [ "$#" -gt 0 ]; then
    echo "═══ Suite (eigene Auswahl: $*) ═══"
    exec pytest "$@"
fi

echo "═══ Suite ═══"
pytest -v

# Zweiter Durchgang, ausdruecklich "-m browser": Die Browsertests sind in
# pyproject.toml per addopts abgewaehlt ("-m 'not browser'"), damit ein
# frischer Checkout ohne Chromium gruen bleibt. Das -m von der Kommandozeile
# ueberschreibt das. Hier im Testabbild IST ein Chromium, also laufen sie -
# sie starten sich ihren eigenen uvicorn auf einem freien Port und legen ihre
# Bundles in der Testdatenbank an (siehe tests/browser/conftest.py).
echo "═══ Browsertests ═══"
pytest -m browser -v
