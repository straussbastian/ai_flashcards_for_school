"""Zwei kleine Zusagen: Der Fokus geht nie verloren, und ein leeres Bundle sagt das.

Zum Fokus verlangt die Spec zweierlei: "Fokus wandert beim Kartenwechsel
auf die neue Karte" und "Der Tastaturfokus darf nie verloren gehen". Der
Prototyp ersetzte beim Blaettern den Karteninhalt, ohne den Fokus
mitzunehmen: Lag er auf einem Knopf der Karte, war der nach dem Ersetzen
fort und der Fokus landete auf <body> - Tab faengt danach wieder ganz
vorn an, und eine Sprachausgabe verliert die Stelle (ABWEICHUNG 9).
"""

from tests.browser.conftest import (
    abdruck,
    flashcard,
    frage,
    knoepfe,
    laden,
    leiste,
    ruhig_bleiben,
    starten,
    umblaettern,
)


def _fokus(blatt) -> str:
    """Wo der Tastaturfokus steht - als Beschreibung, nicht als Knoten."""
    return blatt.evaluate("""() => {
      const a = document.activeElement;
      if (!a) return 'nirgends';
      if (a === document.body) return 'body';
      return a.tagName.toLowerCase() + (a.id ? '#' + a.id : '');
    }""")


def test_der_fokus_bleibt_beim_blaettern_in_der_seite(seite, bundle):
    url = bundle([flashcard("Erste Karte", "Erste Antwort"),
                  frage("Zweite Karte", ["neun", "elf"], 1),
                  flashcard("Dritte Karte", "Dritte Antwort")], reihenfolge="fest")
    starten(seite, url)

    for schritt, taste in enumerate(["→", "→", "←", "←", "→"], start=1):
        umblaettern(seite, taste)
        assert _fokus(seite) not in ("body", "nirgends"), (
            f"Nach Schritt {schritt} ({taste}) liegt der Tastaturfokus auf <body>. "
            "Tab faengt dann wieder ganz vorn an."
        )


def test_leeres_bundle_erklaert_sich_und_bietet_nichts_an(seite, bundle):
    """Die Spec: "Startseite erklaert, dass noch keine Karten hinterlegt sind,
    kein Start-Button"."""
    url = bundle([], titel="Noch nichts drin")
    laden(seite, url)

    # Kleingeschrieben verglichen: Der Hinweis steht per CSS in
    # Grossbuchstaben, und innerText liefert ihn so, wie er zu lesen ist.
    sichtbar = seite.locator("#karte-innen").inner_text()
    assert "noch keine karten" in sichtbar.lower(), (
        f"Der Hinweis auf das leere Bundle fehlt: {sichtbar!r}"
    )
    assert knoepfe(seite) == [], f"Es gibt etwas zu druecken: {knoepfe(seite)}"
    assert leiste(seite) == "", (
        f"Die Tastenleiste nennt eine Taste, die es nicht gibt: {leiste(seite)!r}"
    )

    vorher = abdruck(seite)
    seite.keyboard.press("Enter")
    assert ruhig_bleiben(seite, vorher), "Die Eingabetaste hat etwas bewirkt."
