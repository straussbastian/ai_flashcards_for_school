"""Die Sitzungsquelle fuer alles, was keine FastAPI-Abhaengigkeit ist.

Der MCP-Endpunkt und der Token-Pruefer laufen ausserhalb von FastAPIs
Abhaengigkeitsaufloesung: Der eine ist eine eingehaengte ASGI-Anwendung, der
andere wird vom SDK aus einer Middleware heraus aufgerufen. Beide koennen
Depends(get_session) nicht benutzen.

Das ist keine Kleinigkeit, sondern eine Sicherheitsnaht: Die Absicherung in
tests/conftest.py ist ein Eintrag in app.dependency_overrides und greift
ausschliesslich fuer FastAPI-Abhaengigkeiten. Griffe die MCP-Schicht direkt
zu get_session_factory(), traefen alle MCP-Tests die
ENTWICKLUNGSDATENBANK - und zwar gruen, ohne dass irgendetwas auffiele.

Deshalb gibt es genau eine Stelle, an der eine Sitzung entsteht, und diese
Stelle ist ausdruecklich ueberschreibbar.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory

Quelle = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class KeineSitzungsquelle(RuntimeError):
    """Es wurde keine Sitzungsquelle gesetzt.

    Kann im Betrieb nicht auftreten - dort steht die Standardquelle. Der
    Fehler existiert fuer die Testsperre in tests/conftest.py.
    """


@asynccontextmanager
async def _standardquelle() -> AsyncIterator[AsyncSession]:
    """Eine Sitzung aus der gecachten Fabrik, wie get_session sie auch nimmt."""
    async with get_session_factory()() as offene:
        yield offene


_quelle: Quelle = _standardquelle


def quelle_setzen(neue: Quelle) -> None:
    """Ersetzt die Sitzungsquelle. Nur fuer Tests gedacht."""
    global _quelle
    _quelle = neue


def quelle_zuruecksetzen() -> None:
    """Stellt die Standardquelle wieder her."""
    global _quelle
    _quelle = _standardquelle


def sitzung() -> AbstractAsyncContextManager[AsyncSession]:
    """Die einzige Sitzungsquelle fuer Nicht-FastAPI-Code.

    Benutzung:

        async with sitzung() as offene:
            ...
    """
    return _quelle()
