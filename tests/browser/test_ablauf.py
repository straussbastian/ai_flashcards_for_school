"""Der gewoehnliche Ablauf - einmal ganz durch, nur mit der Tastatur.

Die Spec, Abschnitt 6: "Am Rechner ist jedes Bedienelement mit der
Tastatur erreichbar - es gibt keine Stelle, an der man zur Maus greifen
muss." Dieser Test greift kein einziges Mal zur Maus.
"""

from tests.browser.conftest import (
    abdruck,
    druecken,
    flashcard,
    frage,
    knoepfe,
    laden,
    ruhig_bleiben,
    sichtbare_seite,
    starten,
    umblaettern,
)

# Vier Karten in fester Reihenfolge, damit der Ablauf vorhersagbar ist.
# Die Antworten mischt der Runner trotzdem - der Test sucht deshalb den
# Buchstaben zum Antworttext und verlaesst sich nie auf eine Position.
PROBEZEIT = "**Probezeit** - wie lang?"
RUHEZEIT = "Wie lang ist die Ruhezeit?"
KUENDIGUNG = "Wie lang ist die Kuendigungsfrist?"
URLAUB = "Wie viele Urlaubstage?"


def _karten() -> list[dict]:
    return [
        flashcard(PROBEZEIT, "Sechs Monate"),
        frage(RUHEZEIT, ["neun Stunden", "elf Stunden"], 1),
        flashcard(KUENDIGUNG, "Zwei Wochen"),
        frage(URLAUB, ["zwanzig Tage", "vierundzwanzig Tage", "dreissig Tage"], 2),
    ]


def _buchstabe_fuer(blatt, antwort: str) -> str:
    """Der Buchstabe, unter dem diese Antwort gerade steht."""
    for beschriftung in knoepfe(blatt):
        if beschriftung.split("\n", 1)[-1].strip() == antwort:
            return beschriftung.split("\n")[0]
    raise AssertionError(f"Die Antwort {antwort!r} steht nicht zur Wahl: {knoepfe(blatt)}")


def test_ein_ganzer_durchlauf_nur_mit_der_tastatur(seite, bundle):
    url = bundle(_karten(), reihenfolge="fest", selbsteinschaetzung=True)
    starten(seite, url)

    # --- Karte 1: Markdown wird als HTML dargestellt ---
    assert seite.locator("#karte-innen strong").first.inner_text() == "Probezeit", (
        "Das Markdown der Vorderseite wird nicht als HTML dargestellt."
    )
    assert "**" not in sichtbare_seite(seite), (
        f"Die Sternchen stehen roh auf der Karte: {sichtbare_seite(seite)!r}"
    )

    umblaettern(seite, "Leertaste")
    assert "Sechs Monate" in sichtbare_seite(seite)
    umblaettern(seite, "A")            # wusste ich -> zaehlt und blaettert weiter

    # --- Karte 2: richtig beantwortet ---
    assert RUHEZEIT in sichtbare_seite(seite)
    umblaettern(seite, _buchstabe_fuer(seite, "elf Stunden"))
    assert "Richtig" in sichtbare_seite(seite), sichtbare_seite(seite)
    umblaettern(seite, "A")            # weiter

    # --- Karte 3: nicht gewusst ---
    umblaettern(seite, "Leertaste")
    umblaettern(seite, "B")            # wusste ich nicht

    # --- Karte 4: falsch beantwortet ---
    umblaettern(seite, _buchstabe_fuer(seite, "zwanzig Tage"))
    assert "falsch" in sichtbare_seite(seite).lower(), sichtbare_seite(seite)
    umblaettern(seite, "A")            # zum Ergebnis

    # --- Ergebnis: zwei von vier ---
    ergebnis = sichtbare_seite(seite).replace("\n", " ")
    assert "2 / 4" in ergebnis, f"Der Punktestand stimmt nicht: {ergebnis!r}"

    # --- "Nur die Fehler" enthaelt genau die danebengegangenen Karten ---
    assert "Nur die Fehler (2)" in ergebnis, ergebnis
    umblaettern(seite, "B")

    gesehen = []
    for nummer in range(2):
        gesehen.append(sichtbare_seite(seite))
        if nummer == 0:
            umblaettern(seite, "→")
    zusammen = " ".join(gesehen)
    assert "Kuendigungsfrist" in zusammen and "Urlaubstage" in zusammen, (
        f"Der Fehlerdurchlauf enthaelt nicht die richtigen Karten: {zusammen!r}"
    )
    for daneben_nicht in ("Probezeit", "Ruhezeit"):
        assert daneben_nicht not in zusammen, (
            f"{daneben_nicht!r} ging nicht daneben, ist aber im Fehlerdurchlauf: {zusammen!r}"
        )


def test_zurueckblaettern_behaelt_das_ergebnis_und_laesst_die_antwort_stehen(seite, bundle):
    """Die Spec: "Bereits beantwortete Karten behalten beim Zurueckblaettern ihr
    Ergebnis; eine Antwort kann nicht nachtraeglich geaendert werden.""" ""
    url = bundle([frage(RUHEZEIT, ["neun Stunden", "elf Stunden"], 1),
                  frage(URLAUB, ["zwanzig Tage", "dreissig Tage"], 1)],
                 reihenfolge="fest")
    starten(seite, url)

    umblaettern(seite, _buchstabe_fuer(seite, "neun Stunden"))   # falsch
    aufloesung = sichtbare_seite(seite)
    assert "falsch" in aufloesung.lower()

    umblaettern(seite, "A")     # weiter zur zweiten Frage
    umblaettern(seite, "←")     # und zurueck

    assert sichtbare_seite(seite) == aufloesung, (
        "Die Karte zeigt beim Zurueckblaettern nicht mehr dasselbe Ergebnis.\n"
        f"vorher: {aufloesung!r}\njetzt:  {sichtbare_seite(seite)!r}"
    )
    # Die Antwortknoepfe sind nicht mehr zu erreichen - die Karte liegt
    # auf ihrer Rueckseite. Damit kann die Antwort auch nicht geaendert
    # werden.
    erreichbar = [k for k in knoepfe(seite) if "beenden" not in k]
    assert all("Stunden" not in k for k in erreichbar), (
        f"Die Antworten stehen wieder zur Wahl: {erreichbar}"
    )

    vorher = abdruck(seite)
    druecken(seite, "B")        # der Buchstabe der anderen Antwort
    assert ruhig_bleiben(seite, vorher), "Die Antwort liess sich nachtraeglich aendern."


def test_am_handy_gibt_es_zwei_balken_statt_der_tastenleiste(handy, bundle):
    """Die Spec: "Am Handy zwei breite Balken unten, kein Wischen"."""
    url = bundle(_karten(), reihenfolge="fest")
    laden(handy, url)
    handy.get_by_role("button", name="Los geht's").click()
    handy.wait_for_timeout(400)

    assert handy.locator("#zurueck").is_visible() and handy.locator("#weiter").is_visible(), (
        "Am Handy fehlen die beiden Navigationsbalken."
    )
    assert not handy.locator("#tastenleiste").is_visible(), (
        "Am Handy steht eine Tastenleiste, obwohl es dort keine Tastatur gibt."
    )

    vorher = abdruck(handy)
    handy.locator("#weiter").click()
    handy.wait_for_timeout(400)
    assert abdruck(handy) != vorher, "Der Weiter-Balken bewirkt nichts."
    assert RUHEZEIT in sichtbare_seite(handy)


def test_am_rechner_gibt_es_die_tastenleiste_statt_der_balken(seite, bundle):
    url = bundle(_karten(), reihenfolge="fest")
    starten(seite, url)
    assert seite.locator("#tastenleiste").is_visible()
    assert not seite.locator("#weiter").is_visible(), (
        "Am Rechner ist die Fussleiste sichtbar - dann sind zwei Wege nebeneinander da."
    )
