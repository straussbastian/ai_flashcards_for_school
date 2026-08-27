"""Aus einer Eingabe des Agenten werden geprueft Spaltenwerte.

Zwei Dinge geschehen hier, und beide sind in der Spec begruendet:

1. Die richtige Antwort kommt als TEXT und wird zu einer POSITION. Die
   Antwortreihenfolge wird bei jedem Durchlauf neu gemischt; ein
   gespeicherter Buchstabe waere danach falsch. Und der Agent, der einen
   Text angibt statt eines Buchstabens, kann nicht verrutschen.
2. Die Laengen werden HIER geprueft, nicht erst beim Ausliefern. Die
   Datenbank hat eigene Constraints, aber die melden sich mit einem
   Constraint-Namen - und den soll die Lehrerin nicht vorgelesen bekommen.
"""

from app.markdown import MarkdownZuLang, rendern
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler, bei_karte
from app.models import MAX_KLASSE_LAENGE, MAX_TITEL_LAENGE

MIN_ANTWORTEN = 2
MAX_ANTWORTEN = 4

# Fuer die Meldung "diese hat sechs" aus der Spec. Zahlwoerter statt Ziffern,
# weil die Meldung vorgelesen wird.
_ZAHLWOERTER = {
    0: "keine",
    1: "eine",
    2: "zwei",
    3: "drei",
    4: "vier",
    5: "fünf",
    6: "sechs",
    7: "sieben",
    8: "acht",
    9: "neun",
    10: "zehn",
}


def _zahlwort(anzahl: int) -> str:
    return _ZAHLWOERTER.get(anzahl, str(anzahl))


def _normalisiert(text: str) -> str:
    """Die Form, in der Antworttexte verglichen werden (Entscheidung E-4)."""
    return text.strip().casefold()


def _laenge_pruefen(text: str | None, feld: str, ort: str) -> None:
    """Wirft MCPFehler, wenn der Text nicht ausgeliefert werden koennte.

    rendern() macht die Arbeit: Es wirft MarkdownZuLang mit einer Meldung,
    die beide Zahlen nennt ("ist mit 5210 Zeichen zu lang. Erlaubt sind 5000
    Zeichen pro Karte."). Die uebernehmen wir woertlich und stellen nur den
    Ort davor.
    """
    if text is None:
        return
    try:
        rendern(text)
    except MarkdownZuLang as fehler:
        raise MCPFehler(f"{ort}: Das Feld '{feld}' ist zu lang. {fehler}") from fehler


def karte_pruefen(eingabe: KarteEingabe, nummer: int) -> dict:
    """Prueft eine Karte und gibt ihre Spaltenwerte zurueck.

    Args:
        eingabe: Die Karte, wie der Agent sie uebergeben hat.
        nummer: Die Position in der uebergebenen Liste, beginnend bei 1.
            Erscheint in jeder Meldung, damit die Lehrerin weiss, welche
            Karte gemeint ist.

    Returns:
        Ein Dict mit den Schluesseln art, vorderseite, rueckseite,
        antworten, richtige_index, erklaerung - genau die Spalten von
        app.models.Karte ausser id, bundle_id und position.

    Raises:
        MCPFehler: Mit einer deutschen Meldung, die sagt, was zu tun ist.
    """
    ort = f"Die Karte auf Position {nummer}"
    vorderseite = (eingabe.vorderseite or "").strip()
    if not vorderseite:
        raise MCPFehler(
            bei_karte(nummer, "hat keine Vorderseite. Bitte gib den Begriff "
                              "oder die Frage an.")
        )
    _laenge_pruefen(vorderseite, "vorderseite", ort)

    if eingabe.art == "flashcard":
        return _flashcard_pruefen(eingabe, nummer, ort, vorderseite)
    return _frage_pruefen(eingabe, nummer, ort, vorderseite)


def _flashcard_pruefen(eingabe: KarteEingabe, nummer: int, ort: str, vorderseite: str) -> dict:
    rueckseite = (eingabe.rueckseite or "").strip()
    if not rueckseite:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard, hat aber keine Rückseite. "
                              "Bitte gib an, was auf der Rückseite stehen soll.")
        )
    if eingabe.antworten or eingabe.richtige_antwort:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard und darf keine "
                              "Antwortmöglichkeiten haben. Setze art auf 'frage', "
                              "wenn es eine Multiple-Choice-Frage werden soll.")
        )
    if eingabe.erklaerung:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard und darf keine Erklärung "
                              "haben. Schreib die Erklärung mit auf die Rückseite.")
        )
    _laenge_pruefen(rueckseite, "rueckseite", ort)
    return {
        "art": "flashcard",
        "vorderseite": vorderseite,
        "rueckseite": rueckseite,
        "antworten": None,
        "richtige_index": None,
        "erklaerung": None,
    }


def _frage_pruefen(eingabe: KarteEingabe, nummer: int, ort: str, vorderseite: str) -> dict:
    if eingabe.rueckseite:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Frage und darf keine Rückseite haben. "
                              "Was dort stehen sollte, gehört in 'erklaerung'.")
        )

    antworten = [text.strip() for text in (eingabe.antworten or [])]
    if not MIN_ANTWORTEN <= len(antworten) <= MAX_ANTWORTEN:
        raise MCPFehler(
            "Eine Frage braucht zwei bis vier Antwortmöglichkeiten, "
            f"die Karte auf Position {nummer} hat {_zahlwort(len(antworten))}."
        )
    if any(not text for text in antworten):
        raise MCPFehler(
            bei_karte(nummer, "hat eine leere Antwortmöglichkeit. Bitte gib "
                              "für jede Möglichkeit einen Text an.")
        )

    richtige = (eingabe.richtige_antwort or "").strip()
    if not richtige:
        raise MCPFehler(
            bei_karte(nummer, "hat keine richtige Antwort. Bitte gib den Text "
                              "einer der Antwortmöglichkeiten an.")
        )

    gesucht = _normalisiert(richtige)
    treffer = [stelle for stelle, text in enumerate(antworten)
               if _normalisiert(text) == gesucht]
    aufzaehlung = ", ".join(f"„{text}“" for text in antworten)
    if not treffer:
        raise MCPFehler(
            bei_karte(nummer, f"nennt als richtige Antwort „{richtige}“. Dieser "
                              f"Text steht nicht unter den Antwortmöglichkeiten "
                              f"({aufzaehlung}). Bitte gib ihn genau so an, wie "
                              f"er in der Liste steht.")
        )
    if len(treffer) > 1:
        raise MCPFehler(
            bei_karte(nummer, f"nennt als richtige Antwort „{richtige}“. Dieser "
                              f"Text kommt unter den Antwortmöglichkeiten mehrfach "
                              f"vor ({aufzaehlung}). Bitte formuliere die "
                              f"Möglichkeiten so, dass jede nur einmal vorkommt.")
        )

    erklaerung = (eingabe.erklaerung or "").strip() or None
    _laenge_pruefen(erklaerung, "erklaerung", ort)
    for text in antworten:
        _laenge_pruefen(text, "antworten", ort)

    return {
        "art": "frage",
        "vorderseite": vorderseite,
        "rueckseite": None,
        "antworten": antworten,
        "richtige_index": treffer[0],
        "erklaerung": erklaerung,
    }


def titel_pruefen(titel: str) -> str:
    beschnitten = (titel or "").strip()
    if not beschnitten:
        raise MCPFehler(
            "Das Lernpaket braucht einen Titel. Bitte gib eine kurze "
            "Überschrift an, zum Beispiel „Netzwerkgrundlagen“."
        )
    if len(beschnitten) > MAX_TITEL_LAENGE:
        raise MCPFehler(
            f"Der Titel ist mit {len(beschnitten)} Zeichen zu lang. Erlaubt "
            f"sind {MAX_TITEL_LAENGE} Zeichen – er steht als einzeilige "
            "Überschrift auf der Lernseite."
        )
    return beschnitten


def klasse_pruefen(klasse: str | None) -> str | None:
    beschnitten = (klasse or "").strip()
    if not beschnitten:
        return None
    if len(beschnitten) > MAX_KLASSE_LAENGE:
        raise MCPFehler(
            f"Die Klassenbezeichnung ist mit {len(beschnitten)} Zeichen zu "
            f"lang. Erlaubt sind {MAX_KLASSE_LAENGE} Zeichen, zum Beispiel "
            "„FS 23b“."
        )
    return beschnitten


def beschreibung_pruefen(beschreibung: str | None) -> str | None:
    beschnitten = (beschreibung or "").strip()
    if not beschnitten:
        return None
    _laenge_pruefen(beschnitten, "beschreibung", "Die Beschreibung des Lernpakets")
    return beschnitten
