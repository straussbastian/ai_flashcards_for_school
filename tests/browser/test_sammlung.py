"""Der Weg durch eine Sammlung, im echten Browser.

Die Routen und die Daten sind in tests/test_sammlungen.py abgedeckt. Hier
geht es um das, was danach im Browser passiert - und um einen Fehler, den
keine der anderen Ebenen sehen kann.

Beim Bauen ist genau der passiert: Die Knoepfe "weiter" und "zurueck zur
Sammlung" sind <a> und keine <button>, und ein zu spezifisches
"color: inherit" im CSS ueberschrieb das helle Gelb des Knopfes mit der
dunklen Kartentinte. Der Text stand dunkel auf dunkel - unsichtbar, aber im
DOM vorhanden. Jeder Test, der nur auf Textinhalt prueft, waere gruen
geblieben. test_die_knoepfe_sind_wirklich_lesbar prueft deshalb den
Farbabstand.
"""

from tests.browser.conftest import flashcard, laden

KARTEN = [flashcard("apple", "Apfel")]


def _leuchtkraft(farbe: str) -> float:
    """Relative Helligkeit nach WCAG, aus einem "rgb(r, g, b)"-Text."""
    zahlen = [int(teil) for teil in farbe[farbe.index("(") + 1:farbe.index(")")].split(",")[:3]]
    kanaele = []
    for wert in zahlen:
        anteil = wert / 255
        kanaele.append(anteil / 12.92 if anteil <= 0.04045 else ((anteil + 0.055) / 1.055) ** 2.4)
    r, g, b = kanaele
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _kontrast(vordergrund: str, hintergrund: str) -> float:
    hell, dunkel = sorted((_leuchtkraft(vordergrund), _leuchtkraft(hintergrund)), reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


def _durchlaufen(blatt) -> None:
    """Ein Ein-Karten-Paket von der Startseite bis zum Ergebnis."""
    blatt.get_by_role("button", name="Los geht's →").click()
    blatt.wait_for_timeout(300)
    blatt.keyboard.press(" ")          # umdrehen
    blatt.wait_for_timeout(400)
    blatt.keyboard.press("A")          # gewusst -> Ergebnis
    blatt.wait_for_timeout(600)


def test_die_sammlung_fuehrt_zum_naechsten_paket(seite_ohne_drehung, sammlung):
    """Aus dreizehn Einzelbesuchen wird ein Weg."""
    url, pakete = sammlung(
        "Englisch komplett",
        [("Englisch 1", KARTEN), ("Englisch 2", KARTEN)],
    )
    laden(seite_ohne_drehung, f"{url}/{pakete[0]}")
    _durchlaufen(seite_ohne_drehung)

    seite_ohne_drehung.get_by_role("link", name="weiter").click()
    seite_ohne_drehung.wait_for_timeout(500)

    assert seite_ohne_drehung.url.endswith(f"{url.rsplit('/', 1)[-1]}/{pakete[1]}"), (
        f"Der Weiter-Knopf fuehrt nicht zum zweiten Paket: {seite_ohne_drehung.url}"
    )
    assert "Englisch 2" in seite_ohne_drehung.locator("#karte-innen").inner_text()


def test_zurueck_fuehrt_zur_sammlung(seite_ohne_drehung, sammlung):
    url, pakete = sammlung("Englisch komplett", [("Englisch 1", KARTEN)])
    laden(seite_ohne_drehung, f"{url}/{pakete[0]}")
    _durchlaufen(seite_ohne_drehung)

    seite_ohne_drehung.get_by_role("link", name="zurück").click()
    seite_ohne_drehung.wait_for_timeout(500)
    assert seite_ohne_drehung.url.rstrip("/").endswith(url.rsplit("/", 1)[-1])
    # ".karte-innen" als Klasse und nicht "#karte-innen": Die Sammlungsseite
    # kommt ohne JavaScript aus und braucht deshalb keine ID, an der ein
    # Skript sie fassen koennte. Die Klasse tragen beide Seiten.
    assert "Englisch komplett" in seite_ohne_drehung.locator(".karte-innen").inner_text()


def test_beim_letzten_paket_gibt_es_kein_weiter(seite_ohne_drehung, sammlung):
    url, pakete = sammlung("Kurz", [("Einziges", KARTEN)])
    laden(seite_ohne_drehung, f"{url}/{pakete[0]}")
    _durchlaufen(seite_ohne_drehung)

    beschriftungen = seite_ohne_drehung.locator(".ergebnis-knoepfe > *").all_inner_texts()
    assert not any("weiter" in b for b in beschriftungen), (
        f"Beim letzten Paket steht trotzdem ein Weiter-Knopf: {beschriftungen}"
    )
    assert any("zurück" in b for b in beschriftungen), (
        "Der Rueckweg zur Sammlung fehlt."
    )


def test_ohne_sammlung_bleibt_der_ergebnisbildschirm_unveraendert(seite_ohne_drehung, bundle):
    """Die einzelne Adresse darf sich durch die Sammlungen nicht aendern."""
    url = bundle(KARTEN, titel="Einzeln")
    laden(seite_ohne_drehung, url)
    _durchlaufen(seite_ohne_drehung)

    beschriftungen = seite_ohne_drehung.locator(".ergebnis-knoepfe > *").all_inner_texts()
    assert not any("weiter" in b or "zurück" in b for b in beschriftungen), (
        f"Ohne Sammlung stehen trotzdem Sammlungs-Knoepfe da: {beschriftungen}"
    )


def test_die_knoepfe_sind_wirklich_lesbar(seite_ohne_drehung, sammlung):
    """Text im DOM heisst nicht Text auf dem Schirm.

    Genau hier ging beim Bauen etwas schief: Ein "color: inherit" auf a.knopf
    war spezifischer als .knopf und ersetzte dessen helles Gelb durch die
    dunkle Kartentinte - auf dem dunklen Knopf war der Text damit
    unsichtbar. Der DOM-Inhalt stimmte die ganze Zeit.

    Geprueft wird deshalb der Kontrast nach WCAG. 4.5:1 ist die Schwelle fuer
    Fliesstext; diese Knoepfe sind fetter und groesser, aber die strengere
    Zahl schadet nicht und laesst keinen Spielraum fuer "sieht schon ok aus".
    """
    url, pakete = sammlung("Englisch komplett",
                           [("Englisch 1", KARTEN), ("Englisch 2", KARTEN)])
    laden(seite_ohne_drehung, f"{url}/{pakete[0]}")
    _durchlaufen(seite_ohne_drehung)

    knoepfe = seite_ohne_drehung.locator(".ergebnis-knoepfe > *")
    assert knoepfe.count() == 3, "Erwartet werden weiter, nochmal und zurueck."

    geprueft = 0

    for nummer in range(knoepfe.count()):
        einer = knoepfe.nth(nummer)
        text = einer.inner_text().strip()
        assert text, f"Knopf {nummer} traegt keinen Text."

        farben = einer.evaluate("""(el) => {
          const s = getComputedStyle(el);
          return { vorn: s.color, hinten: s.backgroundColor };
        }""")

        # Nur bei DECKENDEM Hintergrund gerechnet. Die leisen Knoepfe legen
        # eine Farbe mit 12 % Deckkraft ueber den Zettel; ihre wirksame
        # Hintergrundfarbe ist der Zettel darunter, und der traegt einen
        # Verlauf - getComputedStyle liefert dafuer keine Farbe, sondern die
        # Verlaufsangabe. Eine Rechnung, die den durchsichtigen Wert wie
        # einen deckenden behandelt, meldet 1.0:1 fuer einen bestens
        # lesbaren Knopf. Genau das ist beim ersten Anlauf passiert.
        #
        # Der Fehler, um den es geht, sitzt ohnehin beim deckenden Knopf: Er
        # traegt die dunkle Kartentinte als Hintergrund, und ein zu
        # spezifisches "color: inherit" faerbte den Text in dieselbe Tinte.
        if not farben["hinten"].startswith("rgba"):
            verhaeltnis = _kontrast(farben["vorn"], farben["hinten"])
            assert verhaeltnis >= 4.5, (
                f"Der Knopf „{text}“ hat nur einen Kontrast von "
                f"{verhaeltnis:.1f}:1 ({farben['vorn']} auf "
                f"{farben['hinten']}) - der Text ist kaum oder gar nicht zu "
                "lesen."
            )
            geprueft += 1

    assert geprueft, (
        "Kein Knopf hatte einen deckenden Hintergrund - dann prueft dieser "
        "Test nichts. Sind die Knopffarben umgestellt worden?"
    )
