import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Bundle, Karte


async def _bundle(session) -> Bundle:
    bundle = Bundle(slug="rote-katze-springt", titel="Hauptstaedte Europas")
    session.add(bundle)
    await session.flush()
    return bundle


async def test_gueltige_flashcard_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Hauptstadt von Kroatien?",
            rueckseite="Zagreb",
        )
    )
    await session.flush()


async def test_gueltige_frage_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Hauptstadt von Kroatien?",
            antworten=["Split", "Zagreb", "Rijeka"],
            richtige_index=1,
            erklaerung="Zagreb liegt im Landesinneren.",
        )
    )
    await session.flush()


async def test_flashcard_ohne_rueckseite_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(bundle_id=bundle.id, position=1, art="flashcard", vorderseite="Frage")
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_frage_mit_index_ausserhalb_der_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=5,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_frage_mit_fuenf_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["a", "b", "c", "d", "e"],
            richtige_index=0,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_flashcard_mit_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Frage",
            rueckseite="Antwort",
            antworten=["a", "b"],
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_doppelte_position_im_selben_bundle_wird_abgelehnt(session):
    bundle = await _bundle(session)
    for _ in range(2):
        session.add(
            Karte(
                bundle_id=bundle.id,
                position=1,
                art="flashcard",
                vorderseite="Frage",
                rueckseite="Antwort",
            )
        )
    # Der Unique-Constraint ist DEFERRABLE INITIALLY DEFERRED (siehe
    # app/models.py), damit spaeteres Umsortieren von Karten funktioniert,
    # ohne dass eine Zwischenstufe mit vertauschten Positionen scheitert.
    # PostgreSQL prueft ihn deshalb erst beim COMMIT, nicht bei flush().
    # Ohne die folgende Zeile wuerde flush() nie einen Fehler werfen und
    # dieser Test waere gruen, ohne irgendetwas zu pruefen.
    await session.execute(text("SET CONSTRAINTS uq_karten_bundle_position IMMEDIATE"))
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_unbekannte_reihenfolge_wird_abgelehnt(session):
    session.add(Bundle(slug="blaue-ampel-tanzt", titel="Test", reihenfolge="rueckwaerts"))
    with pytest.raises(IntegrityError):
        await session.flush()
