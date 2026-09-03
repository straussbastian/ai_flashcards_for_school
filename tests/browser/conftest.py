"""Aufbau der Browsertests: ein echter Server, ein echter Chromium.

Diese Tests sind die einzigen im Projekt, die den Runner
(app/static/runner.js) ueberhaupt ausfuehren. Alles darunter - Route,
Bundle-JSON, Markdown-Saeuberung - ist bereits durch pytest abgedeckt;
hier geht es ausschliesslich um das, was danach im Browser passiert.

Warum ein eigener Server statt des TestClient: Der Runner laeuft in einem
Browser, und der braucht eine Adresse, die er aufrufen kann. Ein
ASGI-Transport im selben Prozess hat keine.

Warum die Markierung "browser" (siehe pyproject.toml): Diese Tests
brauchen einen installierten Chromium und einen laufenden Uvicorn. Ein
gewoehnlicher "pytest"-Lauf waehlt sie deshalb nicht aus. Sie sind damit
"deselected", nicht "skipped" - die Projektregel "0 uebersprungen" bleibt
woertlich erfuellt, und ein frischer Checkout bleibt gruen.

Ausfuehren: gar nicht von Hand. Das Testabbild bringt den Chromium mit
(Dockerfile, Stufe "test"), und docker/test-start.sh ruft nach dem
gewoehnlichen Durchgang ausdruecklich "pytest -m browser" auf:

    docker compose -f compose.test.yml up --build \
        --abort-on-container-exit --exit-code-from test

Nur diese eine Auswahl, ohne den ersten Durchgang:

    docker compose -f compose.test.yml run --rm test -m browser
"""

import os
import random
import socket
import string
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from app import models  # noqa: F401 -- registriert die Tabellen bei Base.metadata
from app.db import Base
from app.models import Bundle, Karte
from app.oauth import modelle as oauth_modelle  # noqa: F401 -- desgleichen

HIER = Path(__file__).parent
WURZEL = HIER.parent.parent

# Zeitgrenzen. Jeder Unterprozessaufruf bekommt eine; ein haengender
# Uvicorn soll den Lauf nicht bis zum Jobtimeout blockieren.
START_FRIST = 40.0      # Sekunden bis /healthz antwortet
STOPP_FRIST = 10.0      # Sekunden fuer das geordnete Beenden
WARTE_FRIST = 3.0       # Sekunden, die ein Zustandswechsel im Browser dauern darf


def pytest_collection_modifyitems(config, items):
    """Markiert alles unter tests/browser automatisch als "browser".

    Statt in jeder Datei ein pytestmark zu pflegen: Wer hier eine neue
    Testdatei anlegt, bekommt die Markierung, ohne daran zu denken - und
    kann sie damit auch nicht vergessen.
    """
    for item in items:
        if HIER in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.browser)


# ====================== Server ======================


def _freier_port() -> int:
    """Einen freien Port vom Betriebssystem erfragen.

    Ausdruecklich nicht 8000: Dort laeuft der Betriebscontainer
    (compose.yml). Ein fester Port haette die Tests gegen dessen
    Datenbank laufen lassen, nicht gegen die Testdatenbank - gruen
    vielleicht, aber ueber etwas ganz anderem.
    """
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _warten_auf_healthz(basis: str, prozess: subprocess.Popen, protokoll: Path) -> None:
    """Auf die Bereitschaft warten, statt blind zu schlafen.

    Ein festes sleep ist die haeufigste Ursache fuer sporadisch rote
    Laeufe: Auf einem ausgelasteten Rechner ist es zu kurz, auf einem
    schnellen verschenkt es Zeit. /healthz prueft ausserdem die
    Datenbankverbindung mit - genau die brauchen die Tests.
    """
    ende = time.monotonic() + START_FRIST
    letzter_fehler = ""
    while time.monotonic() < ende:
        if prozess.poll() is not None:
            raise RuntimeError(
                f"Der Server ist beim Start beendet worden (Code {prozess.returncode}).\n"
                f"Ausgabe:\n{protokoll.read_text(errors='replace')}"
            )
        try:
            with urllib.request.urlopen(f"{basis}/healthz", timeout=2) as antwort:
                if antwort.status == 200:
                    return
                letzter_fehler = f"HTTP {antwort.status}"
        except (urllib.error.URLError, OSError) as fehler:
            letzter_fehler = repr(fehler)
        time.sleep(0.1)
    raise RuntimeError(
        f"/healthz hat binnen {START_FRIST} Sekunden nicht geantwortet "
        f"(zuletzt: {letzter_fehler}).\nAusgabe:\n{protokoll.read_text(errors='replace')}"
    )


@pytest.fixture(scope="session")
def datenbank_url() -> str:
    """Die Testdatenbank. Fehlt sie, ist das hier ein Fehler und kein Skip.

    Anders als in tests/conftest.py: Dort werden Tests uebersprungen, die
    zufaellig eine Datenbank brauchen. Hier hat jemand ausdruecklich
    "-m browser" getippt - dann ist ein stiller Skip die falsche Antwort.
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail(
            "TEST_DATABASE_URL ist nicht gesetzt. Die Browsertests laufen im "
            "Testcontainer, der die Variable selbst mitbringt:\n"
            "  docker compose -f compose.test.yml run --rm test -m browser"
        )
    return url


@pytest.fixture(scope="session")
def motor(datenbank_url: str):
    """Eine synchrone Engine auf die Testdatenbank, nur zum Anlegen der Bundles.

    Synchron und nicht ueber die Async-Engine der Anwendung: Diese Tests
    sind synchron (die Playwright-Sync-API vertraegt keinen laufenden
    Event-Loop), und der Server hat ohnehin seine eigene Verbindung.
    """
    engine = create_engine(datenbank_url, future=True)
    # checkfirst ist Standard: Vorhandene Tabellen bleiben unberuehrt.
    # Ein drop_all waere hier falsch - tests/conftest.py macht das fuer
    # seine eigene Sitzung, und zwei Stellen, die dieselbe Datenbank
    # leerraeumen, kommen einander in die Quere.
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def server(datenbank_url: str, motor) -> str:
    """Startet Uvicorn gegen die Testdatenbank und gibt die Basis-URL zurueck."""
    port = _freier_port()
    basis = f"http://127.0.0.1:{port}"

    umgebung = dict(os.environ)
    umgebung.update({
        # Der Server bekommt die TESTdatenbank als DATABASE_URL. Ohne das
        # liefe er gegen die Entwicklungsdatenbank und die Tests saehen
        # ihre eigenen Bundles nicht.
        "DATABASE_URL": datenbank_url,
        # Feste Wegwerfwerte, damit der Start nicht davon abhaengt, was
        # gerade in der .env steht (in der CI gibt es keine).
        "APP_SECRET": "browsertest-wegwerf-schluessel",
        "TEACHER_PASSWORD": "browsertest-wegwerf-passwort",
        "BASE_URL": basis,
    })

    with tempfile.TemporaryDirectory() as ordner:
        protokoll = Path(ordner) / "uvicorn.log"
        # In eine Datei und nicht in eine Pipe: Eine volle Pipe, die
        # niemand liest, laesst den Server blockieren.
        with protokoll.open("wb") as ausgabe:
            prozess = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=str(WURZEL), env=umgebung, stdout=ausgabe, stderr=subprocess.STDOUT,
            )
            try:
                _warten_auf_healthz(basis, prozess, protokoll)
                yield basis
            finally:
                prozess.terminate()
                try:
                    prozess.wait(timeout=STOPP_FRIST)
                except subprocess.TimeoutExpired:
                    prozess.kill()
                    prozess.wait(timeout=STOPP_FRIST)


# ====================== Bundles ======================


def _zufallsslug() -> str:
    """Eine Adresse in der Form, die app/routen/lernseite.py durchlaesst."""
    wort = lambda: "".join(random.choices(string.ascii_lowercase, k=8))  # noqa: E731
    return f"{wort()}-{wort()}-{wort()}"


def flashcard(vorderseite: str, rueckseite: str) -> dict:
    """Eine Lernkarte im Eingabeformat der Fixture "bundle"."""
    return {"art": "flashcard", "vorderseite": vorderseite, "rueckseite": rueckseite}


def frage(vorderseite: str, antworten: list[str], richtige_index: int,
          erklaerung: str = "") -> dict:
    """Eine Frage im Eingabeformat der Fixture "bundle"."""
    return {"art": "frage", "vorderseite": vorderseite, "antworten": antworten,
            "richtige_index": richtige_index, "erklaerung": erklaerung}


@pytest.fixture
def bundle(motor, server: str):
    """Legt Bundles an und raeumt sie danach wieder ab.

    Gibt eine Funktion zurueck, die die fertige URL liefert. Jedes Bundle
    bekommt eine zufaellige Adresse, damit zwei Tests einander nicht ins
    Gehege kommen.
    """
    angelegt: list[str] = []

    def anlegen(karten: list[dict], titel: str = "Arbeitsrecht kompakt",
                beschreibung: str = "", gruppe: str = "",
                selbsteinschaetzung: bool = True, reihenfolge: str = "zufall",
                aktiv: bool = True, karten_pro_durchlauf: int | None = None) -> str:
        slug = _zufallsslug()
        with Session(motor) as sitzung:
            eintrag = Bundle(
                slug=slug, titel=titel, beschreibung=beschreibung or None,
                gruppe=gruppe or None, selbsteinschaetzung=selbsteinschaetzung,
                reihenfolge=reihenfolge, aktiv=aktiv,
                karten_pro_durchlauf=karten_pro_durchlauf,
            )
            sitzung.add(eintrag)
            sitzung.flush()
            for nummer, karte in enumerate(karten, start=1):
                sitzung.add(Karte(
                    bundle_id=eintrag.id, position=nummer, art=karte["art"],
                    vorderseite=karte["vorderseite"],
                    rueckseite=karte.get("rueckseite") or None,
                    antworten=karte.get("antworten"),
                    richtige_index=karte.get("richtige_index"),
                    erklaerung=karte.get("erklaerung") or None,
                ))
            sitzung.commit()
        angelegt.append(slug)
        return f"{server}/{slug}"

    yield anlegen

    with Session(motor) as sitzung:
        ids = sitzung.scalars(select(Bundle.id).where(Bundle.slug.in_(angelegt))).all()
        if ids:
            sitzung.execute(delete(Karte).where(Karte.bundle_id.in_(ids)))
            sitzung.execute(delete(Bundle).where(Bundle.id.in_(ids)))
            sitzung.commit()


# ====================== Browser ======================


@pytest.fixture(scope="session")
def browser():
    """Ein Chromium fuer die ganze Sitzung. Der Start kostet Zeit, der Kontext nicht."""
    with sync_playwright() as p:
        instanz = p.chromium.launch()
        yield instanz
        instanz.close()


@pytest.fixture
def meldungen() -> dict[str, list[str]]:
    """Sammelbecken fuer Konsolenausgaben und unbehandelte Ausnahmen der Seite."""
    return {"konsole": [], "fehler": []}


@pytest.fixture
def seite(browser, meldungen: dict[str, list[str]]):
    """Eine frische Seite am Rechner-Viewport.

    Am Ende jedes Tests wird geprueft, dass der Runner keine unbehandelte
    Ausnahme geworfen hat. Konsolenausgaben werden nur gesammelt: Der
    Browser meldet dort auch Dinge, die nicht dem Runner gehoeren (etwa
    das von der Inhaltsrichtlinie geblockte Favicon).
    """
    kontext = browser.new_context(viewport={"width": 1280, "height": 900})
    blatt = kontext.new_page()
    blatt.on("console", lambda m: meldungen["konsole"].append(f"{m.type}: {m.text}"))
    blatt.on("pageerror", lambda f: meldungen["fehler"].append(str(f)))
    yield blatt
    kontext.close()
    assert meldungen["fehler"] == [], (
        f"Der Runner hat eine unbehandelte Ausnahme geworfen: {meldungen['fehler']}"
    )


@pytest.fixture
def seite_ohne_drehung(browser, meldungen: dict[str, list[str]]):
    """Wie "seite", nur mit prefers-reduced-motion.

    Die Spec sieht das ausdruecklich vor: "Bei prefers-reduced-motion:
    reduce entfaellt die Drehung, die Rueckseite erscheint direkt." Fuer
    den Leistentest, der viele hundert Zustandswechsel durchgeht, ist das
    ausserdem der Unterschied zwischen einer und mehreren Minuten.
    """
    kontext = browser.new_context(viewport={"width": 1280, "height": 900},
                                  reduced_motion="reduce")
    blatt = kontext.new_page()
    blatt.on("console", lambda m: meldungen["konsole"].append(f"{m.type}: {m.text}"))
    blatt.on("pageerror", lambda f: meldungen["fehler"].append(str(f)))
    yield blatt
    kontext.close()
    assert meldungen["fehler"] == [], (
        f"Der Runner hat eine unbehandelte Ausnahme geworfen: {meldungen['fehler']}"
    )


@pytest.fixture
def handy(browser, meldungen: dict[str, list[str]]):
    """Dasselbe am Handy-Viewport (390 px, die Breite aus der Spec)."""
    kontext = browser.new_context(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True)
    blatt = kontext.new_page()
    blatt.on("console", lambda m: meldungen["konsole"].append(f"{m.type}: {m.text}"))
    blatt.on("pageerror", lambda f: meldungen["fehler"].append(str(f)))
    yield blatt
    kontext.close()
    assert meldungen["fehler"] == [], (
        f"Der Runner hat eine unbehandelte Ausnahme geworfen: {meldungen['fehler']}"
    )


# ====================== Gemeinsame Handgriffe ======================
#
# Alles hier drin beschreibt, was eine Lernende sieht und tut - keine
# Klassennamen, keine Knotenreihenfolge. Die IDs stammen aus dem
# Template (app/templates/lernseite.html) und sind dessen oeffentliche
# Schnittstelle an den Runner; sie zu benutzen ist etwas anderes, als
# sich an eine Formatierungsklasse zu haengen.

# Die Uebersetzung von dem, was in der Tastenleiste steht, auf das, was
# man tatsaechlich drueckt. Steht in der Leiste ein Wort, das hier fehlt,
# schlaegt der Leistentest ausdruecklich fehl statt es zu ueberspringen -
# so zieht er bei einer neuen Taste mit, statt sie stillschweigend
# auszulassen.
TASTENNAMEN = {
    "Eingabetaste": "Enter",
    "Leertaste": " ",
    "Esc": "Escape",
    "→": "ArrowRight",
    "←": "ArrowLeft",
    "A": "a", "B": "b", "C": "c", "D": "d",
}


def leiste(blatt: Page) -> str:
    """Der Text der Tastenleiste."""
    return blatt.locator("#tastenleiste").inner_text().strip()


def leistentasten(blatt: Page) -> list[str]:
    """Die Tasten, die die Leiste gerade nennt - als Beschriftung, nicht uebersetzt.

    Ein Eintrag beginnt mit seinen Tasten und endet mit dem, was sie tun
    ("A B C D waehlen", "Leertaste umdrehen"). Genommen wird alles bis zum
    ersten Wort, das keine Taste ist.
    """
    tasten = []
    for eintrag in leiste(blatt).split("·"):
        woerter = eintrag.split()
        if not woerter:
            continue
        # Kein stilles Ueberspringen: Nennt die Leiste eine Taste, die
        # dieser Test nicht kennt, soll er darueber stolpern und nicht
        # so tun, als gaebe es sie nicht. Nur so zieht der Leistentest
        # mit, wenn jemand eine neue Taste einbaut.
        assert woerter[0] in TASTENNAMEN, (
            f"Die Tastenleiste nennt {woerter[0]!r}. Diese Taste kennt der Test nicht - "
            f"traeg sie in TASTENNAMEN (tests/browser/conftest.py) ein, damit sie "
            f"mitgeprueft wird. Ganze Leiste: {leiste(blatt)!r}"
        )
        for wort in woerter:
            if wort in TASTENNAMEN:
                tasten.append(wort)
            else:
                break
    return tasten


# Ein Knopf zaehlt als erreichbar, wenn ein Klick auf seine Mitte auch
# auf ihm landet. Das ist absichtlich schaerfer als "sichtbar": Die
# Rueckseite der Karte liegt deckungsgleich ueber der Vorderseite und ist
# weggedreht - sie hat eine Groesse, ist aber nicht zu treffen.
_JS_KNOEPFE = """
  const erreichbar = [];
  for (const b of document.querySelectorAll('button')) {
    if (b.disabled) continue;
    const r = b.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const el = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!el || !b.contains(el)) continue;
    erreichbar.push(b.innerText.trim());
  }
"""

# Ein Abbild dessen, was gerade zu sehen ist - in EINEM Aufruf, weil
# darauf gewartet wird und jede Runde ueber die Browserbruecke Zeit
# kostet. Die Beschriftungen werden sortiert, weil die Antworten bei
# jedem Durchlauf neu gemischt werden: Ihre Reihenfolge ist kein
# Unterschied im Zustand. Der Fortschritt zaehlt nur, solange die
# Kopfzeile zu sehen ist - sie behaelt ihren letzten Text, wenn der
# Runner zur Startseite zurueckgeht.
JS_ABDRUCK = r"""() => {
  const kopf = document.getElementById('kopf').hidden
    ? '' : document.getElementById('fortschritt-text').innerText;
  const leiste = document.getElementById('tastenleiste').innerText;
  const inhalt = document.getElementById('karte-innen').innerText;
  %s
  erreichbar.sort();
  return [kopf.trim(), leiste.trim(), inhalt.trim(), erreichbar.join(' | ')].join('\n--\n');
}""" % _JS_KNOEPFE


def knoepfe(blatt: Page) -> list[str]:
    """Die Beschriftungen aller Knoepfe, die man tatsaechlich anklicken kann."""
    return blatt.evaluate("() => { %s return erreichbar; }" % _JS_KNOEPFE)


def sichtbare_seite(blatt: Page) -> str:
    """Der Text der Kartenseite, die die Lernende tatsaechlich vor sich hat.

    Vorder- und Rueckseite liegen deckungsgleich uebereinander; im Baum
    stehen immer beide. Welche zu sehen ist, entscheidet die Drehung -
    und damit das, was ein Klick in die Mitte der Karte treffen wuerde.
    Mehrere Punkte, weil die Mitte der Karte auch einmal leer sein kann.
    """
    return blatt.evaluate("""() => {
      const karte = document.getElementById('karte').getBoundingClientRect();
      for (const [fx, fy] of [[.5,.5],[.5,.2],[.5,.8],[.25,.5],[.75,.5]]) {
        let el = document.elementFromPoint(karte.left + karte.width * fx,
                                           karte.top + karte.height * fy);
        while (el && el.parentElement && el.parentElement.id !== 'karte-innen') {
          el = el.parentElement;
        }
        if (el && el.parentElement && el.parentElement.id === 'karte-innen') {
          return el.innerText.trim();
        }
      }
      return '';
    }""")


def abdruck(blatt: Page) -> str:
    """Siehe JS_ABDRUCK."""
    return blatt.evaluate(JS_ABDRUCK)


def druecken(blatt: Page, taste: str) -> None:
    """Eine Taste druecken, so wie sie in der Leiste steht."""
    blatt.keyboard.press(TASTENNAMEN.get(taste, taste))


def warten_bis_anders(blatt: Page, vorher: str) -> bool:
    """Wartet, bis sich der Abdruck aendert. Gibt zurueck, ob er sich geaendert hat.

    Der Runner arbeitet mit Fristen (300 ms bis der Fokus wandert, 350 ms
    bis die Selbsteinschaetzung weiterblaettert) und einer Drehung von
    550 ms. Gewartet wird darauf, dass etwas anders ist, statt fest zu
    schlafen: Ein festes sleep waere entweder zu kurz oder verschenkte
    bei jedem Tastendruck Zeit. Geprueft wird im Browser selbst, damit
    das Warten nicht aus lauter Einzelaufrufen besteht.
    """
    try:
        blatt.wait_for_function(
            "(vorher) => (%s)() !== vorher" % JS_ABDRUCK,
            arg=vorher, timeout=WARTE_FRIST * 1000,
        )
        return True
    except PlaywrightTimeoutError:
        return False


def ruhig_bleiben(blatt: Page, vorher: str) -> bool:
    """Gegenstueck zu warten_bis_anders: Nichts darf sich aendern."""
    ende = time.monotonic() + 0.8
    while time.monotonic() < ende:
        if abdruck(blatt) != vorher:
            return False
        blatt.wait_for_timeout(50)
    return True


def ruhe_abwarten(blatt: Page) -> None:
    """Wartet, bis die Drehung der Karte zu Ende ist.

    Waehrend der Drehung (0,55 s) liegt die Rueckseite schraeg im Raum:
    Ein Klick in die Kartenmitte trifft noch die Vorderseite, und
    gemessene Rechtecke sind unbrauchbar. Gewartet wird auf den
    Stillstand der Verwandlung und nicht auf eine feste Zeit - unter
    prefers-reduced-motion faellt die Drehung ganz weg, dann ist es
    sofort so weit.
    """
    letzte, gleich, ende = None, 0, time.monotonic() + WARTE_FRIST + 2
    while time.monotonic() < ende:
        jetzt = blatt.evaluate(
            "() => getComputedStyle(document.getElementById('karte-innen')).transform"
        )
        gleich = gleich + 1 if jetzt == letzte else 0
        letzte = jetzt
        if gleich >= 2:
            return
        blatt.wait_for_timeout(25)
    raise AssertionError("Die Karte kommt nicht zur Ruhe.")


def umblaettern(blatt: Page, taste: str) -> None:
    """Eine Taste druecken und abwarten, bis der neue Zustand steht."""
    vorher = abdruck(blatt)
    druecken(blatt, taste)
    assert warten_bis_anders(blatt, vorher), (
        f"Die Taste {taste!r} hat nichts bewirkt. Zustand: {vorher!r}"
    )
    ruhe_abwarten(blatt)


def laden(blatt: Page, url: str) -> None:
    """Die Lernseite aufrufen und abwarten, bis der Runner gezeichnet hat.

    Gewartet wird auf einen Inhalt in der Karte und nicht auf die
    Tastenleiste: Die ist am Handy ausgeblendet, dort wartete man ewig.
    """
    blatt.goto(url)
    blatt.wait_for_selector("#karte-innen > *", state="attached")


def starten(blatt: Page, url: str) -> None:
    """Seite laden und den Durchlauf mit der Eingabetaste beginnen."""
    laden(blatt, url)
    vorher = abdruck(blatt)
    blatt.keyboard.press("Enter")
    assert warten_bis_anders(blatt, vorher), "Die Eingabetaste hat den Durchlauf nicht gestartet."
