"""Jinja2-Umgebung. Eine Stelle, an der HTML entsteht - sonst gibt es zwei Wege."""

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

VERZEICHNIS = Path(__file__).parent

_umgebung = Jinja2Templates(directory=str(VERZEICHNIS))
# autoescape ist bei Jinja2Templates fuer .html voreingestellt und bleibt an.
# Wo bereits gesaeubertes HTML eingesetzt wird, steht im Template ausdruecklich
# ein `| safe` mit Begruendung - nirgends sonst.


def rendern(request, name: str, status_code: int = 200, **kontext) -> HTMLResponse:
    return _umgebung.TemplateResponse(
        request=request, name=name, context=kontext, status_code=status_code
    )
