"""Die zwei Konfigurationen, fuer die es keine abgenommene Referenz gibt.

Der Prototyp (docs/design/prototyp.html) kannte nur eine: gemischte
Karten und eingeschaltete Selbsteinschaetzung. Fuer reihenfolge = "fest"
und selbsteinschaetzung = false ist deshalb die Spec die Referenz und
nicht er - und beides ist im Runner eigens gebaut (ABWEICHUNG 4 und 7).
"""

from tests.browser.conftest import (
    abdruck,
    flashcard,
    frage,
    knoepfe,
    leiste,
    ruhe_abwarten,
    sichtbare_seite,
    starten,
    umblaettern,
    warten_bis_anders,
)

MARKEN = ["KARTE-ALPHA", "KARTE-BETA", "KARTE-GAMMA", "KARTE-DELTA", "KARTE-EPSILON"]
ANTWORTEN = ["Zagreb", "Split", "Rijeka", "Dubrovnik"]


def _feste_karten() -> list[dict]:
    return [flashcard(marke, f"Antwort zu {marke}") for marke in MARKEN]


def _durchlauf(blatt, url: str) -> list[str]:
    """Einen Durchlauf blaettern und aufschreiben, welche Karte wann kommt."""
    starten(blatt, url)
    folge = []
    for nummer in range(len(MARKEN)):
        sichtbar = sichtbare_seite(blatt)
        treffer = [m for m in MARKEN if m in sichtbar]
        assert len(treffer) == 1, f"Karte {nummer + 1} zeigt {sichtbar!r}"
        folge.append(treffer[0])
        if nummer < len(MARKEN) - 1:
            vorher = abdruck(blatt)
            blatt.keyboard.press("ArrowRight")
            assert warten_bis_anders(blatt, vorher)
    return folge


def test_feste_reihenfolge_bleibt_ueber_mehrere_laeufe_stehen(seite, bundle):
    """"fest" heisst: die Reihenfolge aus der Datenbank, jedes Mal."""
    url = bundle(_feste_karten(), reihenfolge="fest")
    erster = _durchlauf(seite, url)
    zweiter = _durchlauf(seite, url)
    dritter = _durchlauf(seite, url)

    assert erster == MARKEN, f"Die Karten kommen nicht in der Reihenfolge der Datenbank: {erster}"
    assert zweiter == erster and dritter == erster, (
        f"Die Kartenreihenfolge wechselt trotz reihenfolge = fest: "
        f"{erster} / {zweiter} / {dritter}"
    )


def test_feste_reihenfolge_mischt_die_antworten_trotzdem(seite, bundle):
    """Die Spec: "Bei reihenfolge = fest bleibt die Kartenreihenfolge, die
    Antworten werden trotzdem gemischt.""" ""
    url = bundle([frage("Hauptstadt von Kroatien?", ANTWORTEN, 0)], reihenfolge="fest")

    gesehen = set()
    for _ in range(10):
        starten(seite, url)
        gesehen.add(tuple(k["text"].split("\n", 1)[1] for k in knoepfe(seite)
                          if "\n" in k["text"] and k["text"].split("\n", 1)[1] in ANTWORTEN))

    assert len(gesehen) > 1, (
        "Zehn Durchlaeufe, immer dieselbe Antwortreihenfolge - gemischt wird da nichts: "
        f"{gesehen}"
    )


def test_ohne_selbsteinschaetzung_traegt_die_rueckseite_einen_weiter_knopf(seite, bundle):
    """Ohne Selbsteinschaetzung steht laut Spec auf der Rueckseite "nur Weiter".

    Der Prototyp haengte diesen Knopf an k.gewusst !== null. Ohne
    Selbsteinschaetzung bleibt gewusst fuer immer null - die Rueckseite
    trug dann ueberhaupt kein Bedienelement mehr, und weil die
    Fussleiste am Rechner ausgeblendet ist, kam dort niemand mit der
    Maus weiter (ABWEICHUNG 7).
    """
    url = bundle([flashcard(MARKEN[0], "Sechs Monate"), flashcard(MARKEN[1], "Zwei Wochen")],
                 reihenfolge="fest", selbsteinschaetzung=False)
    starten(seite, url)

    vorher = abdruck(seite)
    seite.keyboard.press(" ")
    assert warten_bis_anders(seite, vorher), "Die Leertaste hat die Karte nicht umgedreht."
    ruhe_abwarten(seite)

    sichtbar = sichtbare_seite(seite)
    assert "Sechs Monate" in sichtbar, f"Die Rueckseite zeigt nicht die Antwort: {sichtbar!r}"
    assert "Wusste ich" not in sichtbar, (
        f"Ohne Selbsteinschaetzung darf sie nicht zur Wahl stehen: {sichtbar!r}"
    )
    assert "wusste ich" not in leiste(seite), (
        f"Die Tastenleiste bietet die Selbsteinschaetzung an: {leiste(seite)!r}"
    )

    # Ein anklickbarer Knopf auf der Rueckseite - fuer alle, die die Maus
    # benutzen. "beenden" gehoert zur Kopfzeile, nicht zur Karte.
    auf_der_karte = [k for k in knoepfe(seite) if "beenden" not in k["text"]]
    assert len(auf_der_karte) == 1, (
        f"Die Rueckseite traegt keinen einzigen Knopf: {knoepfe(seite)}"
    )
    assert "weiter" in auf_der_karte[0]["text"].lower()


def test_ohne_selbsteinschaetzung_kommt_man_ohne_maus_und_ohne_pfeiltaste_weiter(seite, bundle):
    """Am Rechner ist die Fussleiste ausgeblendet - es muss eine Taste geben."""
    url = bundle([flashcard(MARKEN[0], "Sechs Monate"), flashcard(MARKEN[1], "Zwei Wochen")],
                 reihenfolge="fest", selbsteinschaetzung=False)
    starten(seite, url)
    umblaettern(seite, "Leertaste")

    vorher = abdruck(seite)
    seite.keyboard.press("a")   # so, wie es in der Tastenleiste steht
    assert warten_bis_anders(seite, vorher), (
        "Mit der Taste aus der Leiste kommt man nicht weiter."
    )
    assert MARKEN[1] in sichtbare_seite(seite), (
        f"Es ging nicht zur naechsten Karte: {sichtbare_seite(seite)!r}"
    )


def test_ohne_selbsteinschaetzung_zaehlen_nur_die_fragen(seite, bundle):
    """Lernkarten ohne Selbsteinschaetzung koennen nicht zaehlen - es gibt keine Bewertung."""
    url = bundle([flashcard(MARKEN[0], "Sechs Monate"),
                  frage("Hauptstadt von Kroatien?", ANTWORTEN, 0)],
                 reihenfolge="fest", selbsteinschaetzung=False)
    starten(seite, url)
    umblaettern(seite, "Leertaste")   # umdrehen
    umblaettern(seite, "A")           # weiter zur Frage

    buchstabe = next(k["text"].split("\n")[0] for k in knoepfe(seite)
                     if k["text"].endswith(ANTWORTEN[0]))
    vorher = abdruck(seite)
    seite.keyboard.press(buchstabe.lower())
    assert warten_bis_anders(seite, vorher)

    vorher = abdruck(seite)
    seite.keyboard.press("a")         # zum Ergebnis
    assert warten_bis_anders(seite, vorher)

    assert "1 / 1" in sichtbare_seite(seite).replace("\n", " "), (
        f"Die Lernkarte zaehlt mit, obwohl sie nicht bewertet wurde: "
        f"{sichtbare_seite(seite)!r}"
    )
