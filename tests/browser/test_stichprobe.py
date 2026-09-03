"""Nur ein Teil des Pakets je Durchlauf - zufällig gezogen.

Der Anlass steht in der Spec vom 2026-08-29: Ein Lernpaket mit 203
Vokabelkarten ist ein Durchlauf, den niemand macht. Mit
`karten_pro_durchlauf` fragt eine Lernseite nur x davon ab.

Der Kern und der eigentliche Grund für diese Datei ist die Reihenfolge
zweier Schritte im Runner: erst WELCHE Karten gezogen werden, dann IN
WELCHER FOLGE sie stehen. Andersherum - erst ordnen, dann "die ersten x"
nehmen - ergäbe bei `reihenfolge: fest` bei jedem Aufruf dieselben x
Karten, und der Rest des Pakets käme nie dran. Genau das prüft
test_die_stichprobe_wechselt_auch_bei_fester_reihenfolge.
"""

import re

from tests.browser.conftest import flashcard, laden, starten

# Zwölf unterscheidbare Karten. Die Zahl ist mit der Stichprobengröße
# abgestimmt: siehe die Rechnung in test_die_stichprobe_wechselt.
KARTEN = [flashcard(f"Begriff {nummer}", f"Erklärung {nummer}") for nummer in range(1, 13)]
STICHPROBE = 4


def _fortschritt(blatt) -> str:
    return blatt.locator("#fortschritt-text").inner_text()


def _gesamtzahl_im_durchlauf(blatt) -> int:
    """Die Zahl hinter "von" in der Kopfzeile - die Länge des Durchlaufs."""
    treffer = re.search(r"von (\d+)", _fortschritt(blatt))
    assert treffer, f"Die Kopfzeile nennt keine Gesamtzahl: {_fortschritt(blatt)!r}"
    return int(treffer.group(1))


def _durchlauf_lesen(blatt, url: str) -> list[str]:
    """Ein Durchlauf von vorn bis hinten, als Liste der Vorderseiten."""
    starten(blatt, url)
    gesehen = []
    for _ in range(_gesamtzahl_im_durchlauf(blatt)):
        gesehen.append(blatt.locator("#karte-innen .seite:not(.rueckseite) .frage").inner_text())
        blatt.keyboard.press("ArrowRight")
        blatt.wait_for_timeout(120)
    return gesehen


def test_der_durchlauf_hat_nur_so_viele_karten_wie_eingestellt(seite_ohne_drehung, bundle):
    url = bundle(KARTEN, reihenfolge="fest", karten_pro_durchlauf=STICHPROBE)
    starten(seite_ohne_drehung, url)
    assert _gesamtzahl_im_durchlauf(seite_ohne_drehung) == STICHPROBE, (
        f"Der Durchlauf umfasst nicht {STICHPROBE} Karten: "
        f"{_fortschritt(seite_ohne_drehung)!r}"
    )


def test_ohne_einstellung_bleiben_alle_karten_im_durchlauf(seite_ohne_drehung, bundle):
    """Die Vorgabe ändert nichts am bisherigen Verhalten."""
    url = bundle(KARTEN, reihenfolge="fest")
    starten(seite_ohne_drehung, url)
    assert _gesamtzahl_im_durchlauf(seite_ohne_drehung) == len(KARTEN)


def test_eine_zu_grosse_stichprobe_bedeutet_alle(seite_ohne_drehung, bundle):
    """Kein Fehler, sondern die naheliegende Auslegung."""
    url = bundle(KARTEN, reihenfolge="fest", karten_pro_durchlauf=999)
    starten(seite_ohne_drehung, url)
    assert _gesamtzahl_im_durchlauf(seite_ohne_drehung) == len(KARTEN)


def test_die_stichprobe_wechselt_auch_bei_fester_reihenfolge(seite_ohne_drehung, bundle):
    """Der eigentliche Punkt dieser Datei.

    Vor der Änderung nahm der Runner bei `reihenfolge: fest` schlicht die
    ersten x Karten - bei jedem Aufruf dieselben. Hier wird geprüft, dass
    über mehrere Durchläufe nicht immer dieselbe Auswahl erscheint.

    Bewusst "nicht alle Durchläufe gleich" und nicht "diese beiden
    verschieden": Zwei Ziehungen KÖNNEN zufällig übereinstimmen. Bei 4 aus
    12 trifft eine einzelne Wiederholung mit 1/495 zu; dass alle sechs
    Läufe dieselbe Menge ergeben, hat eine Wahrscheinlichkeit von etwa
    1 zu 10^13. Ein sporadisch roter Lauf ist damit ausgeschlossen, ohne
    dass der Test etwas Falsches zusichert.
    """
    url = bundle(KARTEN, reihenfolge="fest", karten_pro_durchlauf=STICHPROBE)
    mengen = {frozenset(_durchlauf_lesen(seite_ohne_drehung, url)) for _ in range(6)}
    assert len(mengen) > 1, (
        "Sechs Durchläufe haben immer dieselben Karten gezogen. Dann werden "
        "vermutlich 'die ersten x' genommen statt zufällig gezogen - der Rest "
        "des Pakets käme nie dran."
    )


def test_bei_fester_reihenfolge_stehen_die_gezogenen_karten_in_paketreihenfolge(
    seite_ohne_drehung, bundle
):
    """"fest" gilt für die ANZEIGE, nicht für die Auswahl.

    Gezogen wird zufällig, sortiert wird danach - die vier gezogenen Karten
    müssen also in der Reihenfolge stehen, in der sie im Paket liegen.
    """
    url = bundle(KARTEN, reihenfolge="fest", karten_pro_durchlauf=STICHPROBE)
    for _ in range(3):
        gesehen = _durchlauf_lesen(seite_ohne_drehung, url)
        nummern = [int(re.search(r"\d+", text).group()) for text in gesehen]
        assert nummern == sorted(nummern), (
            f"Die gezogenen Karten stehen nicht in Paketreihenfolge: {nummern}"
        )


def test_die_startseite_nennt_beide_zahlen(seite_ohne_drehung, bundle):
    """Ohne diesen Satz wirkt "Karte 1 von 4" bei zwölf Karten wie ein Fehler."""
    url = bundle(KARTEN, reihenfolge="fest", karten_pro_durchlauf=STICHPROBE)
    laden(seite_ohne_drehung, url)
    text = seite_ohne_drehung.locator("#karte-innen").inner_text()
    assert "12" in text and str(STICHPROBE) in text, (
        f"Die Startseite nennt nicht beide Zahlen: {text!r}"
    )
