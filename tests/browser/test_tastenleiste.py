"""Die Tastenleiste gegen die Knoepfe, die es wirklich gibt.

Die Spec: "Die Tastenleiste zeigt nur, was gerade wirklich geht. Eine
Leiste, die Tasten nennt, die gerade nichts tun, erzieht dazu, sie nicht
mehr zu lesen." Genau das ist im Prototyp zweimal passiert: Im Ergebnis
ohne Fehler bot die Leiste "B nur die Fehler" an, obwohl es diesen Knopf
dort gar nicht gibt, und bei einer Frage mit zwei Antworten nannte sie C
und D.

Ein Test mit einer gepflegten Liste von Zustaenden haette genau den
naechsten Zustand nicht gehabt, der dazukommt. Deshalb pflegt dieser
Test keine Liste, sondern LAEUFT DIE ZUSTAENDE AB: Er beginnt auf der
Startseite, liest die Leiste, drueckt jede genannte Taste und macht im
Zustand dahinter weiter, bis nichts Neues mehr kommt. Ein neuer Zustand
kommt damit von selbst dazu, sobald man ihn erreichen kann.

Geprueft wird in jedem gefundenen Zustand:

  * Jede Taste, die die Leiste nennt, bewirkt auch etwas (das steckt im
    Ablaufen selbst: Jeder Schritt besteht darauf, dass sich danach
    etwas geaendert hat).
  * Die Buchstaben in der Leiste sind genau die Buchstaben auf den
    Knoepfen, die man in diesem Moment tatsaechlich anklicken kann -
    keiner zu viel, keiner zu wenig.
  * Nennt die Leiste eine Taste, die dieser Test nicht kennt, schlaegt
    er fehl, statt sie zu uebergehen (siehe leistentasten()).
"""

import pytest

from tests.browser.conftest import (
    TASTENNAMEN,
    abdruck,
    druecken,
    flashcard,
    frage,
    knoepfe,
    laden,
    leiste,
    leistentasten,
    warten_bis_anders,
)

# Genug fuer jeden Weg durch ein Bundle mit zwei Karten (starten,
# umdrehen, einschaetzen, antworten, weiter, zurueck) mit Luft nach oben.
TIEFE = 10
# Reissleine gegen eine Zustandsexplosion, die niemand bemerkt hat. Wird
# sie erreicht, meldet der Test das ausdruecklich, statt still weniger zu
# pruefen.
HOECHSTZAHL = 120


def _buchstaben_der_leiste(blatt) -> set[str]:
    return {t for t in leistentasten(blatt) if len(t) == 1 and t.isalpha()}


def _buchstaben_der_knoepfe(blatt) -> set[str]:
    """Die Kuerzel, die sichtbar auf den erreichbaren Knoepfen stehen."""
    ergebnis = set()
    for beschriftung in knoepfe(blatt):
        woerter = beschriftung.split()
        if woerter and len(woerter[0]) == 1 and woerter[0].isalpha() \
                and woerter[0] in TASTENNAMEN:
            ergebnis.add(woerter[0])
    return ergebnis


def _pruefen(blatt, pfad: list[str]) -> None:
    aus_der_leiste = _buchstaben_der_leiste(blatt)
    auf_den_knoepfen = _buchstaben_der_knoepfe(blatt)
    assert aus_der_leiste == auf_den_knoepfen, (
        f"Leiste und Knoepfe sagen Verschiedenes.\n"
        f"  Weg dorthin: {pfad}\n"
        f"  Leiste:      {leiste(blatt)!r} -> {sorted(aus_der_leiste)}\n"
        f"  Knoepfe:     {knoepfe(blatt)} -> {sorted(auf_den_knoepfen)}\n"
        f"  Nur in der Leiste: {sorted(aus_der_leiste - auf_den_knoepfen)} "
        f"(genannt, aber nicht da)\n"
        f"  Nur auf Knoepfen:  {sorted(auf_den_knoepfen - aus_der_leiste)} "
        f"(da, aber nicht genannt)"
    )


def _hinsteuern(blatt, url: str, pfad: list[str]) -> bool:
    """Von vorn laden und den Weg noch einmal gehen.

    Gibt False zurueck, wenn der Weg diesmal nicht gangbar ist: Die
    Antworten werden bei jedem Durchlauf neu gemischt, ein Buchstabe kann
    also einmal die richtige und einmal die falsche Antwort treffen. Der
    Zweig faellt dann aus, geprueft wird in dem Zustand, den es gibt.
    """
    laden(blatt, url)
    for taste in pfad:
        if taste not in leistentasten(blatt):
            return False
        vorher = abdruck(blatt)
        druecken(blatt, taste)
        assert warten_bis_anders(blatt, vorher), (
            f"Die Tastenleiste nennt {taste!r}, aber die Taste bewirkt nichts.\n"
            f"  Weg dorthin: {pfad}\n  Zustand:\n{vorher}"
        )
    return True


def _ablaufen(blatt, url: str) -> dict[str, list[str]]:
    """Alle erreichbaren Zustaende besuchen und in jedem die Leiste pruefen."""
    # Ohne Drehung gibt es nichts abzuwarten: Die Rueckseite ist sofort
    # da, ein Klick in die Kartenmitte trifft sie sofort. Ein Ablauf mit
    # Drehung muesste nach jedem Schritt auf deren Ende warten - bei
    # mehreren hundert Schritten waere das der groesste Posten.
    assert blatt.evaluate("() => matchMedia('(prefers-reduced-motion: reduce)').matches"), (
        "Diese Erkundung braucht eine Seite ohne Drehung (Fixture seite_ohne_drehung)."
    )
    besucht: dict[str, list[str]] = {}

    def gehe(pfad: list[str]) -> None:
        if len(besucht) >= HOECHSTZAHL or not _hinsteuern(blatt, url, pfad):
            return
        zustand = abdruck(blatt)
        if zustand in besucht:
            return
        besucht[zustand] = pfad
        _pruefen(blatt, pfad)
        if len(pfad) >= TIEFE:
            return
        for taste in leistentasten(blatt):
            gehe(pfad + [taste])

    gehe([])
    assert len(besucht) < HOECHSTZAHL, (
        f"Die Erkundung hat die Reissleine bei {HOECHSTZAHL} Zustaenden gezogen. "
        "Entweder ist das Bundle zu gross geworden oder ein Zustand wiederholt "
        "sich nicht mehr - beides will angeschaut werden."
    )
    return besucht


# Zwei Karten reichen fuer alle geforderten Zustaende: Startseite,
# Kartenvorderseite, Flashcard-Rueckseite mit und ohne offene
# Selbsteinschaetzung, beantwortete Frage, Ergebnis mit und ohne
# Fehlerliste, erste und letzte Karte. Die feste Reihenfolge macht die
# Wege wiederholbar; die Antworten mischt der Runner trotzdem.
def _karten() -> list[dict]:
    return [flashcard("Wie lang ist die Probezeit?", "Sechs Monate"),
            frage("Wie lang ist die Ruhezeit?", ["neun Stunden", "elf Stunden"], 1)]


def test_leiste_und_knoepfe_stimmen_in_jedem_zustand_ueberein(seite_ohne_drehung, bundle):
    url = bundle(_karten(), reihenfolge="fest", selbsteinschaetzung=True)
    besucht = _ablaufen(seite_ohne_drehung, url)

    # Die Erkundung darf nicht stillschweigend verkuemmern: Findet sie
    # nur noch die Startseite, waere oben nichts geprueft und der Test
    # trotzdem gruen. Diese Liste zaehlt nicht die Zustaende auf, die es
    # gibt - sie stellt sicher, dass die Erkundung ueberhaupt herumkommt.
    # Gross- und Kleinschreibung bleibt aussen vor: Die Augenbrauen auf
    # der Karte stehen per CSS in Grossbuchstaben, und innerText liefert
    # den Text so, wie er zu lesen ist.
    alles = "\n".join(besucht).lower()
    for muss in ["umdrehen", "wusste ich nicht", "als gewusst gewertet",
                 "richtig!", "leider falsch", "geschafft", "nur die fehler",
                 "karte 1 von 2", "karte 2 von 2"]:
        assert muss in alles, f"Die Erkundung ist nie in einen Zustand mit {muss!r} gekommen."
    ohne_fehlerliste = [z for z in besucht
                        if "geschafft" in z.lower() and "nur die fehler" not in z.lower()]
    assert ohne_fehlerliste, "Die Erkundung hat nie ein Ergebnis ohne Fehler erreicht."


def test_leiste_und_knoepfe_stimmen_auch_ohne_selbsteinschaetzung_ueberein(
        seite_ohne_drehung, bundle):
    url = bundle(_karten(), reihenfolge="fest", selbsteinschaetzung=False)
    besucht = _ablaufen(seite_ohne_drehung, url)

    alles = "\n".join(besucht).lower()
    assert "wusste ich" not in alles, (
        "Ohne Selbsteinschaetzung darf sie nirgends auftauchen."
    )
    for muss in ["umdrehen", "sechs monate", "geschafft", "karte 1 von 2", "karte 2 von 2"]:
        assert muss in alles, f"Die Erkundung ist nie in einen Zustand mit {muss!r} gekommen."


def test_leeres_bundle_nennt_keine_taste(seite_ohne_drehung, bundle):
    url = bundle([])
    besucht = _ablaufen(seite_ohne_drehung, url)
    assert len(besucht) == 1, f"Ein leeres Bundle hat nur einen Zustand, gefunden: {besucht}"
    assert leiste(seite_ohne_drehung) == "", (
        f"Die Leiste nennt eine Taste: {leiste(seite_ohne_drehung)!r}"
    )
