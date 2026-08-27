"""Der Anschlusspunkt zwischen unserem OAuth-Server und dem MCP-SDK.

Das SDK ist in diesem Projekt ausschliesslich Resource Server: Es prueft
Bearer-Tokens und gibt selbst keine aus. Der Anschlusspunkt dafuer ist das
Protokoll TokenVerifier mit seiner einen Methode verify_token.
"""

from mcp.server.auth.provider import AccessToken, TokenVerifier

from app.oauth.metadaten import SCOPE
from app.oauth.speicher import zugriffstoken_pruefen
from app.sitzung import sitzung


class TokenPruefer(TokenVerifier):
    """Schlaegt den Token in der Datenbank nach.

    Die Sitzung kommt aus app/sitzung.py und NICHT aus
    get_session_factory(): Diese Methode laeuft in einer Middleware des SDK,
    also ausserhalb von FastAPIs Abhaengigkeitsaufloesung, und wuerde sonst
    in Tests die Entwicklungsdatenbank treffen. Die ausfuehrliche Begruendung
    steht im Docstring von app/sitzung.py.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        async with sitzung() as offene:
            gespeichert = await zugriffstoken_pruefen(offene, token)
            if gespeichert is None:
                return None
            return AccessToken(
                token=token,
                client_id=gespeichert.client_id,
                scopes=[SCOPE],
                expires_at=int(gespeichert.ablauf_am.timestamp()),
                resource=gespeichert.resource,
            )
