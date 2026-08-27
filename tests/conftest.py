import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401 -- registriert die Tabellen bei Base.metadata
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
    # join_transaction_mode="create_savepoint": Ohne dieses Flag benutzt die
    # Session den Modus "rollback_only" (SQLAlchemy-Default fuer eine bereits
    # begonnene, nicht verschachtelte Connection-Transaktion). Darin leitet
    # ein automatisches Session-Rollback - wie es SQLAlchemy nach einem
    # fehlgeschlagenen flush() ausloest, siehe Constraint-Tests in
    # tests/test_models.py - direkt an "transaktion" oben weiter und beendet
    # sie. Der spaetere, hier unten stehende await transaktion.rollback()
    # liefe dann ins Leere und SQLAlchemy warnt mit "transaction already
    # deassociated from connection". Mit "create_savepoint" arbeitet die
    # Session stattdessen in einem eigenen SAVEPOINT, sodass die aeussere
    # Transaktion bis zum expliziten Rollback unten unangetastet bleibt.
    fabrik = async_sessionmaker(
        bind=verbindung, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with fabrik() as sitzung:
        yield sitzung
    await transaktion.rollback()
    await verbindung.close()


@pytest_asyncio.fixture
async def datenbank_override(session: AsyncSession) -> AsyncGenerator[None, None]:
    """Ueberschreibt die App-Abhaengigkeit get_session mit der Testsession.

    Ohne diesen Override wuerden Anfragen ueber Depends(get_session) die
    echte Entwicklungsdatenbank (DATABASE_URL) treffen statt der
    Testdatenbank. Wird nicht direkt von Tests angefordert, sondern von der
    Fixture "client" unten - so ist die Absicherung an den TestClient
    gekoppelt statt an das Erinnerungsvermoegen einzelner Testdateien.
    Raeumt sich danach selbst wieder ab.
    """
    app.dependency_overrides[get_session] = lambda: session
    yield
    del app.dependency_overrides[get_session]


@pytest.fixture
def client(datenbank_override: None) -> TestClient:
    """Ein TestClient, dessen Datenbank-Abhaengigkeit zwangslaeufig die Testsession benutzt.

    Jeder Test, der einen Client braucht, fordert diese Fixture an und
    bekommt den Override automatisch mit - ohne dass die einzelne Testdatei
    selbst daran denken muss (Sicherheitsgarantie statt Opt-in).
    """
    return TestClient(app)
