import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base, get_session
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Erzeugt die Engine fuer die Testdatenbank.

    TEST_DATABASE_URL wird bewusst erst hier gelesen und nicht auf
    Modulebene: Faehlt die Variable, sollen nur die Tests uebersprungen
    werden, die tatsaechlich eine Datenbank brauchen. Ein Fehlschlag beim
    Einlesen des Moduls wuerde sonst das Einsammeln aller Tests verhindern,
    auch solcher ohne Datenbankbezug (z.B. tests/test_config.py).
    """
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip(
            "TEST_DATABASE_URL ist nicht gesetzt. Bitte in der .env eintragen "
            "(siehe .env.example) und die Testdatenbank einmalig anlegen mit: "
            "docker compose -f compose.dev.yml exec db createdb -U flashcards flashcards_test"
        )

    engine = create_async_engine(test_database_url)
    async with engine.begin() as verbindung:
        await verbindung.run_sync(Base.metadata.drop_all)
        await verbindung.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Eine Session pro Test, die am Ende zurueckgerollt wird."""
    verbindung = await test_engine.connect()
    transaktion = await verbindung.begin()
    fabrik = async_sessionmaker(bind=verbindung, expire_on_commit=False)
    async with fabrik() as sitzung:
        yield sitzung
    await transaktion.rollback()
    await verbindung.close()


@pytest_asyncio.fixture
async def datenbank_override(session: AsyncSession) -> AsyncGenerator[None, None]:
    """Ueberschreibt die App-Abhaengigkeit get_session mit der Testsession.

    Ohne diesen Override wuerden Tests, die den TestClient benutzen, ueber
    Depends(get_session) die echte Entwicklungsdatenbank (DATABASE_URL)
    treffen statt der Testdatenbank. Wird explizit von den Tests angefordert,
    die ihn brauchen (siehe tests/test_main.py), und raeumt sich danach
    selbst wieder ab.
    """
    app.dependency_overrides[get_session] = lambda: session
    yield
    del app.dependency_overrides[get_session]
