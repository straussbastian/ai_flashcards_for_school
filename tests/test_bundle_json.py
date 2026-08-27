import pytest

from app.bundle_json import bauen
from app.models import Bundle, Karte


def _bundle(**abweichungen) -> Bundle:
    werte = dict(slug="kluge-tafel-leuchtet", titel="Arbeitsrecht kompakt",
                 beschreibung=None, klasse=None, selbsteinschaetzung=True,
                 reihenfolge="zufall")
    werte.update(abweichungen)
    bundle = Bundle(**werte)
    bundle.karten = []
    return bundle


def _flashcard(position: int, vorn: str, hinten: str) -> Karte:
    return Karte(position=position, art="flashcard", vorderseite=vorn, rueckseite=hinten)


def _frage(position: int, frage: str, antworten: list[str], index: int,
           erklaerung: str | None = None) -> Karte:
    return Karte(position=position, art="frage", vorderseite=frage,
                 antworten=antworten, richtige_index=index, erklaerung=erklaerung)


def test_kopfdaten_wandern_unveraendert_durch():
    bundle = _bundle(klasse="FS 23b")
    ergebnis = bauen(bundle)
    assert ergebnis["titel"] == "Arbeitsrecht kompakt"
    assert ergebnis["klasse"] == "FS 23b"
    assert ergebnis["selbsteinschaetzung"] is True
    assert ergebnis["reihenfolge"] == "zufall"


def test_markdown_wird_zu_html_gerendert():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "Das ist **wichtig**", "Antwort")]
    karte = bauen(bundle)["karten"][0]
    assert "<strong>wichtig</strong>" in karte["vorderseite"]


def test_antworttexte_bleiben_klartext():
    bundle = _bundle()
    bundle.karten = [_frage(1, "Frage", ["**nicht fett**", "zwei"], 0)]
    karte = bauen(bundle)["karten"][0]
    assert karte["antworten"] == ["**nicht fett**", "zwei"]


def test_skript_in_einer_karte_wird_entfernt():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "Hallo <script>alert(1)</script>", "Antwort")]
    karte = bauen(bundle)["karten"][0]
    assert "script" not in karte["vorderseite"].lower()


def test_karten_kommen_in_position_sreihenfolge():
    bundle = _bundle()
    bundle.karten = [_flashcard(2, "zwei", "b"), _flashcard(1, "eins", "a")]
    reihenfolge = [k["vorderseite"] for k in bauen(bundle)["karten"]]
    assert "eins" in reihenfolge[0]
    assert "zwei" in reihenfolge[1]


def test_zusammensetzung_wird_gezaehlt():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "a", "b"), _frage(2, "c", ["d", "e"], 0)]
    ergebnis = bauen(bundle)
    assert ergebnis["anzahl"] == {"gesamt": 2, "flashcards": 1, "fragen": 1}


def test_flashcard_traegt_keine_antwortfelder():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "a", "b")]
    karte = bauen(bundle)["karten"][0]
    assert "antworten" not in karte
    assert "richtige_index" not in karte


def test_leere_erklaerung_wird_weggelassen():
    bundle = _bundle()
    bundle.karten = [_frage(1, "Frage", ["a", "b"], 0, erklaerung=None)]
    assert "erklaerung" not in bauen(bundle)["karten"][0]
