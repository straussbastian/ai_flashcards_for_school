import json
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bundle_json import bauen
from app.db import get_session
from app.models import Bundle
from app.templates import rendern

router = APIRouter()

# Dasselbe Muster, das app/slug.py erzeugt und tests/test_slug.py erzwingt.
# Ohne dieses Muster wuerde die Route auch /favicon.ico und alles andere
# schlucken und fuer jeden Unsinn die Datenbank fragen.
#
# Das Muster wird unten von Hand mit re.match geprueft und NICHT ueber
# Path(pattern=ADRESSE) an Pydantic gegeben: Eine per Path(pattern=...)
# abgelehnte Adresse beantwortet FastAPI standardmaessig mit 422
# (RequestValidationError), nicht mit 404 - das ergibt fuer eine oeffentliche
# URL, die es schlicht nicht gibt, die falsche Fehlerklasse und wurde hier
# beim Testlauf tatsaechlich beobachtet. Der manuelle Check unten liefert in
# jedem Fall 404, bevor die Datenbank gefragt wird.
ADRESSE = r"^[a-z]+-[a-z]+-[a-z]+$"


def _einbetten(daten: dict) -> str:
    """JSON so einbetten, dass eine Karte den Datenblock nicht beenden kann.

    Enthaelt ein Karteninhalt die Zeichenfolge `</script>`, wuerde sie beim
    naiven Einbetten den Block beenden und alles danach wuerde als Skript
    ausgefuehrt. Das faengt die Markdown-Saeuberung nicht ab, weil sie den
    Inhalt saeubert und nicht die Art der Einbettung.
    """
    roh = json.dumps(daten, ensure_ascii=False)
    return roh.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


@router.get("/{slug}", response_class=HTMLResponse)
async def lernseite(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    if not re.match(ADRESSE, slug):
        return rendern(request, "fehler.html", status_code=404,
                       ueberschrift="Diese Lernseite gibt es nicht",
                       text="Pruef den Link, den du bekommen hast.")

    bundle = await session.scalar(select(Bundle).where(Bundle.slug == slug))

    if bundle is None:
        return rendern(request, "fehler.html", status_code=404,
                       ueberschrift="Diese Lernseite gibt es nicht",
                       text="Pruef den Link, den du bekommen hast.")

    if not bundle.aktiv:
        return rendern(request, "fehler.html", status_code=410,
                       ueberschrift="Diese Lernseite ist nicht mehr aktiv",
                       text="Deine Lehrkraft hat sie stillgelegt.")

    daten = bauen(bundle)
    return rendern(request, "lernseite.html", bundle=daten, daten=_einbetten(daten))
