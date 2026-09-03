import pytest

from app.db import get_session
from app.main import app
from app.models import Bundle, Karte
from tests.conftest import mit_adresse


async def _bundle_anlegen(session, slug="kluge-tafel-leuchtet", aktiv=True, mit_karten=True):
    bundle = mit_adresse(session, Bundle(
        slug=slug, titel="Arbeitsrecht kompakt", aktiv=aktiv,
        gruppe="FS 23b", beschreibung="Erst lernen, dann fragen."))
    await session.flush()
    if mit_karten:
        session.add(Karte(bundle_id=bundle.id, position=1, art="flashcard",
                          vorderseite="Probezeit?", rueckseite="Sechs Monate"))
        session.add(Karte(bundle_id=bundle.id, position=2, art="frage",
                          vorderseite="Ruhezeit?", antworten=["neun", "elf"],
                          richtige_index=1))
        await session.flush()
    return bundle


async def test_bundle_wird_ausgeliefert(klient, session):
    await _bundle_anlegen(session)
    antwort = await klient.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200
    assert "Arbeitsrecht kompakt" in antwort.text


async def test_das_bundle_steckt_als_json_in_der_seite(klient, session):
    await _bundle_anlegen(session)
    antwort = await klient.get("/kluge-tafel-leuchtet")
    assert 'id="bundle-daten"' in antwort.text
    assert '"art": "flashcard"' in antwort.text or '"art":"flashcard"' in antwort.text


async def test_unbekannte_adresse_ergibt_404(klient, session):
    antwort = await klient.get("/gibt-es-nicht")
    assert antwort.status_code == 404
    assert "kluge" not in antwort.text.lower()   # verraet keine anderen Adressen


async def test_inaktives_bundle_ergibt_410(klient, session):
    await _bundle_anlegen(session, aktiv=False)
    antwort = await klient.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 410
    assert "nicht mehr aktiv" in antwort.text


async def test_bundle_ohne_karten_erklaert_sich(klient, session):
    await _bundle_anlegen(session, mit_karten=False)
    antwort = await klient.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200
    assert "noch keine Karten" in antwort.text


class _DatenbankVerboten:
    """Ein Session-Ersatz, der bei jeder tatsaechlichen Abfrage eine Ausnahme wirft.

    Anders als eine Ausnahme direkt in der get_session-Abhaengigkeit: FastAPI
    loest Depends(get_session) fuer JEDE Anfrage an die Route auf, bevor der
    Funktionskoerper laeuft - eine dort werfende Abhaengigkeit wuerde also
    auch fuer eine formal gueltige Adresse feuern und nichts darueber
    aussagen, ob tatsaechlich eine Abfrage gestellt wurde. Dieses Objekt
    laesst sich dagegen anstandslos als Session entgegennehmen; erst ein
    echter session.scalar(...)-Aufruf - der Schritt, der wirklich "die
    Datenbank fragt" - loest die Ausnahme aus.
    """

    async def scalar(self, *args, **kwargs):
        raise AssertionError("Die Datenbank haette hier nicht gefragt werden duerfen.")


@pytest.mark.parametrize("pfad", ["/favicon.ico", "/healthz2", "/zwei-woerter", "/GROSS-und-klein-hier"])
async def test_was_nicht_wie_eine_adresse_aussieht_wird_nicht_gesucht(klient, session, pfad):
    # Der Override ueberschreibt vorruebergehend den echten (durch die
    # klient-Fixture bereits gesetzten) Datenbank-Override: Statt der
    # Testsession bekommt die Route ein Objekt, das bei einer echten Abfrage
    # sofort eine Ausnahme wirft. So sichert der Test nicht nur den
    # Statuscode ab, sondern wirklich die Zusage "die Datenbank wird fuer
    # so eine Adresse gar nicht erst gefragt" - genau die Zusage, die beim
    # %0A-Befund gebrochen war, ohne dass ein Test das bemerkt haette.
    urspruenglicher_override = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = lambda: _DatenbankVerboten()
    try:
        antwort = await klient.get(pfad)
    finally:
        app.dependency_overrides[get_session] = urspruenglicher_override

    assert antwort.status_code == 404


async def test_healthz_bleibt_erreichbar(klient, session):
    assert (await klient.get("/healthz")).status_code == 200


async def test_adresse_mit_angehaengtem_zeilenumbruch_ergibt_404(klient, session):
    # Pythons "$" im Muster matchte frueher auch unmittelbar vor einem
    # abschliessenden "\n" - re.match liess "kluge-tafel-leuchtet\n" damit
    # durch und fragte die Datenbank. Derselbe Datenbank-Verbot-Override wie
    # oben: Ein Wiederauftreten des Bugs soll hier laut fehlschlagen statt
    # sich hinter einem zufaellig richtigen Statuscode zu verstecken.
    await _bundle_anlegen(session)
    urspruenglicher_override = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = lambda: _DatenbankVerboten()
    try:
        antwort = await klient.get("/kluge-tafel-leuchtet%0A")
    finally:
        app.dependency_overrides[get_session] = urspruenglicher_override

    assert antwort.status_code == 404


async def test_adresse_mit_ueberlangem_wort_ergibt_404(klient, session):
    # bundles.slug ist auf 120 Zeichen begrenzt (app/models.py); eine Adresse
    # mit einem Wort ueber der im Muster erlaubten Laenge (39 Zeichen) kann
    # nie existieren und muss die Datenbank nicht fragen - siehe Kommentar
    # bei ADRESSE in app/routen/lernseite.py.
    zu_lang = "a" * 40
    urspruenglicher_override = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = lambda: _DatenbankVerboten()
    try:
        antwort = await klient.get(f"/{zu_lang}-tafel-leuchtet")
    finally:
        app.dependency_overrides[get_session] = urspruenglicher_override

    assert antwort.status_code == 404


async def test_adresse_ueber_der_spaltenlaenge_ergibt_404(klient, session):
    # Nachzuegler aus Plan 3 Task 3: ADRESSE erlaubte frueher bis zu 40
    # Zeichen je Wortgruppe (3*40+2=122), obwohl bundles.slug (app/models.py)
    # nur 120 Zeichen fasst - eine 121 Zeichen lange Adresse passte damit
    # trotzdem durchs Muster und fragte doch die Datenbank, obwohl der
    # Kommentar bei ADRESSE in app/routen/lernseite.py das Gegenteil zusagte.
    # Diese Adresse ist genau 121 Zeichen lang (40+1+40+1+39) - mit dem
    # korrigierten Muster ({1,39} je Wortgruppe) darf sie die Datenbank nicht
    # erreichen.
    adresse = "a" * 40 + "-" + "b" * 40 + "-" + "c" * 39
    assert len(adresse) == 121
    urspruenglicher_override = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = lambda: _DatenbankVerboten()
    try:
        antwort = await klient.get(f"/{adresse}")
    finally:
        app.dependency_overrides[get_session] = urspruenglicher_override

    assert antwort.status_code == 404


async def test_skript_ende_in_einer_karte_zerlegt_die_seite_nicht(klient, session):
    # Die Antworten einer Frage sind Klartext (siehe app/bundle_json.py) und
    # durchlaufen anders als vorderseite/rueckseite/erklaerung KEINE
    # Markdown-Saeuberung (app/markdown.rendern via nh3), die <script>-Tags
    # ohnehin entfernen wuerde. Nur an so einer unbereinigten Stelle prueft
    # dieser Test wirklich die JSON-Einbettung selbst und nicht zufaellig
    # die Markdown-Saeuberung.
    bundle = await _bundle_anlegen(session, mit_karten=False)
    session.add(Karte(bundle_id=bundle.id, position=1, art="frage",
                      vorderseite="Vorsicht bei dieser Frage?",
                      antworten=["</script><script>alert(1)</script>", "harmlos"],
                      richtige_index=1))
    await session.flush()
    antwort = await klient.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200

    # Nicht die ganze Seite auf die konkrete Testzeichenfolge pruefen,
    # sondern den Datenblock selbst herausschneiden und auf die eigentliche
    # Eigenschaft pruefen ("kein </script darin", nicht nur "nicht genau
    # dieses eine Paar </script><script>"). Die echte schliessende
    # </script>-Marke des Datenblocks ist die LETZTE vor dem statischen
    # runner.js-Tag aus dem Template: Selbst wenn eine Karte </script>
    # vorgaukelt, bleibt das echte, vom Template gesetzte Ende danach die
    # naechstgelegene Fundstelle zum runner.js-Tag - ein fruehes,
    # eingeschleustes </script> davor bleibt so innerhalb des geschnittenen
    # Datenblocks und faellt der Pruefung auf.
    start = antwort.text.index('id="bundle-daten">') + len('id="bundle-daten">')
    runner_marke = antwort.text.index('<script src="/static/runner.js">', start)
    ende = antwort.text.rindex('</script>', start, runner_marke)
    datenblock = antwort.text[start:ende]
    assert "</script" not in datenblock


async def test_lernseite_traegt_die_urheberzeile(klient, session):
    """Dieselbe Zeile wie auf Start- und Fehlerseite, aus demselben Teiltemplate.

    Eigener Test statt einer Zeile in tests/test_seiten.py: Die Lernseite
    bindet urheber.html an einer anderen Stelle ein - nach der Fussnote
    statt nach </main> - und braucht deshalb eine Datenbank.
    """
    await _bundle_anlegen(session)
    text = (await klient.get("/kluge-tafel-leuchtet")).text
    assert "Bastian Strauss, Varel" in text
    assert "https://bastianstrauss.digital" in text
    assert text.rindex('class="urheber"') < text.rindex("</div>")
