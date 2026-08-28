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
from app.mcp.eingaben import KarteAenderung, KarteEingabe
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
            "Legt ein neues Lernpaket an und gibt den fertigen Link zurück. "
            "Ein Aufruf genügt für ein komplettes Arbeitsblatt: Titel und "
            "alle Karten auf einmal übergeben.\n\n"
            "WICHTIG für Fragen: Benutze KEINE Antwortmöglichkeiten wie "
            "'keine der genannten' oder 'A und B sind richtig'. Die "
            "Reihenfolge der Antworten wird bei jedem Durchlauf neu gemischt "
            "- solche Möglichkeiten ergeben danach keinen Sinn mehr."
        )
    )
    @als_werkzeug
    async def bundle_anlegen(
        titel: Annotated[str, Field(description="Überschrift der Lernseite.")],
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
            "Positionen. Die IDs braucht man für karte_aendern und "
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

    @server.tool(
        description=(
            "Hängt weitere Karten hinten an ein bestehendes Lernpaket an "
            "und gibt die neuen Karten mit ihren IDs zurück. Die Reihenfolge "
            "der vorhandenen Karten bleibt unberührt.\n\n"
            "WICHTIG für Fragen: Benutze KEINE Antwortmöglichkeiten wie "
            "'keine der genannten' oder 'A und B sind richtig'. Die "
            "Reihenfolge der Antworten wird bei jedem Durchlauf neu gemischt "
            "- solche Möglichkeiten ergeben danach keinen Sinn mehr."
        )
    )
    @als_werkzeug
    async def karten_hinzufuegen(
        slug: Annotated[str, Field(description="Die Drei-Wort-Adresse des Lernpakets.")],
        karten: Annotated[list[KarteEingabe], Field(description="Die neuen Karten.")],
    ) -> dict:
        async with sitzung() as offene:
            bundle, neue = await dienste.karten_anhaengen(offene, slug=slug, karten=karten)
            gesamt = await dienste.karten_zaehlen(offene, bundle.id)
            antwort = {
                **uebersicht(bundle, gesamt),
                "neue_karten": [karte_ausgeben(eine) for eine in neue],
            }
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Ändert einzelne Felder einer Karte. Was nicht angegeben ist, "
            "bleibt unverändert. Die Karten-ID bekommst du von "
            "bundle_anzeigen.\n\n"
            "Wenn du bei einer Frage die Antwortmöglichkeiten austauschst, "
            "gib 'richtige_antwort' mit an - sonst muss der alte Text in der "
            "neuen Liste noch vorkommen."
        )
    )
    @als_werkzeug
    async def karte_aendern(
        karte_id: Annotated[str, Field(description="Die ID der Karte aus bundle_anzeigen.")],
        vorderseite: Annotated[
            str | None,
            Field(default=None, description="Neuer Begriff bzw. neue Frage."),
        ] = None,
        rueckseite: Annotated[
            str | None,
            Field(default=None, description="Nur bei Flashcards: die neue Lösung."),
        ] = None,
        antworten: Annotated[
            list[str] | None,
            Field(default=None, description="Nur bei Fragen: die neuen Antwortmöglichkeiten."),
        ] = None,
        richtige_antwort: Annotated[
            str | None,
            Field(default=None, description="Nur bei Fragen: der TEXT der richtigen Antwort."),
        ] = None,
        erklaerung: Annotated[
            str | None,
            Field(default=None, description="Nur bei Fragen: die neue Erklärung."),
        ] = None,
    ) -> dict:
        aenderung = KarteAenderung(
            vorderseite=vorderseite,
            rueckseite=rueckseite,
            antworten=antworten,
            richtige_antwort=richtige_antwort,
            erklaerung=erklaerung,
        )
        async with sitzung() as offene:
            bundle, karte = await dienste.karte_aendern(
                offene, karte_id=karte_id, aenderung=aenderung
            )
            antwort = {
                **uebersicht(bundle, await dienste.karten_zaehlen(offene, bundle.id)),
                "karte": karte_ausgeben(karte),
            }
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Löscht eine einzelne Karte aus einem Lernpaket. Die Positionen "
            "der übrigen Karten bleiben unverändert. Die letzte Karte eines "
            "Lernpakets lässt sich nicht löschen - dafür gibt es "
            "bundle_deaktivieren."
        )
    )
    @als_werkzeug
    async def karte_loeschen(
        karte_id: Annotated[str, Field(description="Die ID der Karte aus bundle_anzeigen.")],
    ) -> dict:
        async with sitzung() as offene:
            bundle, uebrig = await dienste.karte_loeschen(offene, karte_id=karte_id)
            antwort = {**uebersicht(bundle, uebrig), "geloescht": karte_id}
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Ändert die Kopfdaten eines Lernpakets: Titel, Beschreibung, "
            "Klasse, Selbsteinschätzung, Reihenfolge. Was nicht angegeben "
            "ist, bleibt unverändert; ein leerer Text löscht ein optionales "
            "Feld. Die Adresse des Lernpakets ändert sich dabei nie - "
            "bereits weitergegebene Links bleiben gültig."
        )
    )
    @als_werkzeug
    async def bundle_aendern(
        slug: Annotated[str, Field(description="Die Drei-Wort-Adresse des Lernpakets.")],
        titel: Annotated[
            str | None, Field(default=None, description="Neue Überschrift der Lernseite.")
        ] = None,
        beschreibung: Annotated[
            str | None,
            Field(default=None, description="Neuer Einleitungstext. Leerer Text löscht ihn."),
        ] = None,
        klasse: Annotated[
            str | None,
            Field(default=None, description="Neue Klassenbezeichnung. Leerer Text löscht sie."),
        ] = None,
        selbsteinschaetzung: Annotated[
            bool | None,
            Field(default=None, description="Ob Flashcards beim Ergebnis mitzählen."),
        ] = None,
        reihenfolge: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "'zufall' mischt die Karten bei jedem Durchlauf, 'fest' "
                    "zeigt sie immer in derselben Reihenfolge."
                ),
            ),
        ] = None,
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_aendern(
                offene,
                slug=slug,
                titel=titel,
                beschreibung=beschreibung,
                klasse=klasse,
                selbsteinschaetzung=selbsteinschaetzung,
                reihenfolge=reihenfolge,
            )
            antwort = uebersicht(bundle, await dienste.karten_zaehlen(offene, bundle.id))
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Schaltet ein Lernpaket unsichtbar (aktiv=false) oder wieder "
            "sichtbar (aktiv=true). Es wird dabei NICHTS gelöscht: Das "
            "Lernpaket und alle Karten bleiben erhalten, die Seite zeigt nur "
            "einen Hinweis. Endgültiges Löschen gibt es über diese Werkzeuge "
            "bewusst nicht."
        )
    )
    @als_werkzeug
    async def bundle_deaktivieren(
        slug: Annotated[str, Field(description="Die Drei-Wort-Adresse des Lernpakets.")],
        aktiv: Annotated[
            bool,
            Field(description="false schaltet unsichtbar, true wieder sichtbar."),
        ],
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_umschalten(offene, slug=slug, aktiv=aktiv)
            antwort = uebersicht(bundle, await dienste.karten_zaehlen(offene, bundle.id))
            await offene.commit()
            return antwort
