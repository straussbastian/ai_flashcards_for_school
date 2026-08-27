"""Die HTTP-Seite des OAuth-Servers.

Bewusst gewoehnliche FastAPI-Routen und nicht @mcp.custom_route(): So laufen
sie unter denselben Schutzkoepfen und demselben deutschen 404-Handler wie der
Rest der Anwendung.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.oauth.metadaten import autorisierungsserver, geschuetzte_resource

router = APIRouter()

# Die Verbindungsmaske von claude.ai laeuft im Browser und holt die
# Discovery-Dokumente per fetch. Ohne diesen Kopf bricht sie mit einer
# Meldung ab, die nichts ueber die Ursache sagt. Die Dokumente sind
# oeffentlich und enthalten nichts Schuetzenswertes - "*" ist hier richtig
# und nicht bequem.
OEFFENTLICH = {"Access-Control-Allow-Origin": "*"}


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadaten() -> JSONResponse:
    """Zwei Pfade, ein Dokument.

    RFC 9728 Abschnitt 3.1 verlangt fuer die Resource BASE_URL/mcp den Pfad
    mit angehaengtem /mcp - und genau den nennt auch der
    WWW-Authenticate-Kopf, den das MCP-SDK schickt. Die Spec fuehrt in
    Abschnitt 3 den kurzen Pfad. Es gibt beide, damit keiner ins Leere
    laeuft.
    """
    return JSONResponse(
        geschuetzte_resource(get_settings().base_url), headers=OEFFENTLICH
    )


@router.get("/.well-known/oauth-authorization-server")
async def autorisierungsserver_metadaten() -> JSONResponse:
    return JSONResponse(
        autorisierungsserver(get_settings().base_url), headers=OEFFENTLICH
    )
