"""Die Karte nutzt den vorhandenen Platz, bevor sie scrollt.

Der Befund aus dem Praxistest: Nahezu jede Rueckseite scrollte, obwohl
ringsum Bildschirm frei war. Nachgemessen am Handy (390x844): Die
Rueckseite blieb auf 272 px stehen, ihr Inhalt brauchte 710 px, erlaubt
waren 612 px - 572 px Bildschirm lagen ungenutzt daneben. Sichtbare Folge
waren abgeschnittene Knoepfe am unteren Kartenrand.

Die Ursache war die Positionierung: Die Rueckseite lag mit
`position: absolute; inset: 0` auf der Vorderseite und uebernahm damit
deren Hoehe. Bei kurzer Frage und langer Antwort - dem Normalfall - bekam
der lange Text die Hoehe des kurzen. Die max-height kam auf der
Rueckseite nie zum Zuge.

Die Zusage, die dieser Test festhaelt, ist bewusst als Ungleichung
formuliert und nicht als feste Pixelzahl: Eine Karte darf erst scrollen,
wenn sie ihre Hoehengrenze ausgeschoepft hat. Das bleibt richtig, wenn
sich Schriftgroessen, Zeilenumbrueche oder die Grenze selbst aendern.
"""

from tests.browser.conftest import flashcard, laden, ruhe_abwarten, warten_bis_anders

KURZ = "Was ist Verzug?"
LANG = (
    "**Verzug** tritt ein, wenn der Schuldner nach Faelligkeit und Mahnung "
    "nicht leistet.\n\n"
    "- Nur im B2B kommen die 40 Euro Pauschale dazu\n"
    "- Pro Rechnung, nicht pro Mahnung\n"
    "- Gegenueber Verbrauchern unzulaessig\n\n"
) * 4

# Liest die aktuell sichtbare Kartenseite aus: Hoehe, Platzbedarf, Grenze.
_MESSUNG = """() => {
  const karte = document.querySelector('#karte');
  const innen = document.querySelector('#karte-innen');
  const aktiv = karte.classList.contains('gedreht')
    ? innen.querySelector('.rueckseite')
    : innen.querySelector('.seite:not(.rueckseite)');
  const cs = getComputedStyle(aktiv);
  return {
    hoehe:   Math.round(aktiv.getBoundingClientRect().height),
    noetig:  aktiv.scrollHeight,
    grenze:  Math.round(parseFloat(cs.maxHeight)),
    scrollt: aktiv.scrollHeight > aktiv.clientHeight + 1,
  };
}"""


def test_die_rueckseite_nutzt_den_platz_bevor_sie_scrollt(handy, bundle):
    url = bundle([flashcard(KURZ, LANG)])
    laden(handy, url)

    vorher = _abdruck(handy)
    handy.keyboard.press("Enter")
    assert warten_bis_anders(handy, vorher)

    vorher = _abdruck(handy)
    handy.keyboard.press(" ")
    assert warten_bis_anders(handy, vorher), "Die Leertaste hat die Karte nicht umgedreht."
    ruhe_abwarten(handy)

    m = handy.evaluate(_MESSUNG)
    if m["scrollt"]:
        assert m["hoehe"] >= m["grenze"] - 2, (
            f"Die Rueckseite scrollt schon bei {m['hoehe']} px, obwohl sie bis "
            f"{m['grenze']} px wachsen duerfte - {m['grenze'] - m['hoehe']} px "
            f"Bildschirm bleiben ungenutzt. Ihr Inhalt braucht {m['noetig']} px."
        )
    else:
        assert m["hoehe"] >= min(m["noetig"], m["grenze"]) - 2, (
            f"Die Rueckseite ist {m['hoehe']} px hoch, ihr Inhalt braucht "
            f"{m['noetig']} px."
        )


def _abdruck(blatt) -> str:
    from tests.browser.conftest import abdruck
    return abdruck(blatt)
