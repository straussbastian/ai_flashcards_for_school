"""Tests fuer die Werkzeuge rund um Bundles.

Aufgerufen wird ueber MCPServer.call_tool() und nicht ueber HTTP: So wird
genau das geprueft, was der Agent zu sehen bekommt (Schema, Ergebnis,
Fehlertext), ohne dass fuer jeden Fall ein Handschlag noetig waere. Der Weg
ueber HTTP wird in tests/test_mcp_ende_zu_ende.py einmal vollstaendig
gegangen.
"""

import json

import pytest
from sqlalchemy import select

from app.mcp import mcp_bauen
from app.models import Bundle
from tests.conftest import TEST_BASIS_URL

FLASHCARD = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlungsschicht"}
FRAGE = {
    "art": "frage",
    "vorderseite": "Was ist die Hauptstadt von Kroatien?",
    "antworten": ["Split", "Zagreb", "Dubrovnik", "Rijeka"],
    "richtige_antwort": "Zagreb",
    "erklaerung": "Zagreb liegt im Landesinneren.",
}


async def _aufrufen(name: str, **argumente) -> dict:
    """Ruft ein Werkzeug auf und gibt sein Ergebnis als Dict zurueck."""
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is False, ergebnis.content[0].text
    return json.loads(ergebnis.content[0].text)


async def _fehlertext(name: str, **argumente) -> str:
    """Ruft ein Werkzeug auf, das scheitern soll, und gibt den Text zurueck.

    MCPServer.call_tool() wirft den ToolError weiter, statt ihn als Ergebnis
    mit is_error zurueckzugeben - das uebernimmt erst die Protokollschicht
    darueber, die dem Client daraus ein isError: true macht (siehe E-7 im
    Plan). Geprueft wird deshalb beides: der geworfene Fehler und, falls das
    SDK das eines Tages aendert, das Ergebnis mit is_error.
    """
    from mcp.server.mcpserver.exceptions import ToolError

    server, _ = mcp_bauen()
    try:
        ergebnis = await server.call_tool(name, argumente)
    except ToolError as fehler:
        return str(fehler)
    assert ergebnis.is_error is True
    return ergebnis.content[0].text


@pytest.fixture(autouse=True)
def frischer_server():
    """Baut den Server pro Test neu, damit kein Zustand mitwandert."""
    mcp_bauen.cache_clear()
    yield
    mcp_bauen.cache_clear()


async def test_anlegen_liefert_slug_url_und_anzahl(konfiguration, mcp_sitzung):
    daten = await _aufrufen(
        "bundle_anlegen",
        titel="Netzwerkgrundlagen",
        klasse="FS 23b",
        karten=[FLASHCARD, FRAGE],
    )
    assert daten["slug"].count("-") == 2
    assert daten["url"] == f"{TEST_BASIS_URL}/{daten['slug']}"
    assert daten["anzahl_karten"] == 2
    assert daten["titel"] == "Netzwerkgrundlagen"


async def test_die_karten_landen_richtig_in_der_datenbank(konfiguration, mcp_sitzung):
    daten = await _aufrufen("bundle_anlegen", titel="T", karten=[FRAGE, FLASHCARD])
    bundle = await mcp_sitzung.scalar(select(Bundle).where(Bundle.slug == daten["slug"]))
    karten = sorted(bundle.karten, key=lambda k: k.position)
    assert [k.position for k in karten] == [0, 1]
    assert karten[0].art == "frage"
    assert karten[0].richtige_index == 1
    assert karten[0].rueckseite is None
    assert karten[1].art == "flashcard"
    assert karten[1].antworten is None


async def test_anlegen_ohne_karten_wird_abgelehnt(konfiguration, mcp_sitzung):
    text = await _fehlertext("bundle_anlegen", titel="Leer", karten=[])
    assert "keine Karten" in text
    assert "mindestens eine" in text


async def test_eine_kaputte_karte_verhindert_das_ganze_bundle(konfiguration, mcp_sitzung):
    """Alles oder nichts: Ein halb angelegtes Lernpaket waere schlimmer als
    keines, weil niemand sieht, was fehlt."""
    kaputt = {**FRAGE, "richtige_antwort": "Ljubljana"}
    text = await _fehlertext("bundle_anlegen", titel="T", karten=[FLASHCARD, kaputt])
    assert "Position 2" in text
    anzahl = len((await mcp_sitzung.scalars(select(Bundle))).all())
    assert anzahl == 0


async def test_ein_belegter_slug_wird_neu_gewuerfelt(konfiguration, mcp_sitzung, monkeypatch):
    """Der Wettlauf aus Spec, Abschnitt 4.

    freien_slug_finden() prueft und schreibt nicht atomar: Zwischen "ist
    frei" und "ist eingetragen" kann ein zweiter Aufruf denselben Kandidaten
    ziehen. Aufgefangen wird das vom Unique-Constraint - und das Anlegen muss
    daraufhin NEU WUERFELN statt der Lehrerin einen IntegrityError
    vorzulegen.

    Nachgestellt wird der Wettlauf, indem freien_slug_finden zuerst einen
    Slug liefert, der schon vergeben ist.
    """
    from app.mcp import dienste

    mcp_sitzung.add(Bundle(slug="schon-vergeben-adresse", titel="Da"))
    await mcp_sitzung.flush()

    kandidaten = iter(["schon-vergeben-adresse", "frisch-gewuerfelte-adresse"])

    async def gefaelscht(sitzung, versuche=10):
        return next(kandidaten)

    monkeypatch.setattr(dienste, "freien_slug_finden", gefaelscht)

    daten = await _aufrufen("bundle_anlegen", titel="Zweites", karten=[FLASHCARD])
    assert daten["slug"] == "frisch-gewuerfelte-adresse"


async def test_wenn_gar_nichts_frei_ist_kommt_eine_klartextmeldung(
    konfiguration, mcp_sitzung, monkeypatch
):
    from app.mcp import dienste

    mcp_sitzung.add(Bundle(slug="immer-dieselbe-adresse", titel="Da"))
    await mcp_sitzung.flush()

    async def immer_dieselbe(sitzung, versuche=10):
        return "immer-dieselbe-adresse"

    monkeypatch.setattr(dienste, "freien_slug_finden", immer_dieselbe)

    text = await _fehlertext("bundle_anlegen", titel="Dritte", karten=[FLASHCARD])
    assert "keine freie" in text.lower()
    assert "noch einmal" in text


async def test_liste_zeigt_slug_url_und_kartenzahl(konfiguration, mcp_sitzung):
    await _aufrufen("bundle_anlegen", titel="Eins", klasse="FS 23b", karten=[FLASHCARD])
    await _aufrufen("bundle_anlegen", titel="Zwei", klasse="EL 24a", karten=[FRAGE, FLASHCARD])

    daten = await _aufrufen("bundle_liste")
    assert daten["anzahl"] == 2
    nach_titel = {eintrag["titel"]: eintrag for eintrag in daten["bundles"]}
    assert nach_titel["Zwei"]["anzahl_karten"] == 2
    assert nach_titel["Eins"]["klasse"] == "FS 23b"
    assert nach_titel["Eins"]["url"].startswith(TEST_BASIS_URL)
    assert nach_titel["Eins"]["aktiv"] is True


async def test_liste_laesst_sich_nach_klasse_filtern(konfiguration, mcp_sitzung):
    await _aufrufen("bundle_anlegen", titel="Eins", klasse="FS 23b", karten=[FLASHCARD])
    await _aufrufen("bundle_anlegen", titel="Zwei", klasse="EL 24a", karten=[FLASHCARD])

    daten = await _aufrufen("bundle_liste", klasse="FS 23b")
    assert [eintrag["titel"] for eintrag in daten["bundles"]] == ["Eins"]


async def test_leere_liste_ist_kein_fehler(konfiguration, mcp_sitzung):
    daten = await _aufrufen("bundle_liste")
    assert daten["anzahl"] == 0
    assert daten["bundles"] == []


async def test_anzeigen_liefert_karten_mit_ids_und_positionen(konfiguration, mcp_sitzung):
    angelegt = await _aufrufen("bundle_anlegen", titel="T", karten=[FRAGE, FLASHCARD])
    daten = await _aufrufen("bundle_anzeigen", slug=angelegt["slug"])

    assert daten["titel"] == "T"
    assert len(daten["karten"]) == 2
    erste = daten["karten"][0]
    assert erste["position"] == 0
    assert len(erste["karte_id"]) == 36
    assert erste["art"] == "frage"
    # Zurueck als TEXT, nicht als Index: So kann der Agent die Karte
    # unveraendert wieder an karte_aendern uebergeben.
    assert erste["richtige_antwort"] == "Zagreb"
    assert erste["antworten"] == ["Split", "Zagreb", "Dubrovnik", "Rijeka"]


async def test_unbekannter_slug_nennt_das_werkzeug_zum_nachsehen(konfiguration, mcp_sitzung):
    """Die Meldung steht so in der Spec, Abschnitt 5."""
    text = await _fehlertext("bundle_anzeigen", slug="rote-katze-springt")
    assert "rote-katze-springt" in text
    assert "bundle_liste" in text


async def test_die_beschreibung_der_werkzeuge_warnt_vor_keine_der_genannten(konfiguration):
    """Die Spec verlangt diesen Hinweis ausdruecklich in der
    Werkzeugbeschreibung, weil die Reihenfolge gemischt wird."""
    server, _ = mcp_bauen()
    werkzeuge = {eines.name: eines for eines in await server.list_tools()}
    schema = json.dumps(werkzeuge["bundle_anlegen"].input_schema, ensure_ascii=False)
    assert "keine der genannten" in schema
    assert "A und B sind richtig" in schema


async def test_alle_acht_werkzeuge_sind_da(konfiguration):
    """Wird spaeter durch Task 11 und 12 vervollstaendigt - hier stehen erst drei."""
    server, _ = mcp_bauen()
    namen = {eines.name for eines in await server.list_tools()}
    assert {"bundle_anlegen", "bundle_liste", "bundle_anzeigen"} <= namen
