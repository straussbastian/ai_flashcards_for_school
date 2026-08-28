"""Lange Inhalte bleiben in der Karte - und ihr Anfang bleibt erreichbar.

Erlaubt sind bis 5000 Zeichen je Feld (app/markdown.py, MAX_LAENGE). Der
Prototyp kannte nur kurze Karten, deshalb konnte er beides nicht zeigen:

  * Ohne Ueberlauf lief der Inhalt sichtbar aus der Karte heraus, ueber
    Fusszeile und Tastenleiste hinweg.
  * Mit Ueberlauf, aber ohne "safe" bei der Zentrierung ragte er nach
    BEIDEN Seiten hinaus - der Anfang lag vor dem Anfang des
    Scrollbereichs und war mit keiner Geste mehr erreichbar. Nachgemessen
    waren es 336 px (Commit ca7d87d).

Der zweite Fall ist der heimtueckische: Die Karte sieht heil aus, nur der
Anfang der Antwort fehlt. Deshalb prueft dieser Test ausdruecklich, dass
bei scrollTop = 0 nichts oberhalb des Sichtfensters liegt.
"""

import time

from tests.browser.conftest import (
    abdruck,
    flashcard,
    frage,
    laden,
    warten_bis_anders,
)

ANFANG = "ANFANGSMARKE"
ENDE = "ENDMARKE"

# Knapp unter der Grenze von 5000 Zeichen, in Absaetzen wie echtes
# Markdown. Der Anfang und das Ende sind eindeutig wiederzufinden.
_ABSATZ = ("Die Probezeit darf hoechstens sechs Monate dauern und laesst sich "
           "waehrenddessen mit einer Frist von zwei Wochen kuendigen. ")
LANGE_RUECKSEITE = (
    ANFANG + "\n\n" + "\n\n".join(_ABSATZ * 3 for _ in range(11)) + "\n\n" + ENDE
)
# Die Datenbank laesst nicht mehr als MAX_MARKDOWN_LAENGE hinein; ein zu
# langer Text schluege beim Anlegen fehl und nicht dort, wo er gemeint ist.
assert 4000 < len(LANGE_RUECKSEITE) <= 5000, len(LANGE_RUECKSEITE)

LANGES_WORT = ("Donaudampfschifffahrtselektrizitaetenhauptbetriebswerk"
               "bauunterbeamtengesellschaftsvorstandsstellvertreterposten")

CODEBLOCK = (
    "Und so sieht es im Quelltext aus:\n\n"
    "```\n"
    "    ergebnis = berechne(erste_zahl, zweite_zahl, dritte_zahl, "
    "vierte_zahl, fuenfte_zahl, sechste_zahl)\n"
    "```\n"
)


def _ruhe_abwarten(blatt) -> None:
    """Wartet, bis die Drehung der Karte zu Ende ist.

    Waehrend der Drehung (0,55 s) sind die gemessenen Rechtecke schraeg
    und damit unbrauchbar. Gewartet wird auf den Stillstand der
    Verwandlung, nicht auf eine feste Zeit - unter
    prefers-reduced-motion faellt die Drehung ganz weg, dann ist es
    sofort so weit.
    """
    letzte, gleich, ende = None, 0, time.monotonic() + 5
    while time.monotonic() < ende:
        jetzt = blatt.evaluate(
            "() => getComputedStyle(document.getElementById('karte-innen')).transform"
        )
        gleich = gleich + 1 if jetzt == letzte else 0
        letzte = jetzt
        if gleich >= 3:
            return
        blatt.wait_for_timeout(50)
    raise AssertionError("Die Karte kommt nicht zur Ruhe.")


# Misst den Scrollbereich, in dem der Inhalt der Rueckseite steht: Wo
# scrollt es, liegt das innerhalb der Karte, und was liegt bei scrollTop
# = 0 ueber dem oberen Rand?
_MESSUNG = """() => {
  const marke = [...document.querySelectorAll('#karte-innen *')].filter(
    (e) => e.textContent.includes(MARKE) &&
           ![...e.children].some((c) => c.textContent.includes(MARKE))).pop();
  if (!marke) return { gefunden: false };
  let kasten = marke.parentElement;
  while (kasten && !(kasten.scrollHeight > kasten.clientHeight + 1 &&
         /auto|scroll/.test(getComputedStyle(kasten).overflowY))) {
    kasten = kasten.parentElement;
  }
  if (!kasten) return { gefunden: true, scrollt: false };
  const karte = document.getElementById('karte').getBoundingClientRect();
  const k = kasten.getBoundingClientRect();
  kasten.scrollTop = 0;
  const oberkanten = [...kasten.children].map((e) => e.getBoundingClientRect().top);
  return {
    gefunden: true,
    scrollt: true,
    in_der_karte: k.top >= karte.top - 1 && k.bottom <= karte.bottom + 1 &&
                  k.left >= karte.left - 1 && k.right <= karte.right + 1,
    hoechste_oberkante_ueber_dem_rand: Math.round(k.top - Math.min(...oberkanten)),
    seite_scrollt_seitwaerts:
      document.scrollingElement.scrollWidth > document.scrollingElement.clientWidth + 1,
  };
}""".replace("MARKE", repr(ANFANG).replace("'", '"'))


def test_lange_rueckseite_scrollt_in_der_karte_und_beginnt_am_anfang(seite, bundle):
    url = bundle([flashcard("Wie lang darf die Probezeit sein?", LANGE_RUECKSEITE)])
    laden(seite, url)
    vorher = abdruck(seite)
    seite.keyboard.press("Enter")
    assert warten_bis_anders(seite, vorher)

    vorher = abdruck(seite)
    seite.keyboard.press(" ")
    assert warten_bis_anders(seite, vorher), "Die Leertaste hat die Karte nicht umgedreht."
    _ruhe_abwarten(seite)

    messung = seite.evaluate(_MESSUNG)
    assert messung["gefunden"], "Der Anfang der Rueckseite steht gar nicht auf der Seite."
    assert messung["scrollt"], (
        "Die lange Rueckseite scrollt nirgends - dann laeuft sie aus der Karte heraus."
    )
    assert messung["in_der_karte"], "Der Scrollbereich liegt nicht innerhalb der Karte."
    assert messung["hoechste_oberkante_ueber_dem_rand"] <= 1, (
        "Bei scrollTop = 0 liegt der Anfang der Rueckseite "
        f"{messung['hoechste_oberkante_ueber_dem_rand']} px oberhalb des Sichtfensters "
        "und ist mit keiner Geste erreichbar (siehe Commit ca7d87d)."
    )
    assert not messung["seite_scrollt_seitwaerts"], "Die Seite scrollt waagerecht."

    # Das Ende ist durch Scrollen erreichbar - der Inhalt ist also
    # vollstaendig da und nicht abgeschnitten.
    erreicht = seite.evaluate("""(ende) => {
      const kasten = [...document.querySelectorAll('#karte-innen, #karte-innen *')]
        .find((e) => e.scrollHeight > e.clientHeight + 1 &&
                     /auto|scroll/.test(getComputedStyle(e).overflowY));
      kasten.scrollTop = kasten.scrollHeight;
      const k = kasten.getBoundingClientRect();
      return [...kasten.querySelectorAll('*')].some((e) => {
        if (!e.textContent.includes(ende)) return false;
        const r = e.getBoundingClientRect();
        return r.top >= k.top - 1 && r.bottom <= k.bottom + 1;
      });
    }""", ENDE)
    assert erreicht, "Das Ende der langen Rueckseite ist auch durch Scrollen nicht zu sehen."


def _seitwaerts(blatt) -> int:
    """Um wie viele Pixel die Seite selbst waagerecht scrollt."""
    return blatt.evaluate(
        "() => document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth"
    )


def test_langes_wort_und_codeblock_lassen_die_seite_nicht_seitwaerts_scrollen(seite, bundle):
    """Die Spec: "die Seite selbst scrollt nie waagerecht"."""
    url = bundle([
        flashcard(f"Ein Wort ohne Fuge: {LANGES_WORT}", f"Und die Antwort: {LANGES_WORT}"),
        frage(CODEBLOCK, [f"Ja, {LANGES_WORT}", "Nein"], 1, erklaerung=CODEBLOCK),
    ], reihenfolge="fest")

    laden(seite, url)
    assert _seitwaerts(seite) <= 1, "Schon die Startseite scrollt waagerecht."

    vorher = abdruck(seite)
    seite.keyboard.press("Enter")
    assert warten_bis_anders(seite, vorher)
    assert _seitwaerts(seite) <= 1, "Die Vorderseite mit dem langen Wort scrollt waagerecht."

    vorher = abdruck(seite)
    seite.keyboard.press(" ")
    assert warten_bis_anders(seite, vorher)
    _ruhe_abwarten(seite)
    assert _seitwaerts(seite) <= 1, "Die Rueckseite mit dem langen Wort scrollt waagerecht."

    vorher = abdruck(seite)
    seite.keyboard.press("ArrowRight")
    assert warten_bis_anders(seite, vorher)
    assert _seitwaerts(seite) <= 1, "Die Frage mit dem Codeblock scrollt waagerecht."

    vorher = abdruck(seite)
    seite.keyboard.press("b")
    assert warten_bis_anders(seite, vorher)
    _ruhe_abwarten(seite)
    assert _seitwaerts(seite) <= 1, "Die Aufloesung mit dem Codeblock scrollt waagerecht."


def test_langes_wort_scrollt_auch_am_handy_nicht_seitwaerts(handy, bundle):
    url = bundle([flashcard(f"Ein Wort ohne Fuge: {LANGES_WORT}", CODEBLOCK)])
    laden(handy, url)
    assert _seitwaerts(handy) <= 1, "Die Startseite scrollt am Handy waagerecht."

    handy.get_by_role("button", name="Los geht's").click()
    handy.wait_for_timeout(300)
    assert _seitwaerts(handy) <= 1, "Die Karte scrollt am Handy waagerecht."

    handy.get_by_role("button", name="Umdrehen").click()
    _ruhe_abwarten(handy)
    assert _seitwaerts(handy) <= 1, "Die Rueckseite scrollt am Handy waagerecht."
