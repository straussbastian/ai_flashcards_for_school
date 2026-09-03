import json
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bundle_json import bauen
from app.db import get_session
from app.models import Adresse, Bundle, Sammlung, SammlungPaket
from app.markdown import rendern as markdown_rendern
from app.templates import rendern

router = APIRouter()

# Dieselben erlaubten Zeichen, die app/slug.py erzeugt und tests/test_slug.py
# erzwingt ([a-z]+ je Wortgruppe). Ohne dieses Muster wuerde die Route auch
# /favicon.ico und alles andere schlucken und fuer jeden Unsinn die
# Datenbank fragen.
#
# {1,39} statt des unbegrenzten [a-z]+ aus tests/test_slug.py: 39 Zeichen
# fassen das laengste Wort in app/woerter (10 Zeichen) grosszuegig, und
# bundles.slug ist auf 120 Zeichen begrenzt (siehe app/models.py). Mit drei
# Wortgruppen zu je hoechstens 39 Zeichen plus zwei Bindestrichen passt eine
# Adresse hoechstens in 3*39+2=119 Zeichen - eine Adresse ueber der
# Spaltengrenze von 120 kann damit nie matchen und muss die Datenbank gar
# nicht erst fragen. (Mit dem frueheren Wert 40 waeren es 3*40+2=122
# gewesen - zwei Zeichen mehr, als die Spalte je fassen kann.)
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
ADRESSE = r"[a-z]{1,39}-[a-z]{1,39}-[a-z]{1,39}"


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
                   text="Prüf den Link, den du bekommen hast.")


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


def _stillgelegt(request: Request) -> HTMLResponse:
    return rendern(request, "fehler.html", status_code=410,
                   ueberschrift="Diese Lernseite ist nicht mehr aktiv",
                   text="Deine Lehrkraft hat sie stillgelegt.")


async def _pakete_der_sammlung(session: AsyncSession, sammlung: Sammlung) -> list[Bundle]:
    """Die aktiven Lernpakete einer Sammlung in ihrer Reihenfolge."""
    zeilen = await session.scalars(
        select(Bundle)
        .join(SammlungPaket, SammlungPaket.bundle_id == Bundle.id)
        .where(SammlungPaket.sammlung_id == sammlung.id, Bundle.aktiv.is_(True))
        .order_by(SammlungPaket.position)
    )
    return list(zeilen)


# Diese Route MUSS vor /{slug} stehen: Starlette nimmt die erste passende,
# und ein einzelnes /{slug} wuerde eine zweisegmentige Adresse ohnehin nicht
# fangen - aber die Reihenfolge festzuhalten erspart der naechsten Aenderung
# eine Suche.
@router.get("/{sammlung_slug}/{paket_slug}", response_class=HTMLResponse)
async def lernseite_in_sammlung(
    request: Request,
    sammlung_slug: str,
    paket_slug: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Ein Lernpaket im Kontext einer Sammlung.

    Der Kontext steht in der Adresse und nicht in den Daten, weil ein
    Lernpaket zu MEHREREN Sammlungen gehoeren kann (n:m). Aus der
    Zugehoerigkeit allein liesse sich nicht ableiten, wohin "zurueck" fuehrt
    und was das naechste Paket ist - aus dem Weg hierher schon.
    """
    if not (re.fullmatch(ADRESSE, sammlung_slug) and re.fullmatch(ADRESSE, paket_slug)):
        return _nicht_gefunden(request)

    sammlung = await session.scalar(
        select(Sammlung).where(Sammlung.slug == sammlung_slug)
    )
    if sammlung is None:
        return _nicht_gefunden(request)
    if not sammlung.aktiv:
        return _stillgelegt(request)

    pakete = await _pakete_der_sammlung(session, sammlung)
    stelle = next((i for i, p in enumerate(pakete) if p.slug == paket_slug), None)
    if stelle is None:
        # Das Paket gibt es nicht, es ist stillgelegt, oder es gehoert nicht
        # zu dieser Sammlung. Alle drei enden hier als 404 - und der letzte
        # Fall ausdruecklich NICHT als stillschweigend ausgeliefertes Paket
        # ohne Kontext: Eine erfundene Kombination ist ein Irrtum und soll
        # als solcher erscheinen.
        return _nicht_gefunden(request)

    bundle = pakete[stelle]
    naechstes = pakete[stelle + 1] if stelle + 1 < len(pakete) else None

    daten = bauen(bundle)
    daten["sammlung"] = {
        "titel": sammlung.titel,
        "url": f"/{sammlung.slug}",
        "naechstes": (
            {"titel": naechstes.titel, "url": f"/{sammlung.slug}/{naechstes.slug}"}
            if naechstes else None
        ),
    }
    return rendern(request, "lernseite.html", bundle=daten, daten=_einbetten(daten))


@router.get("/{slug}", response_class=HTMLResponse)
async def lernseite(
    request: Request,
    slug: str,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Ein Lernpaket ODER eine Sammlung - die Adresstabelle entscheidet.

    Beide teilen sich einen Adressraum (siehe app/models.py, Adresse), und
    "art" sagt, was unter dieser Adresse liegt. Damit muss nicht erst die
    eine und dann die andere Tabelle gefragt werden.
    """
    if not re.fullmatch(ADRESSE, slug):
        return _nicht_gefunden(request)

    # select(...) + scalar() statt session.get(): Diese Datei fragt ueberall
    # so, und tests/test_sicherheit.py reicht eine Attrappe herein, die genau
    # diese eine Methode kennt. Einheitlich zu bleiben ist hier billiger, als
    # die Attrappe zu erweitern.
    adresse = await session.scalar(select(Adresse).where(Adresse.slug == slug))
    if adresse is None:
        return _nicht_gefunden(request)

    if adresse.art == "sammlung":
        sammlung = await session.scalar(select(Sammlung).where(Sammlung.slug == slug))
        if sammlung is None:
            return _nicht_gefunden(request)
        if not sammlung.aktiv:
            return _stillgelegt(request)
        return rendern(
            request, "sammlung.html",
            sammlung=sammlung,
            # Durch rendern() aus app/markdown.py, wie jedes andere
            # Markdown-Feld: markdown-it rendert, nh3 saeubert. Das Template
            # setzt es mit |safe ein und darf das nur deshalb.
            beschreibung_html=markdown_rendern(sammlung.beschreibung or ""),
            pakete=await _pakete_der_sammlung(session, sammlung),
        )

    bundle = await session.scalar(select(Bundle).where(Bundle.slug == slug))
    if bundle is None:
        return _nicht_gefunden(request)
    if not bundle.aktiv:
        return _stillgelegt(request)

    daten = bauen(bundle)
    return rendern(request, "lernseite.html", bundle=daten, daten=_einbetten(daten))
