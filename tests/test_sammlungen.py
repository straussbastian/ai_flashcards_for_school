"""Sammlungen: die Werkzeuge und die beiden Routen.

Massstab ist docs/superpowers/specs/2026-09-03-sammlungen-design.md.

Zwei Entscheidungen tragen den Entwurf und greifen ineinander: n:m (ein
Lernpaket darf in mehreren Sammlungen liegen) und die verschachtelte Adresse
/sammlung/paket. Ohne die zweite waere bei der ersten unklar, wohin
"zurueck" fuehrt. Der Test dazu steht ganz unten und ist der wichtigste
dieser Datei.
"""

import json

import pytest

from app.mcp import mcp_bauen
from app.models import Adresse, Bundle, Karte

FLASHCARD = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlung"}


async def _aufrufen(name: str, **argumente) -> dict:
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is False, ergebnis.content[0].text
    return json.loads(ergebnis.content[0].text)


async def _fehlertext(name: str, **argumente) -> str:
    server, _ = mcp_bauen()
    try:
        ergebnis = await server.call_tool(name, argumente)
    except Exception as fehler:  # noqa: BLE001 -- ToolError des SDK
        return str(fehler)
    assert ergebnis.is_error, "Der Aufruf haette scheitern muessen."
    return ergebnis.content[0].text


async def _paket(sitzung, slug: str, titel: str, aktiv: bool = True) -> Bundle:
    """Ein Lernpaket samt Adresse und einer Karte, ohne Umweg ueber MCP."""
    sitzung.add(Adresse(slug=slug, art="paket"))
    bundle = Bundle(slug=slug, titel=titel, aktiv=aktiv)
    sitzung.add(bundle)
    await sitzung.flush()
    sitzung.add(Karte(bundle_id=bundle.id, position=0, art="flashcard",
                      vorderseite="Frage", rueckseite="Antwort"))
    await sitzung.flush()
    return bundle


# ====================== Die Werkzeuge ======================


async def test_sammlung_anlegen_gibt_adresse_und_link(konfiguration, mcp_sitzung):
    daten = await _aufrufen("sammlung_anlegen", titel="Englisch komplett")
    assert daten["titel"] == "Englisch komplett"
    assert daten["url"].endswith(daten["slug"])
    assert daten["anzahl_pakete"] == 0


async def test_sammlung_bekommt_keine_paketadresse(konfiguration, mcp_sitzung):
    """Der gemeinsame Adressraum, von der Werkzeugseite aus gesehen."""
    paket = await _aufrufen("bundle_anlegen", titel="Ein Paket", karten=[FLASHCARD])
    sammlung = await _aufrufen("sammlung_anlegen", titel="Eine Sammlung")
    assert sammlung["slug"] != paket["slug"]


async def test_pakete_stehen_in_der_angegebenen_reihenfolge(konfiguration, mcp_sitzung):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Englisch 1")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Englisch 2")

    angelegt = await _aufrufen(
        "sammlung_anlegen", titel="Englisch",
        pakete=["gelassene-treppe-hobelt", "erste-klinge-kitzelt"],
    )
    gezeigt = await _aufrufen("sammlung_anzeigen", slug=angelegt["slug"])
    assert [p["titel"] for p in gezeigt["pakete"]] == ["Englisch 2", "Englisch 1"]
    assert [p["position"] for p in gezeigt["pakete"]] == [0, 1]


async def test_die_links_zeigen_auf_die_verschachtelte_adresse(konfiguration, mcp_sitzung):
    """Genau diese URL gehoert in einen Link fuer die Klasse."""
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Englisch 1")
    angelegt = await _aufrufen("sammlung_anlegen", titel="Englisch",
                               pakete=["erste-klinge-kitzelt"])
    gezeigt = await _aufrufen("sammlung_anzeigen", slug=angelegt["slug"])
    assert gezeigt["pakete"][0]["url"].endswith(
        f"{angelegt['slug']}/erste-klinge-kitzelt"
    )


async def test_pakete_setzen_ersetzt_die_ganze_liste(konfiguration, mcp_sitzung):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Eins")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Zwei")
    angelegt = await _aufrufen("sammlung_anlegen", titel="S",
                               pakete=["erste-klinge-kitzelt"])

    daten = await _aufrufen("sammlung_pakete_setzen", slug=angelegt["slug"],
                            pakete=["gelassene-treppe-hobelt"])
    assert [p["titel"] for p in daten["pakete"]] == ["Zwei"]


async def test_eine_leere_liste_leert_die_sammlung(konfiguration, mcp_sitzung):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Eins")
    angelegt = await _aufrufen("sammlung_anlegen", titel="S",
                               pakete=["erste-klinge-kitzelt"])
    daten = await _aufrufen("sammlung_pakete_setzen", slug=angelegt["slug"], pakete=[])
    assert daten["pakete"] == []
    assert daten["anzahl_pakete"] == 0


async def test_ein_paket_zweimal_in_derselben_sammlung_wird_abgelehnt(
    konfiguration, mcp_sitzung
):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Eins")
    angelegt = await _aufrufen("sammlung_anlegen", titel="S")

    text = await _fehlertext(
        "sammlung_pakete_setzen", slug=angelegt["slug"],
        pakete=["erste-klinge-kitzelt", "erste-klinge-kitzelt"],
    )
    assert "mehrfach" in text
    assert "erste-klinge-kitzelt" in text


async def test_ein_unbekanntes_paket_wird_im_klartext_gemeldet(konfiguration, mcp_sitzung):
    angelegt = await _aufrufen("sammlung_anlegen", titel="S")
    text = await _fehlertext("sammlung_pakete_setzen", slug=angelegt["slug"],
                             pakete=["gibt-es-nicht"])
    assert "gibt-es-nicht" in text
    assert "bundle_liste" in text


async def test_liste_filtert_nach_gruppe_und_laesst_deaktivierte_weg(
    konfiguration, mcp_sitzung
):
    eins = await _aufrufen("sammlung_anlegen", titel="Eins", gruppe="Englisch")
    await _aufrufen("sammlung_anlegen", titel="Zwei", gruppe="Mathe")
    drei = await _aufrufen("sammlung_anlegen", titel="Drei", gruppe="Englisch")
    await _aufrufen("sammlung_deaktivieren", slug=drei["slug"], aktiv=False)

    daten = await _aufrufen("sammlung_liste", gruppe="Englisch")
    assert [s["titel"] for s in daten["sammlungen"]] == ["Eins"]
    assert daten["sammlungen"][0]["slug"] == eins["slug"]

    mit_stillen = await _aufrufen("sammlung_liste", gruppe="Englisch", nur_aktive=False)
    assert {s["titel"] for s in mit_stillen["sammlungen"]} == {"Eins", "Drei"}


async def test_aendern_laesst_die_adresse_stehen(konfiguration, mcp_sitzung):
    """Die Adresse ist weitergegeben worden und darf sich nicht wegbewegen."""
    angelegt = await _aufrufen("sammlung_anlegen", titel="Alt")
    geaendert = await _aufrufen("sammlung_aendern", slug=angelegt["slug"], titel="Neu")
    assert geaendert["slug"] == angelegt["slug"]
    assert geaendert["titel"] == "Neu"


# ====================== Die Routen ======================


async def test_die_sammlungsseite_listet_ihre_pakete(konfiguration, mcp_sitzung, klient):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Englisch 1")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Englisch 2")
    angelegt = await _aufrufen(
        "sammlung_anlegen", titel="Englisch komplett",
        pakete=["erste-klinge-kitzelt", "gelassene-treppe-hobelt"],
    )

    antwort = await klient.get(f"/{angelegt['slug']}")
    assert antwort.status_code == 200
    assert "Englisch komplett" in antwort.text
    assert antwort.text.index("Englisch 1") < antwort.text.index("Englisch 2")
    assert f"/{angelegt['slug']}/erste-klinge-kitzelt" in antwort.text


async def test_deaktivierte_pakete_stehen_nicht_in_der_sammlung(
    konfiguration, mcp_sitzung, klient
):
    """Eine Sammlung soll nichts anbieten, was hinter dem Link nicht da ist."""
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Sichtbar")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Stillgelegt", aktiv=False)
    angelegt = await _aufrufen(
        "sammlung_anlegen", titel="S",
        pakete=["erste-klinge-kitzelt", "gelassene-treppe-hobelt"],
    )

    antwort = await klient.get(f"/{angelegt['slug']}")
    assert "Sichtbar" in antwort.text
    assert "Stillgelegt" not in antwort.text


async def test_das_paket_im_kontext_kennt_seine_sammlung(
    konfiguration, mcp_sitzung, klient
):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Englisch 1")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Englisch 2")
    angelegt = await _aufrufen(
        "sammlung_anlegen", titel="Englisch komplett",
        pakete=["erste-klinge-kitzelt", "gelassene-treppe-hobelt"],
    )

    antwort = await klient.get(f"/{angelegt['slug']}/erste-klinge-kitzelt")
    assert antwort.status_code == 200
    assert "Englisch komplett" in antwort.text
    assert "Englisch 2" in antwort.text          # das naechste Paket


async def test_beim_letzten_paket_gibt_es_kein_naechstes(
    konfiguration, mcp_sitzung, klient
):
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Einziges")
    angelegt = await _aufrufen("sammlung_anlegen", titel="S",
                               pakete=["erste-klinge-kitzelt"])

    antwort = await klient.get(f"/{angelegt['slug']}/erste-klinge-kitzelt")
    daten = json.loads(antwort.text.split('id="bundle-daten"')[1].split(">", 1)[1].split("</script>")[0])
    assert daten["sammlung"]["naechstes"] is None


async def test_ohne_sammlung_traegt_das_paket_keinen_kontext(
    konfiguration, mcp_sitzung, klient
):
    """Die einzelne Adresse verhaelt sich unveraendert."""
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Einzeln")
    antwort = await klient.get("/erste-klinge-kitzelt")
    daten = json.loads(antwort.text.split('id="bundle-daten"')[1].split(">", 1)[1].split("</script>")[0])
    assert "sammlung" not in daten


async def test_ein_paket_das_nicht_zur_sammlung_gehoert_gibt_404(
    konfiguration, mcp_sitzung, klient
):
    """Ausdruecklich 404 und nicht stillschweigend das Paket ohne Kontext.

    Eine erfundene Kombination ist ein Irrtum und soll als solcher
    erscheinen - sonst sieht die Klasse eine Seite, die es so nie gab.
    """
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Drin")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Draussen")
    angelegt = await _aufrufen("sammlung_anlegen", titel="S",
                               pakete=["erste-klinge-kitzelt"])

    antwort = await klient.get(f"/{angelegt['slug']}/gelassene-treppe-hobelt")
    assert antwort.status_code == 404


@pytest.mark.parametrize("adresse", [
    "/gibt-es-gar-nicht/erste-klinge-kitzelt",
    "/kein-gueltiges-muster",
    "/zu/kurz",
])
async def test_unsinnige_adressen_geben_404(konfiguration, mcp_sitzung, klient, adresse):
    antwort = await klient.get(adresse)
    assert antwort.status_code == 404


async def test_eine_stillgelegte_sammlung_antwortet_mit_410(
    konfiguration, mcp_sitzung, klient
):
    angelegt = await _aufrufen("sammlung_anlegen", titel="Weg")
    await _aufrufen("sammlung_deaktivieren", slug=angelegt["slug"], aktiv=False)
    antwort = await klient.get(f"/{angelegt['slug']}")
    assert antwort.status_code == 410


# ====================== Der wichtigste Test ======================


async def test_dasselbe_paket_in_zwei_sammlungen_fuehrt_jeweils_richtig_weiter(
    konfiguration, mcp_sitzung, klient
):
    """Der Grund, warum die Adresse verschachtelt ist.

    Ein Lernpaket darf in mehreren Sammlungen liegen (n:m). Aus der
    Zugehoerigkeit allein liesse sich dann nicht ableiten, wohin "zurueck"
    fuehrt und was das naechste Paket ist - aus dem WEG hierher schon.

    Das ist die Zusicherung, die am ehesten unbemerkt braeche: Beide Wege
    liefern 200, beide zeigen dasselbe Lernpaket, und nur der Kontext
    unterscheidet sie.
    """
    await _paket(mcp_sitzung, "erste-klinge-kitzelt", "Das geteilte Paket")
    await _paket(mcp_sitzung, "gelassene-treppe-hobelt", "Nur in Englisch")
    await _paket(mcp_sitzung, "junge-decke-entdeckt", "Nur in Pruefung")

    englisch = await _aufrufen(
        "sammlung_anlegen", titel="Englisch komplett",
        pakete=["erste-klinge-kitzelt", "gelassene-treppe-hobelt"],
    )
    pruefung = await _aufrufen(
        "sammlung_anlegen", titel="Pruefung Januar",
        pakete=["erste-klinge-kitzelt", "junge-decke-entdeckt"],
    )

    def kontext(text: str) -> dict:
        daten = json.loads(
            text.split('id="bundle-daten"')[1].split(">", 1)[1].split("</script>")[0]
        )
        return daten["sammlung"]

    ueber_englisch = kontext(
        (await klient.get(f"/{englisch['slug']}/erste-klinge-kitzelt")).text
    )
    ueber_pruefung = kontext(
        (await klient.get(f"/{pruefung['slug']}/erste-klinge-kitzelt")).text
    )

    assert ueber_englisch["titel"] == "Englisch komplett"
    assert ueber_englisch["url"] == f"/{englisch['slug']}"
    assert ueber_englisch["naechstes"]["titel"] == "Nur in Englisch"

    assert ueber_pruefung["titel"] == "Pruefung Januar"
    assert ueber_pruefung["url"] == f"/{pruefung['slug']}"
    assert ueber_pruefung["naechstes"]["titel"] == "Nur in Pruefung"
