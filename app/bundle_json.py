"""Aus Bundle und Karten die Form bauen, die der Browser bekommt.

Der einzige Ort, an dem entschieden wird, was ausgeliefert wird. Wichtig
dabei: Nur `vorderseite`, `rueckseite`, `erklaerung` und `beschreibung`
enthalten HTML, und dieses HTML kommt ausschliesslich aus `rendern()`.
Antworttexte, Titel und Klasse bleiben Klartext - der Browser setzt sie
als Text ein, nicht als HTML.

Optionale Felder sind immer vorhanden und tragen bei Abwesenheit einen
leeren String (`beschreibung`, `erklaerung`, `klasse`). Das gewährleistet
eine konsistente Prüfung im Browser: `if (bundle.klasse)`, `if (karte.erklaerung)`
usw. funktionieren überall gleich.
"""

from app.markdown import rendern
from app.models import Bundle, Karte


def _karte(karte: Karte) -> dict:
    daten: dict = {"art": karte.art, "vorderseite": rendern(karte.vorderseite)}
    if karte.art == "flashcard":
        daten["rueckseite"] = rendern(karte.rueckseite)
        return daten
    daten["antworten"] = list(karte.antworten or [])
    daten["richtige_index"] = karte.richtige_index
    daten["erklaerung"] = rendern(karte.erklaerung)
    return daten


def bauen(bundle: Bundle) -> dict:
    karten = sorted(bundle.karten, key=lambda k: k.position)
    flashcards = sum(1 for k in karten if k.art == "flashcard")
    return {
        "titel": bundle.titel,
        "beschreibung": rendern(bundle.beschreibung),
        "klasse": bundle.klasse or "",
        "selbsteinschaetzung": bundle.selbsteinschaetzung,
        "reihenfolge": bundle.reihenfolge,
        "anzahl": {
            "gesamt": len(karten),
            "flashcards": flashcards,
            "fragen": len(karten) - flashcards,
        },
        "karten": [_karte(k) for k in karten],
    }
