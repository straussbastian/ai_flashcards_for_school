"""Schutzkoepfe fuer alle Antworten.

Die Markdown-Saeuberung ist die erste Verteidigungslinie fuer Inhalte, die
ueber MCP hereinkommen. Diese Richtlinie ist die zweite - und hier besonders
billig, weil die Seite nichts Fremdes braucht: keine externen Skripte, keine
Bilder, keine Webfonts (die Spec legt system-ui fest).
"""

from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

RICHTLINIE = "; ".join([
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "connect-src 'none'",   # der Runner spricht nach dem Laden mit niemandem
    "img-src 'none'",
    "font-src 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
])

# Die Zustimmungsseite ist die einzige Seite dieses Projekts mit einem
# Formular. form-action gilt fuer das Ziel des Formulars UND fuer jede
# Weiterleitung, die daraus folgt - deshalb steht hier neben 'self' auch
# claude.ai (die Rueckadresse von Cowork) und die beiden Loopback-Adressen
# (Claude Code, dessen Port beim Start zufaellig ist; CSP erlaubt dafuer
# den Platzhalter :*). Ohne diese Ausnahme braeche der Ablauf im Browser ab,
# ohne dass am Server irgendetwas auffiele.
#
# Freigaben aus EXTRA_REDIRECT_URIS (etwa n8n) kommen mit ihrem Ursprung
# dazu. Der Ursprung und nicht die volle Adresse: CSP vergleicht bei einer
# Weiterleitung den Pfad ohnehin nicht. Dass darin keine Zeichen stehen, die
# die Richtlinie aufbrechen koennten, stellt app/config.py beim Start sicher.
def zustimmung_richtlinie(zusaetzliche: Iterable[str] = ()) -> str:
    """Die Richtlinie der Zustimmungsseite, mit den freigegebenen Ursprüngen."""
    quellen = ["'self'", "https://claude.ai", "http://localhost:*", "http://127.0.0.1:*"]
    for adresse in zusaetzliche:
        teile = urlsplit(adresse)
        ursprung = f"{teile.scheme}://{teile.netloc}"
        if ursprung not in quellen:
            quellen.append(ursprung)
    return RICHTLINIE.replace("form-action 'none'", "form-action " + " ".join(quellen))


ZUSTIMMUNG_RICHTLINIE = zustimmung_richtlinie()

# Der MCP-Endpunkt liefert kein Dokument, sondern JSON-RPC ueber
# Server-Sent-Events. Eine Inhaltsrichtlinie hat dort nichts zu regeln, und
# ein Kopf, den niemand auswertet, ist nur eine weitere Stelle, an der etwas
# schiefgehen kann.
OHNE_RICHTLINIE = frozenset({"/mcp"})

# Der Pfad der Zustimmungsseite. Steht als Konstante da, damit er nicht an
# zwei Stellen (hier und in app/routen/oauth.py) auseinanderlaufen kann.
ZUSTIMMUNG_PFAD = "/oauth/authorize"


class Schutzkoepfe(BaseHTTPMiddleware):
    """Haengt die Richtlinie und zwei weitere Schutzkoepfe an jede Antwort."""

    async def dispatch(self, request, call_next):
        """Laesst die Anfrage durch und ergaenzt die Antwort um die Schutzkoepfe."""
        antwort = await call_next(request)
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path in OHNE_RICHTLINIE:
            return antwort
        # get_settings() nur auf der Zustimmungsseite: Alle anderen Seiten
        # brauchen die Konfiguration fuer ihre Richtlinie nicht.
        antwort.headers["Content-Security-Policy"] = (
            zustimmung_richtlinie(get_settings().extra_redirect_uris)
            if request.url.path == ZUSTIMMUNG_PFAD
            else RICHTLINIE
        )
        return antwort
