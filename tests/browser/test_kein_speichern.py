"""Es wird nichts gespeichert - und zwar nachweislich.

Das ist keine Bequemlichkeit, sondern die Zusage aus der Spec: "Kein
Speichern von Ergebnissen, keine Cookies, kein LocalStorage" und "Nach
dem ersten Aufruf gibt es keine weiteren Serveranfragen. Das erzwingt
technisch, was versprochen wurde: Es kann nichts gespeichert werden."

Der letzte Satz ist der interessante: Solange der Runner nach dem Laden
mit niemandem mehr spricht, kann auf dem Server gar nichts ueber die
Lernenden ankommen. Deshalb wird hier nicht nur in die Ablagen des
Browsers geschaut, sondern auch mitgezaehlt, was ueber die Leitung geht.
"""

from tests.browser.conftest import (
    abdruck,
    flashcard,
    frage,
    knoepfe,
    laden,
    sichtbare_seite,
    starten,
    umblaettern,
)


def _karten() -> list[dict]:
    return [flashcard("Wie lang ist die Probezeit?", "Sechs Monate"),
            frage("Wie lang ist die Ruhezeit?", ["neun Stunden", "elf Stunden"], 1)]


def _ablagen(blatt) -> dict:
    return blatt.evaluate("""() => ({
      cookie: document.cookie,
      lokal: Object.fromEntries(Object.entries(localStorage)),
      sitzung: Object.fromEntries(Object.entries(sessionStorage)),
    })""")


def test_ein_ganzer_durchlauf_hinterlaesst_nichts_im_browser(seite, bundle):
    url = bundle(_karten(), reihenfolge="fest")
    starten(seite, url)
    umblaettern(seite, "Leertaste")
    umblaettern(seite, "A")
    buchstabe = next(k.split("\n")[0] for k in knoepfe(seite) if k.endswith("elf Stunden"))
    umblaettern(seite, buchstabe)
    umblaettern(seite, "A")     # zum Ergebnis
    assert "geschafft" in sichtbare_seite(seite).lower()

    ablagen = _ablagen(seite)
    assert ablagen["cookie"] == "", f"Es liegt ein Cookie da: {ablagen['cookie']!r}"
    assert ablagen["lokal"] == {}, f"Im localStorage steht etwas: {ablagen['lokal']}"
    assert ablagen["sitzung"] == {}, f"Im sessionStorage steht etwas: {ablagen['sitzung']}"


def test_neu_laden_faengt_wieder_von_vorn_an(seite, bundle):
    url = bundle(_karten(), reihenfolge="fest")
    starten(seite, url)
    umblaettern(seite, "Leertaste")
    mittendrin = abdruck(seite)

    seite.reload()
    seite.wait_for_selector("#karte-innen > *", state="attached")

    assert abdruck(seite) != mittendrin
    assert any("Los geht" in k for k in knoepfe(seite)), (
        f"Nach dem Neuladen steht nicht wieder die Startseite da: {knoepfe(seite)}"
    )
    assert not seite.locator("#kopf").is_visible(), (
        "Der Fortschritt aus dem alten Durchlauf steht noch da."
    )


def test_nach_dem_laden_geht_keine_anfrage_mehr_hinaus(seite, bundle):
    """Der Runner spricht nach dem Laden mit niemandem mehr."""
    url = bundle(_karten(), reihenfolge="fest")
    anfragen: list[str] = []
    seite.on("request", lambda a: anfragen.append(f"{a.method} {a.url}"))

    laden(seite, url)
    # Alles, was zum ersten Aufruf gehoert (Dokument, CSS, Runner), ist
    # erlaubt. Ab hier darf nichts mehr dazukommen.
    seite.wait_for_timeout(300)
    beim_laden = len(anfragen)
    assert beim_laden, "Es wurde ueberhaupt nichts geladen - der Test misst nichts."

    starten(seite, url)
    # starten() laedt die Seite noch einmal; danach wird nur noch bedient.
    seite.wait_for_timeout(300)
    nach_dem_start = len(anfragen)

    umblaettern(seite, "Leertaste")
    umblaettern(seite, "A")
    buchstabe = next(k.split("\n")[0] for k in knoepfe(seite) if k.endswith("elf Stunden"))
    umblaettern(seite, buchstabe)
    umblaettern(seite, "A")
    umblaettern(seite, "A")     # nochmal starten
    seite.wait_for_timeout(500)

    assert len(anfragen) == nach_dem_start, (
        "Der Runner hat nach dem Laden noch Anfragen gestellt: "
        f"{anfragen[nach_dem_start:]}"
    )
