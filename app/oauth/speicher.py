"""Die Datenbankarbeit des OAuth-Servers.

Kennt kein HTTP. Jede Ablehnung verlaesst dieses Modul als OAuthFehler mit
einem RFC-Code und einem deutschen Klartext; welche der beiden Angaben in
der Antwort landet, entscheidet die Route.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.oauth.geheimnisse import gleich, neues_geheimnis, pfeffern, pkce_ableiten
from app.oauth.modelle import (
    ART_ERNEUERUNG,
    ART_ZUGRIFF,
    STANDARD_SCOPE,
    OAuthClient,
    OAuthCode,
    OAuthToken,
)

# Zehn Minuten sind grosszuegig fuer einen Klick auf "Zugriff geben" und
# knapp genug, dass ein abgefangener Code nicht lange nuetzt.
CODE_GUELTIGKEIT = timedelta(minutes=10)
# Eine Stunde, wie die Spec es in Abschnitt 5 vorgibt.
ZUGRIFF_GUELTIGKEIT = timedelta(hours=1)
# 30 Tage. Laenger waere unnoetig, kuerzer hiesse, dass die Lehrerin den
# Connector regelmaessig neu verbinden muss.
ERNEUERUNG_GUELTIGKEIT = timedelta(days=30)


class OAuthFehler(Exception):
    """Eine Ablehnung mit RFC-Code und deutschem Klartext."""

    def __init__(self, code: str, beschreibung: str) -> None:
        super().__init__(f"{code}: {beschreibung}")
        self.code = code
        self.beschreibung = beschreibung


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


async def client_anlegen(
    sitzung: AsyncSession, client_name: str | None, redirect_uris: list[str]
) -> OAuthClient:
    """Legt einen Client an und gibt ihn zurueck (RFC 7591)."""
    kunde = OAuthClient(
        client_id=neues_geheimnis(),
        client_name=client_name,
        redirect_uris=list(redirect_uris),
        scope=STANDARD_SCOPE,
    )
    sitzung.add(kunde)
    await sitzung.flush()
    return kunde


async def client_holen(sitzung: AsyncSession, client_id: str) -> OAuthClient | None:
    return await sitzung.scalar(
        select(OAuthClient).where(OAuthClient.client_id == client_id)
    )


async def code_ausgeben(
    sitzung: AsyncSession,
    client: OAuthClient,
    redirect_uri: str,
    code_challenge: str,
    resource: str | None,
) -> str:
    """Gibt einen frischen Autorisierungscode aus und gibt ihn im Klartext zurueck.

    In der Datenbank landet nur der gepfefferte Hash. Die familie_id, die
    hier entsteht, begleitet alle Tokens, die spaeter aus diesem Code
    hervorgehen.
    """
    code = neues_geheimnis()
    sitzung.add(
        OAuthCode(
            code_hash=pfeffern(code),
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            scope=client.scope,
            resource=resource,
            familie_id=uuid.uuid4(),
            ablauf_am=_jetzt() + CODE_GUELTIGKEIT,
        )
    )
    await sitzung.flush()
    return code


async def code_einloesen(
    sitzung: AsyncSession,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> OAuthCode:
    """Loest einen Autorisierungscode ein. Genau einmal.

    Raises:
        OAuthFehler: Immer mit dem Code "invalid_grant". Die Spec verlangt in
            Abschnitt 5 ausdruecklich, dass abgelaufene oder zurueckgezogene
            Grants mit invalid_grant beantwortet werden und nicht mit einem
            eigenen Fehlercode. Auch die Beschreibungen bleiben absichtlich
            unspezifisch: Ein Angreifer soll aus der Antwort nicht ablesen
            koennen, welcher der Pruefschritte gescheitert ist.
    """
    abgelehnt = OAuthFehler(
        "invalid_grant",
        "Der Autorisierungscode ist ungueltig, abgelaufen oder bereits "
        "eingeloest. Bitte verbinde den Connector noch einmal.",
    )

    gespeichert = await sitzung.scalar(
        select(OAuthCode).where(OAuthCode.code_hash == pfeffern(code))
    )
    if gespeichert is None:
        raise abgelehnt
    if gespeichert.eingeloest_am is not None:
        # Ein zweites Mal vorgelegter Code heisst: Er wurde abgefangen. Alles,
        # was aus ihm hervorgegangen ist, ist damit wertlos.
        await familie_zurueckziehen(sitzung, gespeichert.familie_id)
        raise abgelehnt
    if gespeichert.ablauf_am <= _jetzt():
        raise abgelehnt
    if not gleich(gespeichert.client_id, client_id):
        raise abgelehnt
    if not gleich(gespeichert.redirect_uri, redirect_uri):
        raise abgelehnt

    try:
        abgeleitet = pkce_ableiten(code_verifier)
    except ValueError as fehler:
        raise abgelehnt from fehler
    if not gleich(gespeichert.code_challenge, abgeleitet):
        raise abgelehnt

    gespeichert.eingeloest_am = _jetzt()
    await sitzung.flush()
    return gespeichert


async def familie_zurueckziehen(sitzung: AsyncSession, familie_id: uuid.UUID) -> None:
    """Zieht alle Tokens einer Familie zurueck.

    Hier ist ein Massen-update() richtig und nicht verboten: OAuthToken
    traegt kein onupdate=func.now() (die Zeile "zurueckgezogen_am" wird
    ausdruecklich gesetzt), und es koennen beliebig viele Zeilen betroffen
    sein. Der Constraint aus den Global Constraints betrifft "bundles" und
    "karten" mit ihrem geaendert_am.
    """
    await sitzung.execute(
        update(OAuthToken)
        .where(OAuthToken.familie_id == familie_id, OAuthToken.zurueckgezogen_am.is_(None))
        .values(zurueckgezogen_am=_jetzt())
    )
    await sitzung.flush()


async def tokenpaar_ausgeben(
    sitzung: AsyncSession,
    client_id: str,
    familie_id: uuid.UUID,
    scope: str,
    resource: str | None,
) -> tuple[str, str, int]:
    """Gibt einen Zugriffs- und einen Erneuerungstoken aus.

    Returns:
        (Zugriffstoken, Erneuerungstoken, Gueltigkeit des Zugriffstokens in
        Sekunden) - alle drei so, wie sie in die Token-Antwort gehoeren.
    """
    zugriff = neues_geheimnis()
    erneuerung = neues_geheimnis()
    jetzt = _jetzt()
    for wert, art, dauer in (
        (zugriff, ART_ZUGRIFF, ZUGRIFF_GUELTIGKEIT),
        (erneuerung, ART_ERNEUERUNG, ERNEUERUNG_GUELTIGKEIT),
    ):
        sitzung.add(
            OAuthToken(
                token_hash=pfeffern(wert),
                art=art,
                client_id=client_id,
                familie_id=familie_id,
                scope=scope,
                resource=resource,
                ablauf_am=jetzt + dauer,
            )
        )
    await sitzung.flush()
    return zugriff, erneuerung, int(ZUGRIFF_GUELTIGKEIT.total_seconds())


async def erneuern(
    sitzung: AsyncSession, erneuerungstoken: str, client_id: str
) -> tuple[str, str, int]:
    """Rotiert ein Tokenpaar. Der alte Erneuerungstoken wird dabei ungueltig.

    Raises:
        OAuthFehler: Immer mit "invalid_grant", siehe code_einloesen().
    """
    abgelehnt = OAuthFehler(
        "invalid_grant",
        "Der Erneuerungstoken ist ungueltig, abgelaufen oder wurde bereits "
        "benutzt. Bitte verbinde den Connector noch einmal.",
    )

    gespeichert = await sitzung.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == pfeffern(erneuerungstoken),
            OAuthToken.art == ART_ERNEUERUNG,
        )
    )
    if gespeichert is None:
        raise abgelehnt
    if gespeichert.zurueckgezogen_am is not None:
        # Wiederverwendung eines bereits rotierten Tokens: Der Token war in
        # fremden Haenden. Auch das frisch ausgegebene Paar wird wertlos,
        # sonst arbeitete der Dieb mit dem neueren weiter.
        await familie_zurueckziehen(sitzung, gespeichert.familie_id)
        raise abgelehnt
    if gespeichert.ablauf_am <= _jetzt():
        raise abgelehnt
    if not gleich(gespeichert.client_id, client_id):
        raise abgelehnt

    gespeichert.zurueckgezogen_am = _jetzt()
    await sitzung.flush()
    return await tokenpaar_ausgeben(
        sitzung,
        client_id=gespeichert.client_id,
        familie_id=gespeichert.familie_id,
        scope=gespeichert.scope,
        resource=gespeichert.resource,
    )


async def zugriffstoken_pruefen(sitzung: AsyncSession, token: str) -> OAuthToken | None:
    """Der Zugriffstoken, wenn er gilt - sonst None.

    Ein Erneuerungstoken kommt hier nie durch: die Art wird mitgeprueft.
    """
    gespeichert = await sitzung.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == pfeffern(token),
            OAuthToken.art == ART_ZUGRIFF,
        )
    )
    if gespeichert is None:
        return None
    if gespeichert.zurueckgezogen_am is not None:
        return None
    if gespeichert.ablauf_am <= _jetzt():
        return None
    return gespeichert
