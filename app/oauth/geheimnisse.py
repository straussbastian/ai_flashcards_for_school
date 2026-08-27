"""Zufall, Pfeffer und PKCE.

Alle Geheimnisse dieses Servers entstehen hier, und alle Vergleiche laufen
konstantzeitig. Gespeichert wird nie ein Geheimnis, sondern immer nur sein
mit APP_SECRET gepfefferter HMAC-SHA256 - ein gestohlener
Datenbankauszug enthaelt damit keine benutzbaren Tokens.
"""

import base64
import hashlib
import hmac
import re
import secrets

from app.config import get_settings

# 32 Byte Zufall, base64url ohne Polster: 43 Zeichen. Das ist zugleich die
# Untergrenze, die RFC 7636 fuer einen code_verifier vorschreibt.
GEHEIMNIS_BYTES = 32

# RFC 7636, Abschnitt 4.1: 43 bis 128 Zeichen aus [A-Za-z0-9-._~].
_VERIFIER_MUSTER = re.compile(r"[A-Za-z0-9\-._~]{43,128}")


def _ohne_polster(rohbytes: bytes) -> str:
    return base64.urlsafe_b64encode(rohbytes).decode("ascii").rstrip("=")


def neues_geheimnis() -> str:
    """Ein frisches, URL-sicheres Geheimnis mit 256 Bit Entropie."""
    return _ohne_polster(secrets.token_bytes(GEHEIMNIS_BYTES))


def pfeffern(wert: str) -> str:
    """Der HMAC-SHA256 des Wertes unter APP_SECRET, hexadezimal.

    HMAC statt eines nackten sha256: Ohne Schluessel liesse sich zu einem
    erbeuteten Hash der zugehoerige Token offline suchen. Mit Schluessel
    braucht es dafuer zusaetzlich APP_SECRET, und das steht nicht in der
    Datenbank.

    Absichtlich KEIN Passwort-Hash (argon2, bcrypt): Die Werte sind
    256-Bit-Zufall, nicht ratbare Passwoerter. Ein langsamer Hash brauchte
    hier bei jeder MCP-Anfrage Rechenzeit, ohne etwas zu schuetzen.
    """
    schluessel = get_settings().app_secret.encode("utf-8")
    return hmac.new(schluessel, wert.encode("utf-8"), hashlib.sha256).hexdigest()


def gleich(links: str, rechts: str) -> bool:
    """Konstantzeitiger Vergleich zweier Zeichenketten."""
    return hmac.compare_digest(links, rechts)


def pkce_ableiten(code_verifier: str) -> str:
    """Die code_challenge zu einem code_verifier nach RFC 7636, Methode S256.

    Raises:
        ValueError: Wenn der Verifier nicht dem Format aus RFC 7636 entspricht.
            Die Pruefung gehoert hierher und nicht zum Aufrufer: Ein zu kurzer
            Verifier haette weniger Entropie als vorgeschrieben, und das darf
            nicht davon abhaengen, ob eine Route daran gedacht hat.
    """
    if not _VERIFIER_MUSTER.fullmatch(code_verifier):
        raise ValueError(
            "Der code_verifier entspricht nicht RFC 7636: erwartet werden 43 "
            "bis 128 Zeichen aus A-Z, a-z, 0-9 und den Zeichen - . _ ~"
        )
    return _ohne_polster(hashlib.sha256(code_verifier.encode("ascii")).digest())
