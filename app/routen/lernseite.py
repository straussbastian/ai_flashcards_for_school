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

# Dieselben erlaubten Zeichen, die app/slug.py erzeugt und tests/test_slug.py
# erzwingt ([a-z]+ je Wortgruppe). Ohne dieses Muster wuerde die Route auch
# /favicon.ico und alles andere schlucken und fuer jeden Unsinn die
# Datenbank fragen.
#
# {1,40} statt des unbegrenzten [a-z]+ aus tests/test_slug.py: 40 Zeichen
# fassen das laengste Wort in app/woerter (10 Zeichen) grosszuegig, und
# bundles.slug ist auf 120 Zeichen begrenzt (siehe app/models.py) - eine
# Adresse ueber dieser Laenge kann nie existieren und muss die Datenbank
# gar nicht erst fragen.
#
# Das Muster wird unten von Hand mit re.fullmatch geprueft und NICHT ueber
# Path(pattern=ADRESSE) an Pydantic gegeben: Eine per Path(pattern=...)
# abgelehnte Adresse beantwortet FastAPI standardmaessig mit 422
# (RequestValidationError), nicht mit 404 - das ergibt fuer eine oeffentliche
# URL, die es schlicht nicht gibt, die falsche Fehlerklasse und wurde hier
# beim Testlauf tatsaechlich beobachtet.
#
# re.fullmatch statt re.match mit einem "$"-Anker im Muster: Pythons "$"
# matcht auch unmittelbar vor einem abschliessenden "\n" - re.match(ADRESSE,
# "kluge-tafel-leuchtet\n") haette also gehalten, obwohl der Slug einen
# Zeilenumbruch enthaelt, und die Datenbank waere trotzdem gefragt worden
# (nachgemessen: GET /kluge-tafel-leuchtet%0A). Sicherheitsfolge hatte das
# keine, da kein Spaltenwert je einen Zeilenumbruch enthaelt, aber es
# widersprach der Zusage weiter unten, dass die Datenbank fuer Unsinn gar
# nicht erst gefragt wird. re.fullmatch verankert an beiden Enden ohne
# dieses Schlupfloch und macht die "^"/"$"-Anker im Muster ueberfluessig.
ADRESSE = r"[a-z]{1,40}-[a-z]{1,40}-[a-z]{1,40}"


def _nicht_gefunden(request: Request) -> HTMLResponse:
    """Die 404-Antwort fuer eine unbekannte Adresse.

    Eine wohlgeformte, aber unbekannte Adresse (kein Bundle mit diesem Slug)
    und eine formal falsche Adresse (faellt schon durch ADRESSE) muessen
    dieselbe Antwort liefern - sonst liesse sich aus dem Unterschied
    erraten, ob ein Adressmuster ueberhaupt in der richtigen Form war.
    Beide Aufrufer teilen sich deshalb diese eine Funktion statt zweier
    wortgleicher Kopien, die auseinanderlaufen koennten.
    """
    return rendern(request, "fehler.html", status_code=404,
                   ueberschrift="Diese Lernseite gibt es nicht",
                   text="Pruef den Link, den du bekommen hast.")


def _einbetten(daten: dict) -> str:
    """JSON so einbetten, dass eine Karte den Datenblock nicht beenden kann.

    Enthaelt ein Karteninhalt die Zeichenfolge `</script>`, wuerde sie beim
    naiven Einbetten den Block beenden und alles danach wuerde als Skript
    ausgefuehrt. Das faengt die Markdown-Saeuberung nicht ab, weil sie den
    Inhalt saeubert und nicht die Art der Einbettung.

    `<`, `>` und `&` werden zusaetzlich zu U+2028/U+2029 (LINE SEPARATOR /
    PARAGRAPH SEPARATOR) entschaerft: Beide gelten in JavaScript-Quelltext
    als Zeilenumbruch, waeren also gefaehrlich, sobald dieser Block je als
    Skript statt als reine Textdaten gelesen wuerde. Heute ist das
    folgenlos, weil der Block mit type="application/json" nie ausgefuehrt
    wird und JSON.parse mit beiden Zeichen umgehen kann - aber die
    Entschaerfung kostet nichts und macht die Sicherheit unabhaengig davon,
    wie ein spaeterer Runner an die Daten kommt.
    """
    roh = json.dumps(daten, ensure_ascii=False)
    return (
        roh.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(" ", "\\u2028")
        .replace(" ", "\\u2029")
    )


@router.get("/{slug}", response_class=HTMLResponse)
async def lernseite(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    if not re.fullmatch(ADRESSE, slug):
        return _nicht_gefunden(request)

    bundle = await session.scalar(select(Bundle).where(Bundle.slug == slug))

    if bundle is None:
        return _nicht_gefunden(request)

    if not bundle.aktiv:
        return rendern(request, "fehler.html", status_code=410,
                       ueberschrift="Diese Lernseite ist nicht mehr aktiv",
                       text="Deine Lehrkraft hat sie stillgelegt.")

    daten = bauen(bundle)
    return rendern(request, "lernseite.html", bundle=daten, daten=_einbetten(daten))
