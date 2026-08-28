"""Die eine Regel, deren Bruch alles kostet.

Genau vier Felder tragen HTML - vorderseite, rueckseite, erklaerung und
beschreibung -, und dieses HTML kommt aus app/markdown.rendern(), also
serverseitig gesaeubert. Alles andere ist Klartext: die Antworttexte, der
Titel und die Klasse. Sie laufen nicht durch rendern(); ein als HTML
eingesetzter Antworttext waere ein Cross-Site-Scripting auf einer Seite,
die Schuelerinnen und Schueler ohne Anmeldung aufrufen.

Der einzige Schutz sind sechs richtig gewaehlte Funktionsaufrufe im
Runner (knoten() statt htmlKnoten()). Diese Datei prueft sie an jeder
Stelle, an der ein Antworttext auf den Schirm kommt.

Warum nicht nur "es ist nichts passiert": Die Inhaltsrichtlinie
(app/sicherheit.py) verbietet dem Browser ohnehin, ein Ereignisattribut
auszufuehren. Ein eingeschleustes <img> WUERDE also nichts tun - und ein
Test, der nur darauf schaut, waere gruen, auch wenn der Runner den
Antworttext als HTML einsetzte. Deshalb prueft jede Stelle drei Dinge:
kein zusaetzliches Element im Baum, die Zeichen stehen sichtbar als Text
da, und ausgefuehrt wurde auch nichts.
"""

from tests.browser.conftest import (
    abdruck,
    druecken,
    frage,
    knoepfe,
    warten_bis_anders,
)

# Zwei Angriffe, die sich im Baum nachweisen lassen: Der erste bringt ein
# <img> mit, der zweite bricht aus einem Attribut aus und bringt ein
# <script> mit. Beide setzen dieselbe Markierung, falls sie doch laufen.
IMG = '<img src=x onerror="window.__gehackt=1">'
SKRIPT = '"><script>window.__gehackt=1</script>'
GIFT = f"Falsch {IMG} {SKRIPT}"


def _keine_einschleusung(blatt, wo: str, sichtbar: list[str]) -> None:
    """Die drei Pruefungen an einer Stelle."""
    eingeschleust = blatt.evaluate(
        "() => [...document.querySelectorAll('#karte-innen img, #karte-innen script')]"
        ".map((e) => e.outerHTML)"
    )
    assert eingeschleust == [], (
        f"{wo}: Es steht ein eingeschleustes Element im Baum: {eingeschleust}"
    )

    text = blatt.locator("#karte-innen").inner_text()
    for stueck in sichtbar:
        assert stueck in text, (
            f"{wo}: {stueck!r} steht nicht sichtbar als Text da. Gesehen: {text!r}"
        )

    assert blatt.evaluate("() => window.__gehackt") is None, (
        f"{wo}: Eingeschleuster Code wurde ausgefuehrt."
    )


def test_antworttext_titel_und_klasse_bleiben_klartext(seite, bundle, meldungen):
    """Der ganze Weg: Startseite, Frage, Aufloesung, Ergebnis mit Fehlerliste."""
    url = bundle(
        [frage("Welche Antwort ist falsch?", ["Richtig ist harmlos", GIFT], 0)],
        titel=f"Titel {IMG} {SKRIPT}",
        klasse=IMG,
    )

    # --- Startseite: Titel und Klasse ---
    seite.goto(url)
    seite.wait_for_selector("#tastenleiste")
    _keine_einschleusung(seite, "Startseite", [IMG, SKRIPT])

    # --- Vorderseite der Frage: die Antworttexte ---
    vorher = abdruck(seite)
    seite.keyboard.press("Enter")
    assert warten_bis_anders(seite, vorher)
    _keine_einschleusung(seite, "Frage", [GIFT])

    # --- Rueckseite: "Deine Antwort" und die Loesung ---
    giftig = [k for k in knoepfe(seite) if GIFT in k["text"]]
    assert len(giftig) == 1, f"Die vergiftete Antwort ist nicht zu sehen: {knoepfe(seite)}"
    vorher = abdruck(seite)
    druecken(seite, giftig[0]["text"].split()[0])
    assert warten_bis_anders(seite, vorher)
    _keine_einschleusung(seite, "Aufloesung", [GIFT])

    # --- Ergebnis mit Fehlerliste: die Antworttexte kommen erneut ---
    vorher = abdruck(seite)
    druecken(seite, "A")
    assert warten_bis_anders(seite, vorher)
    assert "Nur die Fehler" in abdruck(seite), (
        "Die falsch beantwortete Frage steht nicht in der Fehlerliste."
    )
    _keine_einschleusung(seite, "Ergebnis", [GIFT])

    # Kein Wort ueber die Markierung in der Konsole: Waere das Skript
    # gelaufen und haette es dabei etwas gemeldet, stuende es hier.
    assert not [m for m in meldungen["konsole"] if "gehackt" in m], meldungen["konsole"]
