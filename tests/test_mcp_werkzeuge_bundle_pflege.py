"""Tests fuer bundle_aendern und bundle_deaktivieren.

Massstab ist Abschnitt 5 der Spec. Zwei Saetze daraus tragen diese Datei:

    "bundle_aendern | slug, optional titel, beschreibung, klasse,
     selbsteinschaetzung, reihenfolge | aktualisiertes Bundle"

    "Kein endgueltiges Loeschen ueber MCP. bundle_deaktivieren setzt
     aktiv = false; die Seite zeigt dann einen freundlichen Hinweis. Ein
     Versehen ist damit ein Handgriff, kein Datenverlust."

Der zweite ist der wichtigere: Dass ueber MCP nichts endgueltig verschwindet,
ist eine Zusage an die Lehrerin und keine Implementierungsfrage.
"""

import json

import pytest

from app.mcp import mcp_bauen
from tests.conftest import TEST_BASIS_URL

FLASHCARD = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlungsschicht"}


async def _aufrufen(name: str, **argumente) -> dict:
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is False, ergebnis.content[0].text
    return json.loads(ergebnis.content[0].text)


async def _fehlertext(name: str, **argumente) -> str:
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
    mcp_bauen.cache_clear()
    yield
    mcp_bauen.cache_clear()


async def _paket(**abweichungen) -> dict:
    felder = {"titel": "Netzwerkgrundlagen", "karten": [FLASHCARD]}
    felder.update(abweichungen)
    return await _aufrufen("bundle_anlegen", **felder)


# ===================== bundle_aendern =====================


async def test_aendern_ersetzt_nur_das_angegebene_feld(konfiguration, mcp_sitzung):
    paket = await _paket(klasse="FS 23b")
    geaendert = await _aufrufen("bundle_aendern", slug=paket["slug"], titel="Netzwerke II")
    assert geaendert["titel"] == "Netzwerke II"
    assert geaendert["klasse"] == "FS 23b"
    assert geaendert["url"] == f"{TEST_BASIS_URL}/{paket['slug']}"


async def test_die_adresse_aendert_sich_nie_mit(konfiguration, mcp_sitzung):
    """Der Link ist weitergegeben worden - er darf sich nicht unter den
    Lernenden wegbewegen, nur weil die Lehrerin den Titel korrigiert."""
    paket = await _paket()
    geaendert = await _aufrufen("bundle_aendern", slug=paket["slug"], titel="Ganz anders")
    assert geaendert["slug"] == paket["slug"]


async def test_alle_felder_lassen_sich_aendern(konfiguration, mcp_sitzung):
    paket = await _paket()
    geaendert = await _aufrufen(
        "bundle_aendern",
        slug=paket["slug"],
        titel="Netzwerke II",
        beschreibung="Zweiter Durchgang",
        klasse="FS 24a",
        selbsteinschaetzung=False,
        reihenfolge="fest",
    )
    assert geaendert["titel"] == "Netzwerke II"
    assert geaendert["beschreibung"] == "Zweiter Durchgang"
    assert geaendert["klasse"] == "FS 24a"
    assert geaendert["selbsteinschaetzung"] is False
    assert geaendert["reihenfolge"] == "fest"


async def test_die_kartenzahl_steht_auch_in_der_antwort(konfiguration, mcp_sitzung):
    paket = await _paket(karten=[FLASHCARD, {**FLASHCARD, "vorderseite": "MTU"}])
    geaendert = await _aufrufen("bundle_aendern", slug=paket["slug"], titel="Neu")
    assert geaendert["anzahl_karten"] == 2


async def test_unbekannte_reihenfolge_wird_im_klartext_abgelehnt(konfiguration, mcp_sitzung):
    """Die Datenbank haette ck_bundles_reihenfolge - aber ihre Meldung
    besteht aus einem Constraint-Namen, und den soll niemand vorgelesen
    bekommen."""
    paket = await _paket()
    text = await _fehlertext("bundle_aendern", slug=paket["slug"], reihenfolge="rueckwaerts")
    assert "zufall" in text
    assert "fest" in text


async def test_leerer_titel_wird_abgelehnt(konfiguration, mcp_sitzung):
    paket = await _paket()
    text = await _fehlertext("bundle_aendern", slug=paket["slug"], titel="   ")
    assert "Titel" in text


async def test_zu_langer_titel_wird_abgelehnt(konfiguration, mcp_sitzung):
    paket = await _paket()
    text = await _fehlertext("bundle_aendern", slug=paket["slug"], titel="x" * 201)
    assert "201" in text


async def test_aendern_ohne_jede_angabe_wird_abgelehnt(konfiguration, mcp_sitzung):
    paket = await _paket()
    text = await _fehlertext("bundle_aendern", slug=paket["slug"])
    assert "kein Feld" in text


async def test_aendern_eines_unbekannten_slugs_nennt_bundle_liste(konfiguration, mcp_sitzung):
    text = await _fehlertext("bundle_aendern", slug="gibt-es-nicht", titel="Neu")
    assert "bundle_liste" in text


async def test_beschreibung_laesst_sich_leeren(konfiguration, mcp_sitzung):
    """Ein leerer String heisst "weg", nicht "unveraendert".

    Anders liesse sich eine einmal gesetzte Beschreibung nie mehr
    loswerden - und das waere aus Sicht der Lehrerin ein Fehler.
    """
    paket = await _paket(beschreibung="Erster Entwurf")
    assert paket["beschreibung"] == "Erster Entwurf"
    geaendert = await _aufrufen("bundle_aendern", slug=paket["slug"], beschreibung="")
    assert geaendert["beschreibung"] == ""


# ===================== bundle_deaktivieren =====================


async def test_deaktivieren_setzt_aktiv_auf_falsch(konfiguration, mcp_sitzung):
    paket = await _paket()
    assert paket["aktiv"] is True
    ergebnis = await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=False)
    assert ergebnis["aktiv"] is False


async def test_deaktivieren_loescht_nichts(konfiguration, mcp_sitzung):
    """Die Spec verbietet endgueltiges Loeschen ueber MCP ausdruecklich.

    Das Lernpaket und alle Karten muessen danach noch da sein - sonst waere
    ein Versehen ein Datenverlust statt eines Handgriffs.
    """
    paket = await _paket(karten=[FLASHCARD, {**FLASHCARD, "vorderseite": "MTU"}])
    await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=False)

    weiterhin = await _aufrufen("bundle_anzeigen", slug=paket["slug"])
    assert weiterhin["aktiv"] is False
    assert len(weiterhin["karten"]) == 2
    assert weiterhin["titel"] == "Netzwerkgrundlagen"


async def test_deaktivieren_laesst_sich_zuruecknehmen(konfiguration, mcp_sitzung):
    """Ein Handgriff hin, ein Handgriff zurueck."""
    paket = await _paket()
    await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=False)
    wieder = await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=True)
    assert wieder["aktiv"] is True


async def test_ein_deaktiviertes_paket_faellt_aus_der_liste(konfiguration, mcp_sitzung):
    """nur_aktive ist standardmaessig an: Wer nichts angibt, sieht nur die
    aktiven Lernpakete. Erst nur_aktive=False holt die stillgelegten dazu."""
    paket = await _paket()
    await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=False)

    standard = await _aufrufen("bundle_liste")
    alle = await _aufrufen("bundle_liste", nur_aktive=False)
    assert paket["slug"] not in {eines["slug"] for eines in standard["bundles"]}
    assert paket["slug"] in {eines["slug"] for eines in alle["bundles"]}


async def test_deaktivieren_gibt_den_link_mit_zurueck(konfiguration, mcp_sitzung):
    paket = await _paket()
    ergebnis = await _aufrufen("bundle_deaktivieren", slug=paket["slug"], aktiv=False)
    assert ergebnis["url"] == f"{TEST_BASIS_URL}/{paket['slug']}"


async def test_deaktivieren_eines_unbekannten_slugs_nennt_bundle_liste(
    konfiguration, mcp_sitzung
):
    text = await _fehlertext("bundle_deaktivieren", slug="gibt-es-nicht", aktiv=False)
    assert "bundle_liste" in text


# ===================== Vollstaendigkeit =====================


async def test_alle_acht_werkzeuge_sind_da(konfiguration):
    """Die Spec listet in Abschnitt 5 genau acht Werkzeuge."""
    server, _ = mcp_bauen()
    namen = {eines.name for eines in await server.list_tools()}
    assert namen == {
        "bundle_anlegen",
        "bundle_liste",
        "bundle_anzeigen",
        "bundle_aendern",
        "karten_hinzufuegen",
        "karte_aendern",
        "karte_loeschen",
        "bundle_deaktivieren",
    }
