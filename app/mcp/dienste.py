"""Die Datenbankarbeit hinter den Werkzeugen.

Kennt kein MCP. Jede Ablehnung verlaesst dieses Modul als MCPFehler mit
deutschem Klartext.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import beschreibung_pruefen, karte_pruefen, klasse_pruefen, titel_pruefen
from app.models import Bundle, Karte
from app.slug import SlugKollision, freien_slug_finden

# Drei Anlaeufe. freien_slug_finden() wuerfelt selbst schon bis zu zehnmal
# und prueft dabei jedes Mal die Datenbank; diese Schleife hier faengt
# ausschliesslich den Wettlauf ab - zwei gleichzeitige Aufrufe, die denselben
# freien Kandidaten ziehen. Dass das dreimal hintereinander passiert, ist bei
# einer Nutzerin ausgeschlossen.
SLUG_VERSUCHE = 3


async def bundle_holen(sitzung: AsyncSession, slug: str) -> Bundle:
    """Das Bundle zu einem Slug.

    Raises:
        MCPFehler: Wenn es keines gibt. Die Meldung nennt das Werkzeug zum
            Nachsehen - so steht sie in der Spec, Abschnitt 5.
    """
    bundle = await sitzung.scalar(select(Bundle).where(Bundle.slug == slug))
    if bundle is None:
        raise MCPFehler(
            f"Ein Lernpaket mit der Adresse „{slug}“ gibt es nicht. Mit "
            "bundle_liste siehst du alle vorhandenen."
        )
    return bundle


async def karte_holen(sitzung: AsyncSession, karte_id: str) -> Karte:
    """Die Karte zu einer ID.

    Raises:
        MCPFehler: Wenn die ID keine ist oder es die Karte nicht gibt.
    """
    try:
        kennung = uuid.UUID(karte_id)
    except (ValueError, AttributeError, TypeError) as fehler:
        raise MCPFehler(
            f"„{karte_id}“ ist keine Karten-ID. Die IDs stehen bei jeder "
            "Karte, die bundle_anzeigen ausgibt."
        ) from fehler
    karte = await sitzung.scalar(select(Karte).where(Karte.id == kennung))
    if karte is None:
        raise MCPFehler(
            f"Eine Karte mit der ID {karte_id} gibt es nicht. Mit "
            "bundle_anzeigen siehst du die IDs aller Karten eines Lernpakets."
        )
    return karte


async def bundle_anlegen(
    sitzung: AsyncSession,
    titel: str,
    beschreibung: str | None,
    klasse: str | None,
    selbsteinschaetzung: bool,
    karten: list[KarteEingabe],
) -> Bundle:
    """Legt ein Lernpaket samt Karten an.

    Alles oder nichts: Die Karten werden vollstaendig geprueft, BEVOR
    irgendetwas geschrieben wird. Ein halb angelegtes Lernpaket waere
    schlimmer als keines, weil niemand sieht, was fehlt.

    Raises:
        MCPFehler: Bei jeder abgelehnten Eingabe und wenn keine freie Adresse
            gefunden wird.
    """
    if not karten:
        raise MCPFehler(
            "Das Lernpaket enthält keine Karten. Bitte gib mindestens eine "
            "Karte an – ein Lernpaket ohne Karten kann niemand üben."
        )
    geprueft = [karte_pruefen(eine, nummer) for nummer, eine in enumerate(karten, start=1)]

    felder = {
        "titel": titel_pruefen(titel),
        "beschreibung": beschreibung_pruefen(beschreibung),
        "klasse": klasse_pruefen(klasse),
        "selbsteinschaetzung": selbsteinschaetzung,
    }

    for _ in range(SLUG_VERSUCHE):
        slug = await freien_slug_finden(sitzung)
        bundle = Bundle(slug=slug, **felder)
        bundle.karten = [
            Karte(position=stelle, **werte) for stelle, werte in enumerate(geprueft)
        ]
        try:
            # begin_nested() setzt einen SAVEPOINT. Schlaegt der Einfuegevorgang
            # am Unique-Constraint fehl, wird nur bis dorthin zurueckgerollt und
            # die Sitzung bleibt benutzbar - ein Rollback der ganzen Transaktion
            # wuerde alles verwerfen, was vorher geschah.
            async with sitzung.begin_nested():
                sitzung.add(bundle)
                await sitzung.flush()
        except IntegrityError as fehler:
            if "uq_bundles_slug" not in str(fehler.orig):
                raise
            # Der Wettlauf aus Spec, Abschnitt 4: Zwischen "ist frei" und
            # "ist eingetragen" hat ein zweiter Aufruf denselben Kandidaten
            # gezogen. Das ist kein Fehler, den die Lehrerin lesen soll,
            # sondern ein Signal, noch einmal zu wuerfeln.
            continue
        return bundle

    raise MCPFehler(
        "Es konnte keine freie Drei-Wort-Adresse gefunden werden. Bitte "
        "versuche es noch einmal."
    )


async def bundles_auflisten(
    sitzung: AsyncSession, klasse: str | None, nur_aktive: bool
) -> list[tuple[Bundle, int]]:
    """Alle Lernpakete mit ihrer Kartenzahl, neueste zuerst."""
    abfrage = (
        select(Bundle, func.count(Karte.id))
        .outerjoin(Karte, Karte.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(Bundle.erstellt_am.desc())
    )
    if klasse:
        abfrage = abfrage.where(Bundle.klasse == klasse.strip())
    if nur_aktive:
        abfrage = abfrage.where(Bundle.aktiv.is_(True))
    return [(bundle, anzahl) for bundle, anzahl in (await sitzung.execute(abfrage)).all()]
