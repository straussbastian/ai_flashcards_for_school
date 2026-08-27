from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler as _standard_http_exception_handler
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routen import lernseite, oauth, system
from app.routen.lernseite import _nicht_gefunden
from app.sicherheit import Schutzkoepfe
from app.templates import VERZEICHNIS

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

app.add_middleware(Schutzkoepfe)

app.mount("/static", StaticFiles(directory=str(VERZEICHNIS.parent / "static")), name="static")

app.include_router(system.router)
app.include_router(oauth.router)
# Muss als letzter kommen: /{slug} ist zwar durch ein Muster begrenzt, aber
# eine spaetere Route mit gleicher Form wuerde sonst verdeckt.
app.include_router(lernseite.router)


@app.exception_handler(StarletteHTTPException)
async def _404_als_deutsche_seite(request: Request, exc: StarletteHTTPException) -> Response:
    """Ein 404, das nicht schon /{slug} beantwortet hat, bekommt trotzdem die deutsche Seite.

    Nicht jede 404 laeuft durch app.routen.lernseite: Eine Adresse mit
    mehr als einem Pfadsegment (z.B. /ein-zwei-drei/vier), eine ohne
    Segment ueberhaupt passendes Muster (z.B. /.well-known/acme) oder eine
    fehlende Datei unter /static passt zu keiner Route und wird von
    Starlette selbst mit seinem englischen Standard-JSON beantwortet.
    Schueler saehen das bei jedem vertippten Link mit Schraegstrich. Dieser
    Handler faengt ausschliesslich den Statuscode 404 ab und rendert
    dieselbe Antwort wie _nicht_gefunden() in app.routen.lernseite - jede
    andere HTTPException (z.B. 405 Method Not Allowed) geht unveraendert an
    FastAPIs eigenen Standardhandler weiter.
    """
    if exc.status_code == 404:
        return _nicht_gefunden(request)
    return await _standard_http_exception_handler(request, exc)
