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


class Schutzkoepfe(BaseHTTPMiddleware):
    """Haengt die Richtlinie und zwei weitere Schutzkoepfe an jede Antwort."""

    async def dispatch(self, request, call_next):
        """Laesst die Anfrage durch und ergaenzt die Antwort um die Schutzkoepfe."""
        antwort = await call_next(request)
        antwort.headers["Content-Security-Policy"] = RICHTLINIE
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        return antwort
