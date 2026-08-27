"""Die HTTP-Seite des OAuth-Servers.

Bewusst gewoehnliche FastAPI-Routen und nicht @mcp.custom_route(): So laufen
sie unter denselben Schutzkoepfen und demselben deutschen 404-Handler wie der
Rest der Anwendung.
"""

import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.oauth.metadaten import SCOPE, autorisierungsserver, geschuetzte_resource
from app.oauth.redirect import CLAUDE_RUECKSPRUNG, passt, registrierbar
from app.oauth.speicher import (
    OAuthFehler,
    client_anlegen,
    client_holen,
    code_ausgeben,
    code_einloesen,
    erneuern,
    tokenpaar_ausgeben,
)
from app.templates import rendern

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


# Die Parameter, die die Zustimmungsseite unveraendert weiterreichen muss.
# passwort steht bewusst NICHT darin: Es wird geprueft und danach vergessen.
DURCHGEREICHT = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
    "resource",
)


def _weiterleitung_mit_fehler(
    redirect_uri: str, code: str, beschreibung: str, state: str | None
) -> RedirectResponse:
    """Ein Fehler, der zur Rueckadresse gehoert (RFC 6749 Abschnitt 4.1.2.1).

    Nur aufrufen, NACHDEM redirect_uri gegen die registrierten Adressen
    geprueft wurde - sonst waere dieser Server ein offener Weiterleiter.
    """
    trenner = "&" if "?" in redirect_uri else "?"
    teile = [f"error={quote(code)}", f"error_description={quote(beschreibung)}"]
    if state is not None:
        teile.append(f"state={quote(state)}")
    return RedirectResponse(redirect_uri + trenner + "&".join(teile), status_code=302)


def _seite_mit_fehler(anfrage: Request, text: str) -> HTMLResponse:
    """Eine deutsche Fehlerseite, wenn NICHT weitergeleitet werden darf."""
    return rendern(
        anfrage,
        "fehler.html",
        status_code=400,
        ueberschrift="Der Verbindungsversuch hat nicht geklappt",
        text=text,
    )


async def _vorpruefen(
    anfrage: Request, werte: dict[str, str | None], sitzung: AsyncSession
) -> HTMLResponse | RedirectResponse | None:
    """Prueft die Anfrage. Gibt eine Antwort zurueck, wenn sie abzulehnen ist.

    Die Reihenfolge ist sicherheitsrelevant: Solange nicht feststeht, dass
    die Rueckadresse zu einem registrierten Client gehoert, geht KEINE
    Antwort dorthin - auch kein Fehler.
    """
    kunde = await client_holen(sitzung, werte["client_id"] or "")
    if kunde is None:
        return _seite_mit_fehler(
            anfrage,
            "Der Client, der sich verbinden will, ist diesem Server nicht "
            "bekannt. Bitte entferne den Connector in Claude und fuege ihn "
            "noch einmal hinzu.",
        )

    redirect_uri = werte["redirect_uri"]
    if not redirect_uri or not passt(redirect_uri, list(kunde.redirect_uris)):
        return _seite_mit_fehler(
            anfrage,
            "Die Rueckadresse der Anfrage gehoert nicht zu diesem Client. "
            "Bitte entferne den Connector in Claude und fuege ihn noch "
            "einmal hinzu.",
        )

    state = werte["state"]
    if werte["response_type"] != "code":
        return _weiterleitung_mit_fehler(
            redirect_uri,
            "unsupported_response_type",
            "Dieser Server kennt nur den Ablauf mit Autorisierungscode "
            "(response_type=code).",
            state,
        )
    if not werte["code_challenge"] or werte["code_challenge_method"] != "S256":
        return _weiterleitung_mit_fehler(
            redirect_uri,
            "invalid_request",
            "Dieser Server verlangt PKCE mit der Methode S256.",
            state,
        )
    return None


@router.get("/oauth/authorize", response_class=HTMLResponse, response_model=None)
async def zustimmung_zeigen(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> HTMLResponse | RedirectResponse:
    werte = {name: anfrage.query_params.get(name) for name in DURCHGEREICHT}
    abgelehnt = await _vorpruefen(anfrage, werte, sitzung)
    if abgelehnt is not None:
        return abgelehnt
    return rendern(
        anfrage,
        "zustimmung.html",
        verborgen={name: wert for name, wert in werte.items() if wert is not None},
        fehler=None,
    )


@router.post("/oauth/authorize", response_model=None)
async def zustimmung_erteilen(
    anfrage: Request,
    passwort: str = Form(default=""),
    sitzung: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    formular = await anfrage.form()
    werte = {name: formular.get(name) for name in DURCHGEREICHT}
    abgelehnt = await _vorpruefen(anfrage, werte, sitzung)
    if abgelehnt is not None:
        return abgelehnt

    # secrets.compare_digest statt "==": Ein gewoehnlicher Vergleich bricht
    # beim ersten falschen Zeichen ab und verraet ueber die Laufzeit, wie
    # viele Zeichen stimmten.
    if not secrets.compare_digest(passwort, get_settings().teacher_password):
        return rendern(
            anfrage,
            "zustimmung.html",
            status_code=401,
            verborgen={name: wert for name, wert in werte.items() if wert is not None},
            fehler="Das Passwort stimmt nicht. Bitte versuche es noch einmal.",
        )

    kunde = await client_holen(sitzung, werte["client_id"])
    code = await code_ausgeben(
        sitzung,
        client=kunde,
        redirect_uri=werte["redirect_uri"],
        code_challenge=werte["code_challenge"],
        resource=werte["resource"],
    )
    await sitzung.commit()

    ziel = werte["redirect_uri"]
    trenner = "&" if "?" in ziel else "?"
    teile = [f"code={quote(code)}"]
    if werte["state"] is not None:
        teile.append(f"state={quote(werte['state'])}")
    return RedirectResponse(ziel + trenner + "&".join(teile), status_code=302)


def _tokenantwort(zugriff: str, erneuerung: str, gueltigkeit: int, scope: str) -> JSONResponse:
    """Die Antwort nach RFC 6749 Abschnitt 5.1."""
    return JSONResponse(
        {
            "access_token": zugriff,
            "token_type": "Bearer",
            "expires_in": gueltigkeit,
            "refresh_token": erneuerung,
            "scope": scope,
        },
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )


@router.post("/oauth/token")
async def token_ausgeben(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> JSONResponse:
    """Code einloesen oder Tokenpaar erneuern.

    Der Koerper ist application/x-www-form-urlencoded, so verlangt es die
    Spec in Abschnitt 5 (und RFC 6749). Gelesen wird er von Hand statt ueber
    Form(...)-Parameter im Funktionskopf: Ein fehlendes Pflichtfeld
    beantwortet FastAPI sonst mit 422 und einer englischen Pydantic-Liste,
    waehrend OAuth hier 400 mit einem "error"-Feld verlangt - und genau das
    wertet Claude aus.
    """
    formular = await anfrage.form()
    grant_type = formular.get("grant_type")

    try:
        if grant_type == "authorization_code":
            eingeloest = await code_einloesen(
                sitzung,
                code=str(formular.get("code") or ""),
                client_id=str(formular.get("client_id") or ""),
                redirect_uri=str(formular.get("redirect_uri") or ""),
                code_verifier=str(formular.get("code_verifier") or ""),
            )
            zugriff, erneuerung, gueltigkeit = await tokenpaar_ausgeben(
                sitzung,
                client_id=eingeloest.client_id,
                familie_id=eingeloest.familie_id,
                scope=eingeloest.scope,
                resource=eingeloest.resource,
            )
            scope = eingeloest.scope
        elif grant_type == "refresh_token":
            zugriff, erneuerung, gueltigkeit = await erneuern(
                sitzung,
                erneuerungstoken=str(formular.get("refresh_token") or ""),
                client_id=str(formular.get("client_id") or ""),
            )
            scope = SCOPE
        else:
            return _fehler(
                "unsupported_grant_type",
                "Dieser Server kennt nur die Ablaeufe 'authorization_code' "
                "und 'refresh_token'.",
            )
    except OAuthFehler as fehler:
        # commit statt rollback: code_einloesen() und erneuern() ziehen bei
        # einer Wiederverwendung die ganze Tokenfamilie zurueck - dieser
        # Widerruf muss auch dann bestehen bleiben, wenn die Anfrage
        # abgelehnt wird. Genau dafuer wurde er geschrieben.
        await sitzung.commit()
        return _fehler(fehler.code, fehler.beschreibung)

    await sitzung.commit()
    return _tokenantwort(zugriff, erneuerung, gueltigkeit, scope)
