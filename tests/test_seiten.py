"""Startseite und Fehlerseiten: Statuscode, Text, Optik-Anbindung, Schreibweise.

Die Lernseite selbst hat ihre eigene Datei (tests/test_lernseite.py); hier
geht es um die drei Seiten, die kein Bundle zeigen.

Zur Datenbank: Die Startseite und die 404-Seite kommen ohne aus und
benutzen deshalb einen eigenen TestClient statt der Fixture "client" - die
haengt an einer echten Testdatenbank. Die 404-Pfade sind mit Bedacht
gewaehlt: Sie passen nicht auf das Adressmuster in app/routen/lernseite.py
und loesen deshalb nie eine Abfrage aus. Nur die 410-Seite braucht ein
inaktives Bundle und damit die Fixtures "klient" und "session".
"""

import html as html_modul
import re
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Bundle
from app.oauth.redirect import CLAUDE_RUECKSPRUNG
from tests.conftest import mit_adresse

STYLESHEET = "/static/lernseite.css"


# ===================== Startseite =====================


def test_startseite_antwortet_mit_200():
    antwort = TestClient(app).get("/")
    assert antwort.status_code == 200


def test_startseite_nennt_den_hinweis_in_korrekter_schreibweise():
    """Der eine Satz, den die Seite tragen soll - mit Umlaut.

    Wortwoertlich geprueft und nicht nur auf "Lehrkraft": Das "ueber"
    ohne Umlaut stand hier monatelang und ist genau der Fehler, den
    dieser Test kuenftig abfangen soll.
    """
    text = TestClient(app).get("/").text
    assert "Diese Seite wird über einen Link aufgerufen" in text
    assert "von deiner Lehrkraft bekommst" in text


def test_startseite_bindet_das_stylesheet_ein():
    """Ohne diese Zeile faellt die Seite auf nacktes HTML zurueck.

    Genau so sah sie aus, bevor sie gestaltet wurde - und ein
    versehentlich entfernter Block "kopf" waere sonst niemandem
    aufgefallen, weil Statuscode und Text unveraendert stimmen.
    """
    assert STYLESHEET in TestClient(app).get("/").text


def test_startseite_steht_auf_der_tafel():
    """Die Klassen, an denen die Optik der Lernseite haengt."""
    text = TestClient(app).get("/").text
    for gruppe in ('class="buehne knapp"', 'class="stapel"', 'class="seite"'):
        assert gruppe in text


def test_startseite_hat_kein_eingabefeld():
    """Ausdrueckliche Entscheidung des Auftraggebers: nur der Hinweis.

    Kein Feld, in das jemand eine Adresse tippt - ein System, das
    bewusst nicht auffindbar sein soll, bietet dafuer keine Tuer an.
    """
    text = TestClient(app).get("/").text
    assert "<input" not in text
    assert "<form" not in text


# ===================== Fehlerseiten =====================

# Beide Pfade passen NICHT auf das Adressmuster (drei Wortgruppen mit
# Bindestrich) und werden deshalb ohne Datenbankabfrage mit 404
# beantwortet - der erste ueber die Route /{slug}, der zweite ueber den
# Ausnahmebehandler in app/main.py.
KEINE_DATENBANK_404 = ["/vertippt", "/ein-zwei-drei/vier"]


@pytest.mark.parametrize("pfad", KEINE_DATENBANK_404)
def test_404_seite_antwortet_mit_404_und_traegt_die_ueberschrift(pfad):
    antwort = TestClient(app).get(pfad)
    assert antwort.status_code == 404
    assert "Diese Lernseite gibt es nicht" in antwort.text


@pytest.mark.parametrize("pfad", KEINE_DATENBANK_404)
def test_404_seite_bindet_das_stylesheet_ein(pfad):
    assert STYLESHEET in TestClient(app).get(pfad).text


def test_404_seite_steht_auf_der_tafel():
    text = TestClient(app).get("/vertippt").text
    for gruppe in ('class="buehne knapp"', 'class="stapel"', 'class="titel"'):
        assert gruppe in text


async def _inaktives_bundle(session, slug="stille-tafel-ruht"):
    bundle = mit_adresse(session, Bundle(slug=slug, titel="Stillgelegt", aktiv=False))
    await session.flush()
    return bundle


async def test_410_seite_antwortet_mit_410_und_traegt_die_ueberschrift(klient, session):
    await _inaktives_bundle(session)
    antwort = await klient.get("/stille-tafel-ruht")
    assert antwort.status_code == 410
    assert "Diese Lernseite ist nicht mehr aktiv" in antwort.text


async def test_410_seite_bindet_das_stylesheet_ein(klient, session):
    await _inaktives_bundle(session)
    antwort = await klient.get("/stille-tafel-ruht")
    assert STYLESHEET in antwort.text
    assert 'class="buehne knapp"' in antwort.text


async def test_die_beiden_fehlerfaelle_haben_verschiedene_ueberschriften(klient, session):
    """Sonst koennte ein Template-Umbau beide Faelle auf denselben Text legen."""
    await _inaktives_bundle(session)
    vierhundertvier = (await klient.get("/gibt-es-nicht")).text
    vierhundertzehn = (await klient.get("/stille-tafel-ruht")).text
    assert "Diese Lernseite gibt es nicht" in vierhundertvier
    assert "Diese Lernseite gibt es nicht" not in vierhundertzehn
    assert "Diese Lernseite ist nicht mehr aktiv" in vierhundertzehn


# ===================== Schreibweise =====================

# Die Projektregel trennt zwei Welten: Bezeichner bleiben ASCII, sichtbarer
# Text steht in korrektem Deutsch. Ein Test, der einfach im Quelltext der
# Templates sucht, kann das nicht unterscheiden - er schluege bei der
# CSS-Klasse "nur-fuer-screenreader", bei der Template-Variablen
# "ueberschrift" und beim Dateinamen "lernseite.css" an. Deshalb wird die
# gerenderte Antwort zuerst auf das reduziert, was ein Mensch im Browser
# liest: Skript- und Stilbloecke raus, alle Tags samt Attributen raus,
# HTML-Entitaeten aufgeloest. Was uebrig bleibt, ist reiner Anzeigetext -
# und darin ist jede dieser Formen ein Rechtschreibfehler.

_SKRIPT_ODER_STIL = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>", re.S)

# Ersatzschreibweisen, die es im Deutschen so nicht gibt. Bewusst eine
# Liste von Wortstaemmen statt einer Suche nach "ae|oe|ue": Woerter wie
# "neue", "Steuer" oder "Museum" traegen diese Buchstabenpaare voellig zu
# Recht, eine solche Suche waere dauerhaft rot.
UMLAUTFEHLER = [
    "ueber", "fuer", "koenn", "muess", "moecht", "waer", "haett", "groess",
    "schoen", "zurueck", "pruef", "gehoer", "oeffn", "waehl", "naechst",
    "moeglich", "gueltig", "laeuft", "spaet", "aender", "erklaer", "rueck",
    "loesch", "loesung", "stueck", "tuer", "fuehr", "bloed", "hoer",
    # "fuege" stand so auf der OAuth-Fehlerseite ("fuege ihn noch einmal
    # hinzu") und wurde von keinem der anderen Staemme erfasst. Achtung,
    # falls einmal ein Werkzeugname im Anzeigetext auftaucht:
    # karten_hinzufuegen ist ein Bezeichner und bleibt ASCII - dann muss
    # nicht der Name geaendert werden, sondern der Satz drumherum.
    "fuege",
]


def seitentext(roh: str) -> str:
    """Aus der HTML-Antwort das machen, was im Browser zu lesen ist."""
    ohne_skript = _SKRIPT_ODER_STIL.sub(" ", roh)
    ohne_tags = _TAG.sub(" ", ohne_skript)
    return html_modul.unescape(ohne_tags)


def umlautfehler_finden(roh: str) -> list[str]:
    text = seitentext(roh).lower()
    return [form for form in UMLAUTFEHLER if form in text]


def test_seitentext_erkennt_einen_fehler_ueberhaupt():
    """Gegenprobe: Ein Pruefer, der nie anschlaegt, prueft nichts.

    Zugleich die Probe darauf, dass die Reduktion auf Anzeigetext das
    Richtige stehen laesst und das Richtige entfernt.
    """
    assert umlautfehler_finden("<p>Diese Seite wird ueber einen Link aufgerufen.</p>") == ["ueber"]


def test_seitentext_schlaegt_nicht_bei_bezeichnern_an():
    """Klassennamen, Variablen und Dateinamen sind Code und bleiben ASCII."""
    quelle = (
        '<link rel="stylesheet" href="/static/lernseite.css">'
        '<p class="nur-fuer-screenreader" id="ueberschrift">Alles gut hier.</p>'
        '<style>.fuer-nichts { color: red; }</style>'
        '<script>const ueberschrift = "x";</script>'
    )
    assert umlautfehler_finden(quelle) == []


@pytest.mark.parametrize("pfad", ["/", "/vertippt", "/ein-zwei-drei/vier"])
def test_sichtbarer_text_ohne_umlautfehler(pfad):
    gefunden = umlautfehler_finden(TestClient(app).get(pfad).text)
    assert gefunden == [], f"{pfad} zeigt Ersatzschreibweisen: {gefunden}"


async def test_sichtbarer_text_der_410_seite_ohne_umlautfehler(klient, session):
    await _inaktives_bundle(session)
    antwort = await klient.get("/stille-tafel-ruht")
    gefunden = umlautfehler_finden(antwort.text)
    assert gefunden == [], f"Die 410-Seite zeigt Ersatzschreibweisen: {gefunden}"


# ===================== Schreibweise der OAuth-Seiten =====================

# Die Zustimmungsseite und die OAuth-Fehlerseite sind die einzigen weiteren
# Seiten, die ein Mensch zu sehen bekommt - die Lehrerin sieht sie genau
# dann, wenn sie den Connector verbindet. Sie laufen deshalb durch denselben
# Pruefer wie Startseite und Fehlerseiten. Beide brauchen die Fixture
# "client" (echte Testdatenbank) und "konfiguration" (feste BASE_URL), weil
# sie einen registrierten Client nachschlagen.

def _client_registrieren(client) -> str:
    antwort = client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_RUECKSPRUNG]},
    )
    return antwort.json()["client_id"]


def _zustimmungsadresse(client_id: str) -> str:
    return (
        "/oauth/authorize?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={quote(CLAUDE_RUECKSPRUNG, safe='')}"
        "&scope=lernseiten&state=abc"
        "&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        "&code_challenge_method=S256"
    )


def test_sichtbarer_text_der_zustimmungsseite_ohne_umlautfehler(client, konfiguration):
    antwort = client.get(_zustimmungsadresse(_client_registrieren(client)))
    assert antwort.status_code == 200
    gefunden = umlautfehler_finden(antwort.text)
    assert gefunden == [], f"Die Zustimmungsseite zeigt Ersatzschreibweisen: {gefunden}"


def test_sichtbarer_text_der_oauth_fehlerseite_ohne_umlautfehler(client, konfiguration):
    """Ein unbekannter Client fuehrt zur Fehlerseite - sie darf nicht weiterleiten."""
    antwort = client.get(_zustimmungsadresse("gibt-es-nicht"))
    assert antwort.status_code == 400
    gefunden = umlautfehler_finden(antwort.text)
    assert gefunden == [], f"Die OAuth-Fehlerseite zeigt Ersatzschreibweisen: {gefunden}"


def test_die_zweite_oauth_fehlerseite_ohne_umlautfehler(client, konfiguration):
    """Registrierter Client, aber fremde Rueckadresse - der zweite Fehlertext."""
    kennung = _client_registrieren(client)
    adresse = _zustimmungsadresse(kennung).replace(
        quote(CLAUDE_RUECKSPRUNG, safe=""), quote("https://boese.example/cb", safe="")
    )
    antwort = client.get(adresse)
    assert antwort.status_code == 400
    gefunden = umlautfehler_finden(antwort.text)
    assert gefunden == [], f"Die OAuth-Fehlerseite zeigt Ersatzschreibweisen: {gefunden}"


# ===================== Urheberzeile =====================

# Sie steht auf allen drei gestalteten Seiten, kommt aus einem einzigen
# Teiltemplate (app/templates/urheber.html) und wurde vom Auftraggeber
# ausdruecklich verlangt. Getestet wird deshalb nicht nur, DASS sie da ist,
# sondern auch die drei Eigenschaften, die still wegbrechen koennen, ohne
# dass eine Seite dabei kaputt aussieht.

URHEBER_SEITEN = ["/", "/vertippt"]


@pytest.mark.parametrize("pfad", URHEBER_SEITEN)
def test_seite_traegt_die_urheberzeile(pfad):
    text = TestClient(app).get(pfad).text
    assert "Bastian Strauss, Varel" in text
    assert "2026" in text
    assert "https://bastianstrauss.digital" in text


@pytest.mark.parametrize("pfad", URHEBER_SEITEN)
def test_urheberzeile_oeffnet_in_einem_neuen_tab(pfad):
    """Sonst verliert ein Kind mitten im Durchlauf seinen Fortschritt.

    Die Lernseite speichert nichts: Wer sie waehrend eines Durchlaufs
    verlaesst, faengt danach von vorn an. Ein versehentlicher Griff auf
    den Verweis darf deshalb nicht im selben Tab landen - und sobald
    target="_blank" gesetzt ist, gehoert rel="noopener" zwingend dazu.
    """
    text = TestClient(app).get(pfad).text
    assert 'target="_blank"' in text
    assert 'rel="noopener noreferrer"' in text


@pytest.mark.parametrize("pfad", URHEBER_SEITEN)
def test_urheberzeile_steht_innerhalb_der_buehne(pfad):
    """Sonst bekommt jede Seite einen Scrollbalken, den sie vorher nicht hatte.

    .buehne ist die Flexspalte mit min-height 100dvh. Ein Element
    dahinter laege unterhalb des Schirms. Das faellt in keinem anderen
    Test auf: Statuscode, Text und Klassen stimmen dann alle noch.
    """
    text = TestClient(app).get(pfad).text
    assert text.rindex('class="urheber"') < text.rindex("</div>")
