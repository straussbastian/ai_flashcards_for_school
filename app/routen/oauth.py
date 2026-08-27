"""Die HTTP-Seite des OAuth-Servers.

Bewusst gewoehnliche FastAPI-Routen und nicht @mcp.custom_route(): So laufen
sie unter denselben Schutzkoepfen und demselben deutschen 404-Handler wie der
Rest der Anwendung.
"""

import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.oauth.metadaten import SCOPE, autorisierungsserver, geschuetzte_resource
from app.oauth.redirect import CLAUDE_RUECKSPRUNG, registrierbar
from app.oauth.speicher import client_anlegen

router = APIRouter()

# Die Verbindungsmaske von claude.ai laeuft im Browser und holt die
# Discovery-Dokumente per fetch. Ohne diesen Kopf bricht sie mit einer
# Meldung ab, die nichts ueber die Ursache sagt. Die Dokumente sind
# oeffentlich und enthalten nichts Schuetzenswertes - "*" ist hier richtig
# und nicht bequem.
OEFFENTLICH = {"Access-Control-Allow-Origin": "*"}

# Alle Antworten mit Geheimnissen darin duerfen nirgends liegenbleiben.
NICHT_SPEICHERN = {"Cache-Control": "no-store", "Pragma": "no-cache"}


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


class Registrierungswunsch(BaseModel):
    """Die Felder aus RFC 7591, die dieser Server auswertet.

    Alles Weitere (client_uri, logo_uri, contacts, ...) darf mitgeschickt
    werden und wird stillschweigend ignoriert - RFC 7591 Abschnitt 3.1
    erlaubt das ausdruecklich, und ein Server, der an einem unbekannten Feld
    scheitert, ist mit dem naechsten Claude-Update kaputt.
    """

    model_config = {"extra": "ignore"}

    redirect_uris: list[str]
    client_name: str | None = None


def _fehler(code: str, beschreibung: str, status: int = 400) -> JSONResponse:
    """Eine Ablehnung im Format aus RFC 6749 Abschnitt 5.2.

    error ist der maschinenlesbare Code, error_description der deutsche
    Klartext - Claude zeigt ihn der Lehrerin an.
    """
    return JSONResponse(
        {"error": code, "error_description": beschreibung},
        status_code=status,
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )


@router.post("/oauth/register")
async def registrieren(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> JSONResponse:
    """Dynamic Client Registration (RFC 7591).

    Der Koerper wird von Hand gelesen statt ueber ein Pydantic-Modell im
    Funktionskopf: FastAPI beantwortet ein ungueltiges Modell mit 422 und
    einer englischen Pydantic-Fehlerliste. RFC 7591 verlangt hier 400 mit
    einem "error"-Feld, und Claude wertet genau das aus.
    """
    try:
        rohdaten = await anfrage.json()
    except ValueError:
        return _fehler(
            "invalid_client_metadata",
            "Der Anfragekoerper ist kein gueltiges JSON.",
        )
    try:
        wunsch = Registrierungswunsch.model_validate(rohdaten)
    except ValidationError:
        return _fehler(
            "invalid_client_metadata",
            "Die Anfrage braucht das Feld 'redirect_uris' mit mindestens "
            "einer Rueckadresse.",
        )

    if not wunsch.redirect_uris:
        return _fehler(
            "invalid_redirect_uri",
            "Es wurde keine Rueckadresse angegeben. Erlaubt sind "
            f"{CLAUDE_RUECKSPRUNG} sowie http://localhost/callback und "
            "http://127.0.0.1/callback.",
        )
    for uri in wunsch.redirect_uris:
        if not registrierbar(uri):
            return _fehler(
                "invalid_redirect_uri",
                f"Die Rueckadresse {uri!r} ist auf diesem Server nicht "
                f"erlaubt. Erlaubt sind {CLAUDE_RUECKSPRUNG} sowie "
                "http://localhost/callback und http://127.0.0.1/callback "
                "(der Port darf dort abweichen).",
            )

    kunde = await client_anlegen(
        sitzung, client_name=wunsch.client_name, redirect_uris=wunsch.redirect_uris
    )
    await sitzung.commit()

    return JSONResponse(
        {
            "client_id": kunde.client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": kunde.client_name,
            "redirect_uris": list(kunde.redirect_uris),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
        status_code=201,
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )
