"""Tests fuer die Sitzungsquelle aus app/sitzung.py und fuer das MCP-SDK.

Warum beides in einer Datei: Die Sitzungsquelle existiert ausschliesslich,
damit die MCP-Schicht nicht an tests/conftest.py vorbei auf die
Entwicklungsdatenbank zugreift. Ohne SDK gaebe es sie nicht.
"""

import pytest

from app.sitzung import KeineSitzungsquelle, quelle_setzen, quelle_zuruecksetzen, sitzung


def test_das_sdk_ist_version_zwei():
    """Version 1 des SDK haette eine voellig andere API.

    In Version 1 hiess die Klasse FastMCP und lag in mcp.server.fastmcp.
    Wuerde jemand versehentlich auf 1.x zurueckfallen, scheiterte der Import
    hier - und nicht erst irgendwo mitten im Betrieb.
    """
    from mcp.server.mcpserver import MCPServer

    assert MCPServer is not None

    with pytest.raises(ModuleNotFoundError):
        import mcp.server.fastmcp  # noqa: F401


async def test_ohne_gesetzte_quelle_fliegt_ein_klarer_fehler():
    """Die Standardquelle wird in Tests durch eine Sperre ersetzt.

    Der Sinn der Sperre steht in tests/conftest.py bei der Fixture
    "sitzungsquelle_gesperrt": Ein MCP-Test, der die Fixture "mcp_sitzung"
    vergisst, soll laut scheitern statt still die Entwicklungsdatenbank zu
    treffen.
    """
    with pytest.raises(KeineSitzungsquelle):
        async with sitzung():
            pass


async def test_gesetzte_quelle_wird_benutzt(session):
    """quelle_setzen biegt sitzung() auf eine beliebige Sitzung um."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def eigene():
        yield session

    quelle_setzen(eigene)
    try:
        async with sitzung() as gefunden:
            assert gefunden is session
    finally:
        quelle_zuruecksetzen()
