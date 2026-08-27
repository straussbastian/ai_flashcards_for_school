from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Gemeinsame Basis aller Tabellen."""


@lru_cache
def get_engine() -> AsyncEngine:
    """Erzeugt die Engine lazy und gecacht.

    Wird die Engine (wie zuvor) beim Modulimport erzeugt, wertet das sofort
    get_settings().database_url aus - und damit scheitert schon der blosse
    Import von app.db (und darueber app.main) ohne gesetzte DATABASE_URL,
    z.B. auf einem frischen Checkout ohne .env oder in CI. Durch den Aufruf
    erst hier haengt nur die tatsaechliche Nutzung an der Umgebungsvariable,
    nicht der Import.
    """
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Gibt die gecachte Session-Fabrik zurueck, gebunden an get_engine()."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-Abhaengigkeit: eine Session pro Anfrage."""
    async with get_session_factory()() as session:
        yield session
