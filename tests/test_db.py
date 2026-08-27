from sqlalchemy import text


async def test_datenbank_antwortet(session):
    ergebnis = await session.scalar(text("SELECT 1"))
    assert ergebnis == 1
