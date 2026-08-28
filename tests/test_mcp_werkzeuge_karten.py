"""Tests fuer die Werkzeuge, die einzelne Karten pflegen.

Aufgerufen wird ueber MCPServer.call_tool(), wie in
tests/test_mcp_werkzeuge_bundles.py und aus demselben Grund.

Der Massstab dieser Datei ist Abschnitt 5 der Spec (dort stehen die acht
Werkzeuge mit Ein- und Ausgabe) und Entscheidung E-5 des Plans: Beim
Loeschen werden die Positionen NICHT neu vergeben, und karten_hinzufuegen
haengt mit max(position) + 1 hinten an. Das ist keine Bequemlichkeit,
sondern haelt jedes Massen-update() von den Tabellen fern - "geaendert_am"
traegt onupdate=func.now() und wird deshalb nur vom ORM gesetzt.
"""

import json

import pytest
from sqlalchemy import select

from app.mcp import mcp_bauen
from app.models import Karte
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
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is False, ergebnis.content[0].text
    return json.loads(ergebnis.content[0].text)


async def _fehlertext(name: str, **argumente) -> str:
    """Wie in tests/test_mcp_werkzeuge_bundles.py: call_tool wirft den ToolError."""
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


async def _paket(karten=None) -> dict:
    """Legt ein Lernpaket an und gibt seine Uebersicht zurueck."""
    return await _aufrufen(
        "bundle_anlegen", titel="Netzwerkgrundlagen", karten=karten or [FLASHCARD, FRAGE]
    )


async def _karten_von(slug: str) -> list[dict]:
    return (await _aufrufen("bundle_anzeigen", slug=slug))["karten"]


# ===================== karten_hinzufuegen =====================


async def test_hinzufuegen_haengt_hinten_an_und_nennt_die_neue_gesamtzahl(
    konfiguration, mcp_sitzung
):
    paket = await _paket()
    ergebnis = await _aufrufen(
        "karten_hinzufuegen", slug=paket["slug"], karten=[{**FLASHCARD, "vorderseite": "MTU"}]
    )
    assert ergebnis["anzahl_karten"] == 3
    assert len(ergebnis["neue_karten"]) == 1
    assert ergebnis["neue_karten"][0]["position"] == 2
    assert ergebnis["url"] == f"{TEST_BASIS_URL}/{paket['slug']}"


async def test_hinzufuegen_gibt_die_ids_der_neuen_karten_zurueck(konfiguration, mcp_sitzung):
    """Ohne die IDs koennte der Agent die neuen Karten nicht weiterbearbeiten."""
    paket = await _paket()
    ergebnis = await _aufrufen(
        "karten_hinzufuegen",
        slug=paket["slug"],
        karten=[{**FLASHCARD, "vorderseite": "MTU"}, {**FRAGE, "vorderseite": "Was ist ARP?"}],
    )
    kennungen = [eine["karte_id"] for eine in ergebnis["neue_karten"]]
    assert len(set(kennungen)) == 2
    vorhandene = {eine["karte_id"] for eine in await _karten_von(paket["slug"])}
    assert set(kennungen) <= vorhandene


async def test_hinzufuegen_ohne_karten_wird_abgelehnt(konfiguration, mcp_sitzung):
    paket = await _paket()
    text = await _fehlertext("karten_hinzufuegen", slug=paket["slug"], karten=[])
    assert "keine Karten" in text


async def test_eine_kaputte_karte_verhindert_alle_neuen(konfiguration, mcp_sitzung):
    """Alles oder nichts - wie bei bundle_anlegen und aus demselben Grund."""
    paket = await _paket()
    kaputt = {"art": "frage", "vorderseite": "Was ist ARP?", "antworten": ["nur eine"]}
    text = await _fehlertext(
        "karten_hinzufuegen", slug=paket["slug"], karten=[{**FLASHCARD, "vorderseite": "MTU"}, kaputt]
    )
    assert "Position 2" in text
    assert len(await _karten_von(paket["slug"])) == 2


async def test_hinzufuegen_zu_unbekanntem_slug_nennt_das_werkzeug_zum_nachsehen(
    konfiguration, mcp_sitzung
):
    text = await _fehlertext("karten_hinzufuegen", slug="gibt-es-nicht", karten=[FLASHCARD])
    assert "bundle_liste" in text


# ===================== karte_aendern =====================


async def test_aendern_ersetzt_nur_das_angegebene_feld(konfiguration, mcp_sitzung):
    paket = await _paket()
    karte = (await _karten_von(paket["slug"]))[0]
    geaendert = await _aufrufen(
        "karte_aendern", karte_id=karte["karte_id"], vorderseite="OSI-Schicht 4"
    )
    assert geaendert["karte"]["vorderseite"] == "OSI-Schicht 4"
    assert geaendert["karte"]["rueckseite"] == karte["rueckseite"]
    assert geaendert["url"] == f"{TEST_BASIS_URL}/{paket['slug']}"


async def test_aendern_einer_frage_ohne_neue_richtige_antwort_behaelt_sie(
    konfiguration, mcp_sitzung
):
    """Die richtige Antwort steht als Text in der Karte, nicht als Index.

    Wird nur die Erklaerung geaendert, muss dieselbe Antwort richtig
    bleiben - sonst waere jede Teilaenderung ein stiller Datenverlust.
    """
    paket = await _paket()
    frage = (await _karten_von(paket["slug"]))[1]
    geaendert = await _aufrufen(
        "karte_aendern", karte_id=frage["karte_id"], erklaerung="Neu erklärt."
    )
    assert geaendert["karte"]["richtige_antwort"] == "Zagreb"
    assert geaendert["karte"]["erklaerung"] == "Neu erklärt."


async def test_neue_antworten_ohne_die_alte_richtige_werden_abgelehnt(konfiguration, mcp_sitzung):
    """Der gefaehrlichste Fall: Die Antwortliste wandert, der Index nicht."""
    paket = await _paket()
    frage = (await _karten_von(paket["slug"]))[1]
    text = await _fehlertext(
        "karte_aendern", karte_id=frage["karte_id"], antworten=["Split", "Rijeka", "Osijek"]
    )
    assert "Zagreb" in text


async def test_antworten_und_richtige_antwort_zusammen_gehen(konfiguration, mcp_sitzung):
    paket = await _paket()
    frage = (await _karten_von(paket["slug"]))[1]
    geaendert = await _aufrufen(
        "karte_aendern",
        karte_id=frage["karte_id"],
        antworten=["Split", "Rijeka", "Osijek"],
        richtige_antwort="Osijek",
    )
    assert geaendert["karte"]["richtige_antwort"] == "Osijek"
    assert geaendert["karte"]["antworten"] == ["Split", "Rijeka", "Osijek"]


async def test_aendern_haelt_die_pruefungen_der_karte_ein(konfiguration, mcp_sitzung):
    """Eine Flashcard darf auch nachtraeglich keine Antworten bekommen."""
    paket = await _paket()
    karte = (await _karten_von(paket["slug"]))[0]
    text = await _fehlertext(
        "karte_aendern", karte_id=karte["karte_id"], antworten=["ja", "nein"]
    )
    assert "Flashcard" in text


async def test_aendern_mit_unbrauchbarer_id_nennt_wo_die_ids_stehen(konfiguration, mcp_sitzung):
    text = await _fehlertext("karte_aendern", karte_id="keine-uuid", vorderseite="x")
    assert "bundle_anzeigen" in text


async def test_aendern_ohne_jede_angabe_wird_abgelehnt(konfiguration, mcp_sitzung):
    """Ein Aufruf, der nichts aendert, ist fast immer ein Missverstaendnis."""
    paket = await _paket()
    karte = (await _karten_von(paket["slug"]))[0]
    text = await _fehlertext("karte_aendern", karte_id=karte["karte_id"])
    assert "kein Feld" in text


# ===================== karte_loeschen =====================


async def test_loeschen_entfernt_die_karte_und_nennt_den_rest(konfiguration, mcp_sitzung):
    paket = await _paket()
    karte = (await _karten_von(paket["slug"]))[0]
    ergebnis = await _aufrufen("karte_loeschen", karte_id=karte["karte_id"])
    assert ergebnis["anzahl_karten"] == 1
    assert ergebnis["url"] == f"{TEST_BASIS_URL}/{paket['slug']}"
    uebrig = await _karten_von(paket["slug"])
    assert len(uebrig) == 1
    assert karte["karte_id"] not in {eine["karte_id"] for eine in uebrig}
    # Die verbliebene Karte ist die andere, nicht irgendeine.
    assert uebrig[0]["vorderseite"] == FRAGE["vorderseite"]


async def test_loeschen_vergibt_die_positionen_nicht_neu(konfiguration, mcp_sitzung):
    """Entscheidung E-5 des Plans, hier festgehalten.

    Die Reihenfolge ergibt sich aus der Sortierung nach position; eine
    Luecke stoert dabei nicht. Wuerde hier neu nummeriert, braeuchte es ein
    Massen-update() - und das fasst geaendert_am nicht an, weil die Spalte
    ihren Wert ueber onupdate vom ORM bekommt.
    """
    paket = await _paket(karten=[FLASHCARD, FRAGE, {**FLASHCARD, "vorderseite": "MTU"}])
    karten = await _karten_von(paket["slug"])
    assert [eine["position"] for eine in karten] == [0, 1, 2]

    await _aufrufen("karte_loeschen", karte_id=karten[1]["karte_id"])
    assert [eine["position"] for eine in await _karten_von(paket["slug"])] == [0, 2]


async def test_nach_dem_loeschen_haengt_die_naechste_karte_hinten_an(konfiguration, mcp_sitzung):
    """max(position) + 1 statt anzahl: Sonst kollidierte die neue Karte.

    Nach dem Loeschen der mittleren Karte gibt es zwei Karten, aber die
    hoechste Position ist 2. Eine neue Karte auf Position "anzahl" waere
    Position 2 - und liefe in uq_karten_bundle_position.
    """
    paket = await _paket(karten=[FLASHCARD, FRAGE, {**FLASHCARD, "vorderseite": "MTU"}])
    karten = await _karten_von(paket["slug"])
    await _aufrufen("karte_loeschen", karte_id=karten[1]["karte_id"])

    ergebnis = await _aufrufen(
        "karten_hinzufuegen", slug=paket["slug"], karten=[{**FLASHCARD, "vorderseite": "VLAN"}]
    )
    assert ergebnis["neue_karten"][0]["position"] == 3
    assert [eine["position"] for eine in await _karten_von(paket["slug"])] == [0, 2, 3]


async def test_die_letzte_karte_laesst_sich_nicht_loeschen(konfiguration, mcp_sitzung):
    """Ein Lernpaket ohne Karten kann niemand ueben - siehe bundle_anlegen.

    Wer das Paket loswerden will, benutzt bundle_deaktivieren; endgueltiges
    Loeschen gibt es ueber MCP bewusst nicht (Spec, Abschnitt 5).
    """
    paket = await _paket(karten=[FLASHCARD])
    karte = (await _karten_von(paket["slug"]))[0]
    text = await _fehlertext("karte_loeschen", karte_id=karte["karte_id"])
    assert "bundle_deaktivieren" in text
    assert len(await _karten_von(paket["slug"])) == 1


async def test_loeschen_einer_unbekannten_karte_wird_gemeldet(konfiguration, mcp_sitzung):
    import uuid

    text = await _fehlertext("karte_loeschen", karte_id=str(uuid.uuid4()))
    assert "gibt es nicht" in text


async def test_geloeschte_karte_ist_wirklich_fort(konfiguration, mcp_sitzung, session):
    paket = await _paket()
    karte = (await _karten_von(paket["slug"]))[0]
    await _aufrufen("karte_loeschen", karte_id=karte["karte_id"])
    import uuid

    gefunden = await session.scalar(
        select(Karte).where(Karte.id == uuid.UUID(karte["karte_id"]))
    )
    assert gefunden is None
