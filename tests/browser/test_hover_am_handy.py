"""Kein Antwortknopf darf sich am Handy von den anderen abheben.

Der Befund kam aus dem Praxistest: Auf einer noch unbeantworteten Frage
stand eine der vier Antworten heller da als die uebrigen. Das sieht aus
wie ein Hinweis auf die richtige Loesung - und traf, weil das Mischen
zufaellig ist, genauso oft die falsche.

Die Ursache war eine Hover-Regel ohne Schutz: `.antwort:hover` galt auch
auf Geraeten, die gar keinen Mauszeiger haben. Auf iOS bleibt der
Hover-Zustand am zuletzt beruehrten Element haengen, bis anderswo
getippt wird; beim Kartenwechsel wird die Antwortliste neu gebaut, und
der Knopf, der an die zuletzt beruehrte Stelle rutscht, erbt ihn.

Der Test prueft die Bedingung selbst und nicht das CSS: Auf einem Geraet,
das `(hover: none)` meldet, darf ein Zeiger ueber einem Knopf dessen
Aussehen nicht veraendern.
"""

from tests.browser.conftest import frage, laden

FRAGE = "Ab wann ist der Kunde in Verzug?"
ANTWORTEN = [
    "Ab dem Tag nach der Faelligkeit",
    "Erst ab der zweiten Mahnung",
    "Sofort ab Rechnungsstellung",
    "Erst nachdem eine Mahnung zugegangen ist",
]


def _hintergruende(blatt) -> list[str]:
    return blatt.locator(".antwort").evaluate_all(
        "knoepfe => knoepfe.map(k => getComputedStyle(k).backgroundColor)"
    )


def test_am_handy_hebt_sich_keine_antwort_von_den_anderen_ab(handy, bundle):
    url = bundle([frage(FRAGE, ANTWORTEN, 0)], reihenfolge="fest")
    laden(handy, url)

    # Die Voraussetzung des Tests, ausdruecklich geprueft: Ohne sie
    # pruefte er auf einem Rechner-Viewport etwas ganz anderes und waere
    # gruen, ohne den Befund abzudecken.
    assert handy.evaluate("matchMedia('(hover: none)').matches"), (
        "Dieses Geraet meldet einen Mauszeiger - dann prueft der Test nicht, "
        "was er pruefen soll."
    )

    handy.get_by_role("button", name="Los geht's").click()
    handy.locator(".antwort").first.wait_for()

    vorher = _hintergruende(handy)
    assert len(set(vorher)) == 1, (
        f"Schon ohne Zutun sehen die Antworten verschieden aus: {vorher}"
    )

    # Genau das, was iOS nach einer Beruehrung zurueticklaesst: ein Zeiger,
    # der ueber einem der Knoepfe steht.
    handy.locator(".antwort").nth(3).hover()
    handy.wait_for_timeout(300)      # die Regel hat eine Uebergangszeit

    nachher = _hintergruende(handy)
    assert len(set(nachher)) == 1, (
        "Eine Antwort hebt sich von den anderen ab, obwohl das Geraet keinen "
        f"Mauszeiger hat. Das sieht aus wie ein Hinweis auf die Loesung: {nachher}"
    )
