"""Der MCP-Server: Aufbau, Absicherung und Einhaengung.

Warum der Aufbau faul ist (lru_cache statt Modulebene): Wuerde der Server
beim Import gebaut, laese er dabei get_settings().base_url - und damit
braeuchte schon der blosse Import von app.main eine vollstaendige Umgebung.
Genau das wurde in Plan 1 abgeschafft (siehe den Docstring von
app.db.get_engine). Ein frischer Checkout ohne .env und die CI muessen
app.main importieren koennen.

Warum eine Route und kein Mount: Nachgemessen gegen mcp 2.1.1 und Starlette
1.6.0 -
  - app.mount("", mcp_app) verschluckt JEDE Anfrage, auch /{slug}: Ein Mount
    mit leerem Praefix passt auf alles, und die Lernseiten waeren tot.
  - app.mount("/mcp", ...) macht den Endpunkt nur unter /mcp/ erreichbar;
    POST /mcp (die Adresse, die die Lehrerin eintraegt) endet in 405.
Eine gewoehnliche starlette.routing.Route mit der Starlette-App als
endpoint trifft dagegen genau /mcp - Starlette behandelt einen
endpoint, der keine Funktion und keine Methode ist, als ASGI-Anwendung und
reicht den unveraenderten Pfad hinein.
"""

from functools import lru_cache

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.types import Receive, Scope, Send

from app.config import get_settings
from app.oauth.metadaten import MCP_PFAD, SCOPE, resource_url
from app.oauth.pruefer import TokenPruefer

# Der DNS-Rebinding-Schutz des SDK ist AUSDRUECKLICH abgeschaltet - siehe
# Entscheidung E-2 im Plan. Kurz: Er ist fuer Server gedacht, die auf
# localhost lauschen und von einer Webseite aus angreifbar waeren. Unserer
# ist ein oeffentlicher HTTPS-Endpunkt, dessen einziger Schutz das
# Bearer-Token ist; der Host-Kopf ist hinter Coolifys Proxy ohnehin nicht
# vertrauenswuerdig (uvicorn laeuft mit --forwarded-allow-ips='*'). Eine
# Positivliste fuer Origin waere dagegen die wahrscheinlichste Ursache fuer
# ein stummes "Couldn't reach the MCP server", das sich lokal nicht
# nachstellen laesst.
#
# Das Feld MUSS uebergeben werden: Ohne Angabe und mit dem Standardwert
# host="127.0.0.1" schaltet das SDK selbsttaetig einen Schutz ein, der
# ausschliesslich localhost-Hostnamen akzeptiert und allem anderen mit 421
# antwortet - also jeder Anfrage aus Anthropics Cloud.
TRANSPORTSICHERHEIT = TransportSecuritySettings(enable_dns_rebinding_protection=False)


@lru_cache
def mcp_bauen() -> tuple[MCPServer, Starlette]:
    """Baut den MCP-Server und seine ASGI-Anwendung, einmalig und gecacht.

    Returns:
        (Server, ASGI-Anwendung). Den Server braucht der Lifespan in
        app/main.py fuer session_manager.run(), die Anwendung braucht die
        Route.

    Tests leeren den Cache mit mcp_bauen.cache_clear() und bauen pro Test
    neu - session_manager.run() laesst sich nur einmal pro Instanz betreten.
    """
    basis_url = get_settings().base_url
    server = MCPServer(
        "flashcards",
        title="Lernseiten für die Berufsschule",
        instructions=(
            "Mit diesen Werkzeugen legst du Lernpakete für eine Berufsschule "
            "an und pflegst sie. Jedes Lernpaket bekommt eine eigene Adresse "
            "aus drei deutschen Wörtern. Gib der Lehrerin nach jeder "
            "Änderung den vollständigen Link."
        ),
        token_verifier=TokenPruefer(),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(basis_url),
            resource_server_url=AnyHttpUrl(resource_url(basis_url)),
            required_scopes=[SCOPE],
        ),
    )
    # Der Import steht hier und nicht oben: app/mcp/werkzeuge.py importiert
    # app.mcp.dienste, und ein Import auf Modulebene ergaebe einen Ringschluss
    # ueber app.mcp.
    from app.mcp.werkzeuge import registrieren

    registrieren(server)

    asgi = server.streamable_http_app(
        streamable_http_path=MCP_PFAD,
        transport_security=TRANSPORTSICHERHEIT,
    )
    return server, asgi


class MCPWeiche:
    """Reicht eine Anfrage an die MCP-Anwendung durch.

    Eine Klasse und keine Funktion: Starlette behandelt einen endpoint, der
    eine Funktion oder Methode ist, als Request/Response-Endpunkt und
    uebergibt ihm ein Request-Objekt. Eine Instanz mit __call__ ist fuer
    Starlette dagegen eine ASGI-Anwendung und bekommt (scope, receive, send)
    - und genau das braucht die MCP-Anwendung.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        _, asgi = mcp_bauen()
        await asgi(scope, receive, send)
