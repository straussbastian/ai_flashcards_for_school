"""Schutzkoepfe fuer alle Antworten.

Die Markdown-Saeuberung ist die erste Verteidigungslinie fuer Inhalte, die
ueber MCP hereinkommen. Diese Richtlinie ist die zweite - und hier besonders
billig, weil die Seite nichts Fremdes braucht: keine externen Skripte, keine
Bilder, keine Webfonts (die Spec legt system-ui fest).
"""

from starlette.middleware.base import BaseHTTPMiddleware

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
ZUSTIMMUNG_RICHTLINIE = RICHTLINIE.replace(
    "form-action 'none'",
    "form-action 'self' https://claude.ai http://localhost:* http://127.0.0.1:*",
)

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
        antwort.headers["Content-Security-Policy"] = (
            ZUSTIMMUNG_RICHTLINIE
            if request.url.path == ZUSTIMMUNG_PFAD
            else RICHTLINIE
        )
        return antwort
