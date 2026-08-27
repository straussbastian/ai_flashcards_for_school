"""Die acht Werkzeuge.

Duenne Huellen: Sie oeffnen eine Sitzung, rufen app/mcp/dienste.py, machen
die Aenderung fest und bauen die Antwort. Jede schreibende Antwort enthaelt
den fertigen Link - so verlangt es die Spec in Abschnitt 5.

Die Fehlerbehandlung steht an genau einer Stelle: im Dekorator
@als_werkzeug. Ein MCPFehler wird zum ToolError des SDK, und dessen Text
kommt beim Agenten als isError-Antwort an. Das SDK stellt dabei das
englische "Error executing tool <name>: " voran - das ist nicht abschaltbar
und in Entscheidung E-7 des Plans begruendet; der deutsche Satz steht
dahinter, und er ist es, den die Lehrerin hoert.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.config import get_settings
from app.mcp import dienste
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.models import Bundle
from app.sitzung import sitzung


def als_werkzeug(funktion: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Uebersetzt MCPFehler in die Fehlerantwort des SDK."""

    @functools.wraps(funktion)
    async def huelle(*args: Any, **kwargs: Any) -> Any:
        try:
            return await funktion(*args, **kwargs)
        except MCPFehler as fehler:
            raise ToolError(str(fehler)) from fehler

    return huelle


def url(slug: str) -> str:
    return get_settings().bundle_url(slug)


def uebersicht(bundle: Bundle, anzahl_karten: int) -> dict:
    """Die Kurzform eines Lernpakets - in jeder Antwort dieselbe."""
    return {
        "slug": bundle.slug,
        "url": url(bundle.slug),
        "titel": bundle.titel,
        "beschreibung": bundle.beschreibung or "",
        "klasse": bundle.klasse or "",
        "selbsteinschaetzung": bundle.selbsteinschaetzung,
        "reihenfolge": bundle.reihenfolge,
        "aktiv": bundle.aktiv,
        "anzahl_karten": anzahl_karten,
    }


def karte_ausgeben(karte) -> dict:
    """Eine Karte so, wie der Agent sie zurueckbekommt.

    Die richtige Antwort kommt als TEXT zurueck, nicht als Index: So kann der
    Agent eine Karte unveraendert wieder an karte_aendern uebergeben, ohne
    zwischen zwei Darstellungen umzurechnen.
    """
    daten = {
        "karte_id": str(karte.id),
        "position": karte.position,
        "art": karte.art,
        "vorderseite": karte.vorderseite,
    }
    if karte.art == "flashcard":
        daten["rueckseite"] = karte.rueckseite
        return daten
    antworten = list(karte.antworten or [])
    daten["antworten"] = antworten
    daten["richtige_antwort"] = antworten[karte.richtige_index]
    daten["erklaerung"] = karte.erklaerung or ""
    return daten


def registrieren(server: MCPServer) -> None:
    """Haengt alle Werkzeuge an den Server."""

    @server.tool(
        description=(
            "Legt ein neues Lernpaket an und gibt den fertigen Link zurueck. "
            "Ein Aufruf genuegt fuer ein komplettes Arbeitsblatt: Titel und "
            "alle Karten auf einmal uebergeben.\n\n"
            "WICHTIG fuer Fragen: Benutze KEINE Antwortmoeglichkeiten wie "
            "'keine der genannten' oder 'A und B sind richtig'. Die "
            "Reihenfolge der Antworten wird bei jedem Durchlauf neu gemischt "
            "- solche Moeglichkeiten ergeben danach keinen Sinn mehr."
        )
    )
    @als_werkzeug
    async def bundle_anlegen(
        titel: Annotated[str, Field(description="Ueberschrift der Lernseite.")],
        karten: Annotated[list[KarteEingabe], Field(description="Die Karten des Lernpakets.")],
        beschreibung: Annotated[
            str | None, Field(default=None, description="Optionaler Einleitungstext, Markdown.")
        ] = None,
        klasse: Annotated[
            str | None, Field(default=None, description="Optionale Klassenbezeichnung, z.B. 'FS 23b'.")
        ] = None,
        selbsteinschaetzung: Annotated[
            bool,
            Field(
                default=True,
                description=(
                    "Ob Flashcards beim Ergebnis mitzaehlen ('Wusste ich' / "
                    "'Wusste ich nicht'). Standard: ja."
                ),
            ),
        ] = True,
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_anlegen(
                offene,
                titel=titel,
                beschreibung=beschreibung,
                klasse=klasse,
                selbsteinschaetzung=selbsteinschaetzung,
                karten=karten,
            )
            antwort = uebersicht(bundle, len(bundle.karten))
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Listet alle Lernpakete mit Adresse, Link, Titel, Klasse, "
            "Kartenzahl und Zustand auf."
        )
    )
    @als_werkzeug
    async def bundle_liste(
        klasse: Annotated[
            str | None,
            Field(default=None, description="Nur Lernpakete dieser Klasse."),
        ] = None,
        nur_aktive: Annotated[
            bool,
            Field(default=False, description="Deaktivierte Lernpakete weglassen."),
        ] = False,
    ) -> dict:
        async with sitzung() as offene:
            zeilen = await dienste.bundles_auflisten(
                offene, klasse=klasse, nur_aktive=nur_aktive
            )
            return {
                "anzahl": len(zeilen),
                "bundles": [uebersicht(bundle, anzahl) for bundle, anzahl in zeilen],
            }

    @server.tool(
        description=(
            "Zeigt ein Lernpaket mit allen Karten, ihren IDs und ihren "
            "Positionen. Die IDs braucht man fuer karte_aendern und "
            "karte_loeschen."
        )
    )
    @als_werkzeug
    async def bundle_anzeigen(
        slug: Annotated[str, Field(description="Die Drei-Wort-Adresse des Lernpakets.")],
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_holen(offene, slug)
            karten = sorted(bundle.karten, key=lambda eine: eine.position)
            return {
                **uebersicht(bundle, len(karten)),
                "karten": [karte_ausgeben(eine) for eine in karten],
            }
