import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest

from app.markdown import MAX_LAENGE

PROJEKTVERZEICHNIS = Path(__file__).resolve().parent.parent


def test_datenbank_url_mit_prozentzeichen_verursacht_keinen_interpolationsfehler():
    """Regressionstest fuer WICHTIG 2 aus der Fix-Runde zu Task 4.

    migrations/env.py reichte die Datenbank-URL bisher ueber
    config.set_main_option("sqlalchemy.url", ...) durch. Alembics Config ist
    intern ein ConfigParser mit BasicInterpolation, die '%' als
    Interpolationszeichen behandelt. Ein Datenbankpasswort mit '%' (bei
    URL-kodierten Passwoertern der Normalfall, z.B. '%40' fuer '@') liess
    set_main_option() deshalb sofort mit einem ValueError
    ("invalid interpolation syntax") scheitern - noch bevor ueberhaupt ein
    Verbindungsversuch stattfand. Im Container laeuft die Migration beim
    Start; das haette den Start beim Kunden gekippt, nie bei uns (unser
    Entwicklungspasswort enthaelt kein '%').

    Die URL hier zeigt bewusst auf einen nicht erreichbaren Port
    (Connection Refused statt DNS-Timeout, damit der Test schnell bleibt):
    Es geht nicht darum, dass die Migration gelingt, sondern dass sie an
    der Datenbankverbindung scheitert - niemals an der Alembic-Konfiguration
    selbst. Vor dem Fix brach der Prozess schon vor dem Verbindungsversuch
    mit einem ValueError/InterpolationSyntaxError ab; nach dem Fix (URL wird
    direkt in das Dict fuer async_engine_from_config eingetragen statt ueber
    den ConfigParser geschleust, siehe migrations/env.py) kommt die URL
    unveraendert bei psycopg an, und der Fehlschlag ist ein gewoehnlicher
    Verbindungsfehler.
    """
    passwort_mit_prozentzeichen = "geheim%40mit%25prozent"
    url = (
        f"postgresql+psycopg://nutzer:{passwort_mit_prozentzeichen}"
        "@localhost:59999/nicht_erreichbar"
    )

    umgebung = dict(os.environ)
    umgebung["DATABASE_URL"] = url
    umgebung["APP_SECRET"] = "x"
    umgebung["TEACHER_PASSWORD"] = "x"
    # BASE_URL ist seit "BASE_URL ist Pflicht und muss ein Schema tragen"
    # ein Pflichtfeld ohne Default (siehe app/config.py). Ohne diese Zeile
    # haengt dieser Test von der Umgebung ab, in der er laeuft: Auf einem
    # frischen Checkout ohne .env und ohne gesetztes BASE_URL bricht der
    # Kindprozess mit einer pydantic ValidationError ab, statt - wie hier
    # beabsichtigt - am erwarteten Verbindungsfehler zu scheitern. In der CI
    # faellt das nicht auf, weil der Workflow BASE_URL jobweit setzt.
    umgebung["BASE_URL"] = "http://localhost:8000"

    ergebnis = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJEKTVERZEICHNIS,
        env=umgebung,
        capture_output=True,
        text=True,
        timeout=30,
    )

    ausgabe = ergebnis.stdout + ergebnis.stderr

    # Der eigentliche Bug: set_main_option() scheiterte an '%' im Passwort,
    # bevor irgendein Verbindungsversuch stattfand.
    assert "interpolation" not in ausgabe.lower(), ausgabe
    assert "InterpolationSyntaxError" not in ausgabe, ausgabe

    # Der erwartete, unvermeidliche Fehlschlag: die Verbindung selbst.
    assert ergebnis.returncode != 0
    assert "OperationalError" in ausgabe or "Connection refused" in ausgabe


# Der Name einer beliebigen *_max_laenge-Spalte genuegt fuer die Pruefung
# unten - vorderseite ist gewaehlt, weil sie in jeder Karte gesetzt ist
# (nicht optional wie rueckseite/erklaerung).
_KONSTRAINT_NAME = "ck_karten_vorderseite_max_laenge"


def _admin_und_ziel_url(basis_url: str) -> tuple[str, str, str]:
    """Baut aus TEST_DATABASE_URL eine Wartungs-URL (Datenbank "postgres")
    und eine Ziel-URL fuer eine frische, eindeutig benannte Datenbank auf
    demselben Server, ohne dessen Zugangsdaten anzufassen.
    """
    teile = urlsplit(basis_url)
    datenbankname = f"flashcards_migrationscheck_{uuid.uuid4().hex[:8]}"
    admin_url = teile._replace(path="/postgres").geturl()
    ziel_url = teile._replace(path=f"/{datenbankname}").geturl()
    return admin_url, ziel_url, datenbankname


def _psycopg_dsn(sqlalchemy_url: str) -> str:
    """psycopg.connect() kennt kein "+psycopg"-Dialektsuffix im Schema -
    das ist eine reine SQLAlchemy-Konvention. Fuer eine direkte psycopg-
    Verbindung (Anlegen/Loeschen der Wegwerfdatenbank, Auslesen von
    pg_get_constraintdef) muss das Schema auf das nackte "postgresql"
    zurueckgestutzt werden.
    """
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


def test_alembic_migration_haelt_dieselbe_laengengrenze_wie_markdown():
    """Schliesst die zweite Naht, die tests/conftest.py und "alembic check" offenlassen.

    tests/conftest.py baut das Testschema ausschliesslich aus
    Base.metadata.create_all - also aus app/models.py, nie aus
    migrations/versions/0001_grundmodell.py. Der vorhandene Kopplungstest
    tests/test_models.py::test_markdown_grenze_und_datenbankgrenze_passen_zusammen
    verbindet deshalb nur app/markdown.py mit app/models.py, nicht mit der
    Migration.

    Die zweite Naht sollte "alembic check" in der CI abdecken, tut es aber
    nicht: Nachgemessen wurde, dass eine geaenderte Zahl INNERHALB eines
    CHECK-Constraints nicht erkannt wird, weil das Vergleichs-Plugin
    Constraint-NAMEN vergleicht, nicht deren Ausdruecke. Aendert jemand
    MAX_LAENGE in app/markdown.py und MAX_MARKDOWN_LAENGE in app/models.py,
    vergisst aber migrations/versions/0001_grundmodell.py, bleibt alles
    gruen - und der Betrieb, dessen Schema aus der Migration stammt, behaelt
    stillschweigend die alte Grenze.

    Um wirklich die MIGRATION zu pruefen (nicht nur die Modelle, die schon
    von test_markdown_grenze_und_datenbankgrenze_passen_zusammen abgedeckt
    sind), baut dieser Test eine eigene, eindeutig benannte Wegwerfdatenbank
    auf demselben Server wie TEST_DATABASE_URL, spielt "alembic upgrade
    head" darauf ein und liest die tatsaechlich im Server angekommene
    Grenze aus pg_get_constraintdef() aus - nicht aus dem Migrationstext,
    sondern aus dem, was PostgreSQL daraus gemacht hat. Eine eigene
    Datenbank statt der von conftest.py verwalteten flashcards_test: Die
    dortige Fixture baut ihr Schema aus den Modellen, nicht aus der
    Migration, und wird von keinem anderen Test angefasst waehrend dieser
    hier laeuft.

    Muss in BEIDE Richtungen rot werden: Aendert jemand nur die Zahl in der
    Migration (Konstanten bleiben gleich), weicht die aus der Datenbank
    gelesene Grenze von MAX_LAENGE ab. Aendert jemand nur die Konstanten
    (Migration bleibt gleich), bleibt die aus der Datenbank gelesene Grenze
    bei der alten Zahl, waehrend MAX_LAENGE schon die neue ist - derselbe
    Vergleich schlaegt in beide Richtungen an. Beide Richtungen wurden von
    Hand durchgespielt (Zahl in der Migration geaendert und wieder
    zurueckgenommen; MAX_LAENGE/MAX_MARKDOWN_LAENGE geaendert und wieder
    zurueckgenommen), siehe Report.
    """
    basis_url = os.environ.get("TEST_DATABASE_URL")
    if not basis_url:
        pytest.skip(
            "TEST_DATABASE_URL ist nicht gesetzt. Bitte in der .env eintragen "
            "(siehe .env.example) - siehe tests/conftest.py::test_engine."
        )

    admin_url, ziel_url, datenbankname = _admin_und_ziel_url(basis_url)

    admin_verbindung = psycopg.connect(_psycopg_dsn(admin_url), autocommit=True)
    try:
        admin_verbindung.execute(f'CREATE DATABASE "{datenbankname}"')
    finally:
        admin_verbindung.close()

    try:
        umgebung = dict(os.environ)
        umgebung["DATABASE_URL"] = ziel_url
        umgebung["APP_SECRET"] = "x"
        umgebung["TEACHER_PASSWORD"] = "x"
        umgebung["BASE_URL"] = "http://localhost:8000"

        ergebnis = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJEKTVERZEICHNIS,
            env=umgebung,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert ergebnis.returncode == 0, ergebnis.stdout + ergebnis.stderr

        ziel_verbindung = psycopg.connect(_psycopg_dsn(ziel_url))
        try:
            definition = ziel_verbindung.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = %s",
                (_KONSTRAINT_NAME,),
            ).fetchone()
        finally:
            ziel_verbindung.close()

        assert definition is not None, (
            f"Constraint {_KONSTRAINT_NAME!r} wurde von der Migration nicht angelegt."
        )
        treffer = re.search(r"<=\s*(\d+)", definition[0])
        assert treffer is not None, (
            f"Konnte die Laengengrenze nicht aus {definition[0]!r} lesen."
        )
        laenge_aus_der_migration = int(treffer.group(1))

        assert laenge_aus_der_migration == MAX_LAENGE, (
            f"Die Migration setzt {_KONSTRAINT_NAME} auf "
            f"{laenge_aus_der_migration}, app/markdown.MAX_LAENGE ist aber "
            f"{MAX_LAENGE}. Migration und Anwendungscode sind auseinandergelaufen."
        )
    finally:
        # Eigene Verbindung schliessen (oben bereits geschehen) reicht
        # normalerweise, damit DROP DATABASE nicht an offenen Verbindungen
        # scheitert; WITH (FORCE) faengt zusaetzlich Verbindungen ab, die
        # z.B. durch einen abgebrochenen Testlauf haengen geblieben sein
        # koennten, statt den naechsten Testlauf mit einer Datenbankleiche
        # zu blockieren.
        admin_verbindung = psycopg.connect(_psycopg_dsn(admin_url), autocommit=True)
        try:
            admin_verbindung.execute(
                f'DROP DATABASE IF EXISTS "{datenbankname}" WITH (FORCE)'
            )
        finally:
            admin_verbindung.close()
