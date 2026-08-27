import pytest

from app.models import Bundle, Karte


async def _bundle_anlegen(session, slug="kluge-tafel-leuchtet", aktiv=True, mit_karten=True):
    bundle = Bundle(slug=slug, titel="Arbeitsrecht kompakt", aktiv=aktiv,
                    klasse="FS 23b", beschreibung="Erst lernen, dann fragen.")
    session.add(bundle)
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


@pytest.mark.parametrize("pfad", ["/favicon.ico", "/healthz2", "/zwei-woerter", "/GROSS-und-klein-hier"])
async def test_was_nicht_wie_eine_adresse_aussieht_wird_nicht_gesucht(klient, session, pfad):
    antwort = await klient.get(pfad)
    assert antwort.status_code == 404


async def test_healthz_bleibt_erreichbar(klient, session):
    assert (await klient.get("/healthz")).status_code == 200


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
    assert "</script><script>" not in antwort.text
