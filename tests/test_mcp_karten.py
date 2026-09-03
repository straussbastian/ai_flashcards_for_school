"""Tests fuer die Kartenpruefung.

Ohne Datenbank, ohne MCP. Der Schwerpunkt liegt auf den MELDUNGEN: Der Agent
liest sie der Lehrerin vor, also muessen sie sagen, was falsch ist UND was
zu tun ist. Ein Test, der nur den Ausnahmetyp prueft, prueft hier zu wenig.
"""

import pytest

from app.markdown import MAX_LAENGE
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import (
    beschreibung_pruefen,
    karte_pruefen,
    gruppe_pruefen,
    titel_pruefen,
)


def _frage(**abweichungen) -> KarteEingabe:
    felder = {
        "art": "frage",
        "vorderseite": "Was ist die Hauptstadt von Kroatien?",
        "antworten": ["Split", "Zagreb", "Dubrovnik", "Rijeka"],
        "richtige_antwort": "Zagreb",
        "erklaerung": "Zagreb liegt im Landesinneren.",
    }
    felder.update(abweichungen)
    return KarteEingabe(**felder)


def _flashcard(**abweichungen) -> KarteEingabe:
    felder = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlungsschicht"}
    felder.update(abweichungen)
    return KarteEingabe(**felder)


def test_eine_frage_wird_zu_spaltenwerten():
    werte = karte_pruefen(_frage(), nummer=1)
    assert werte["art"] == "frage"
    assert werte["antworten"] == ["Split", "Zagreb", "Dubrovnik", "Rijeka"]
    assert werte["richtige_index"] == 1
    assert werte["rueckseite"] is None
    assert werte["erklaerung"] == "Zagreb liegt im Landesinneren."


def test_eine_flashcard_wird_zu_spaltenwerten():
    werte = karte_pruefen(_flashcard(), nummer=1)
    assert werte["art"] == "flashcard"
    assert werte["rueckseite"] == "Vermittlungsschicht"
    assert werte["antworten"] is None
    assert werte["richtige_index"] is None
    assert werte["erklaerung"] is None


def test_gross_und_kleinschreibung_stoert_die_zuordnung_nicht():
    """Ein Agent, der "zagreb" tippt, soll nicht scheitern (Entscheidung E-4)."""
    assert karte_pruefen(_frage(richtige_antwort="  zagreb "), nummer=1)["richtige_index"] == 1


def test_fehlende_richtige_antwort_nennt_position_und_handlung():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(richtige_antwort=None), nummer=3)
    text = str(fehler.value)
    assert "Position 3" in text
    assert "keine richtige Antwort" in text
    assert "Text einer der Antwortmöglichkeiten" in text


def test_unbekannte_richtige_antwort_zeigt_die_moeglichkeiten():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(richtige_antwort="Ljubljana"), nummer=2)
    text = str(fehler.value)
    assert "Position 2" in text
    assert "Ljubljana" in text
    assert "Zagreb" in text
    assert "genau so" in text


def test_mehrfach_vorkommende_antwort_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(
            _frage(antworten=["Zagreb", "Zagreb", "Split"], richtige_antwort="Zagreb"),
            nummer=5,
        )
    text = str(fehler.value)
    assert "Position 5" in text
    assert "mehrfach" in text


@pytest.mark.parametrize(
    "antworten,anzahl",
    [
        (["Nur eine"], "eine"),
        (["A", "B", "C", "D", "E"], "fünf"),
        (["A", "B", "C", "D", "E", "F"], "sechs"),
    ],
)
def test_falsche_anzahl_antworten_wird_benannt(antworten, anzahl):
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(antworten=antworten, richtige_antwort=antworten[0]), nummer=4)
    text = str(fehler.value)
    assert "zwei bis vier Antwortmöglichkeiten" in text
    assert anzahl in text
    assert "Position 4" in text


def test_flashcard_ohne_rueckseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(rueckseite=None), nummer=1)
    assert "Rückseite" in str(fehler.value)


def test_flashcard_mit_antworten_wird_abgelehnt():
    """Die Datenbank verboete es ohnehin - aber mit einer Meldung, die
    niemandem weiterhilft."""
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(antworten=["A", "B"]), nummer=1)
    text = str(fehler.value)
    assert "Position 1" in text
    assert "Antwortmöglichkeiten" in text


def test_frage_mit_rueckseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(rueckseite="steht hier falsch"), nummer=1)
    assert "Rückseite" in str(fehler.value)


def test_leere_vorderseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(vorderseite="   "), nummer=7)
    text = str(fehler.value)
    assert "Position 7" in text
    assert "Vorderseite" in text


def test_zu_langer_text_wird_vor_dem_speichern_abgefangen():
    """Die Meldung muss BEIDE Zahlen nennen - so kommt sie aus
    app/markdown.py, und so ist sie brauchbar."""
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(rueckseite="x" * (MAX_LAENGE + 1)), nummer=2)
    text = str(fehler.value)
    assert str(MAX_LAENGE + 1) in text
    assert str(MAX_LAENGE) in text
    assert "Position 2" in text


def test_genau_die_grenze_ist_erlaubt():
    karte_pruefen(_flashcard(rueckseite="x" * MAX_LAENGE), nummer=1)


def test_titel_wird_beschnitten_und_geprueft():
    assert titel_pruefen("  Netzwerktechnik  ") == "Netzwerktechnik"
    with pytest.raises(MCPFehler) as fehler:
        titel_pruefen("   ")
    assert "Titel" in str(fehler.value)
    with pytest.raises(MCPFehler) as fehler:
        titel_pruefen("t" * 201)
    assert "200" in str(fehler.value)


def test_gruppe_ist_optional_und_begrenzt():
    assert gruppe_pruefen(None) is None
    assert gruppe_pruefen("   ") is None
    assert gruppe_pruefen("  FS 23b ") == "FS 23b"
    with pytest.raises(MCPFehler) as fehler:
        gruppe_pruefen("k" * 61)
    assert "60" in str(fehler.value)


def test_beschreibung_ist_optional_und_geht_durch_die_laengenpruefung():
    assert beschreibung_pruefen(None) is None
    assert beschreibung_pruefen("  ") is None
    assert beschreibung_pruefen(" Kurz ") == "Kurz"
    with pytest.raises(MCPFehler):
        beschreibung_pruefen("b" * (MAX_LAENGE + 1))
