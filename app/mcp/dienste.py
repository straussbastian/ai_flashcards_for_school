"""Die Datenbankarbeit hinter den Werkzeugen.

Kennt kein MCP. Jede Ablehnung verlaesst dieses Modul als MCPFehler mit
deutschem Klartext.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.eingaben import KarteAenderung, KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import (
    beschreibung_pruefen,
    karte_pruefen,
    klasse_pruefen,
    reihenfolge_pruefen,
    titel_pruefen,
)
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



async def karten_zaehlen(sitzung: AsyncSession, bundle_id) -> int:
    """Die aktuelle Kartenzahl eines Lernpakets, frisch aus der Datenbank.

    Bewusst eine Abfrage statt len(bundle.karten): Die geladene Sammlung
    kommt aus der Identity Map und weiss nichts von einer Karte, die in
    derselben Sitzung gerade eingefuegt oder geloescht wurde. Ein Werkzeug,
    das dann eine zu niedrige Zahl meldet, waere still falsch.
    """
    return await sitzung.scalar(
        select(func.count(Karte.id)).where(Karte.bundle_id == bundle_id)
    )


async def karten_anhaengen(
    sitzung: AsyncSession, slug: str, karten: list[KarteEingabe]
) -> tuple[Bundle, list[Karte]]:
    """Haengt Karten hinten an ein bestehendes Lernpaket an.

    Alles oder nichts, wie bei bundle_anlegen: Erst werden alle Karten
    geprueft, dann wird geschrieben. Eine halb angelegte Lieferung waere
    schlimmer als keine.

    Die neue Position ist max(position) + 1 und ausdruecklich NICHT die
    Anzahl der Karten (Entscheidung E-5). Nach dem Loeschen einer mittleren
    Karte gibt es Luecken; "anzahl" traefe dann eine bereits vergebene
    Position und liefe in uq_karten_bundle_position.

    Returns:
        Das Lernpaket und die neu angelegten Karten in der Reihenfolge der
        Uebergabe.

    Raises:
        MCPFehler: Wenn es das Lernpaket nicht gibt oder eine Karte nicht
            durch die Pruefung kommt.
    """
    if not karten:
        raise MCPFehler(
            "Es wurden keine Karten übergeben. Bitte gib mindestens eine "
            "Karte an."
        )
    bundle = await bundle_holen(sitzung, slug)
    geprueft = [karte_pruefen(eine, nummer) for nummer, eine in enumerate(karten, start=1)]

    hoechste = await sitzung.scalar(
        select(func.max(Karte.position)).where(Karte.bundle_id == bundle.id)
    )
    naechste = 0 if hoechste is None else hoechste + 1

    neue = [
        Karte(bundle_id=bundle.id, position=naechste + abstand, **werte)
        for abstand, werte in enumerate(geprueft)
    ]
    sitzung.add_all(neue)
    await sitzung.flush()
    # Die Sammlung bundle.karten wurde beim Laden gefuellt und kennt die
    # neuen Karten nicht. expire() zwingt den naechsten Zugriff, sie neu zu
    # laden - sonst zeigte bundle_anzeigen im selben Ablauf einen veralteten
    # Stand.
    sitzung.expire(bundle, ["karten"])
    return bundle, neue


def _als_eingabe(karte: Karte, aenderung: KarteAenderung) -> KarteEingabe:
    """Legt die Aenderung ueber die bestehende Karte.

    Was nicht angegeben ist, bleibt, wie es war. Das Ergebnis geht durch
    dasselbe karte_pruefen() wie eine neue Karte - es gibt keine zweite,
    schwaechere Pruefung fuer den Aenderungsweg.

    Die richtige Antwort wird dabei als TEXT uebernommen, nicht als Index:
    Wandert die Antwortliste, muss der Text darin wiedergefunden werden.
    Genau das ist die Stelle, an der eine Zuordnung sonst still verrutscht.
    """
    alte_antworten = list(karte.antworten or [])
    alte_richtige = (
        alte_antworten[karte.richtige_index]
        if karte.richtige_index is not None and karte.richtige_index < len(alte_antworten)
        else None
    )
    return KarteEingabe(
        # art bleibt, wie sie ist: Eine Flashcard und eine Frage haben
        # verschiedene Pflichtfelder. Wer die Art wechseln will, loescht die
        # Karte und legt eine neue an - so steht es auch im Docstring von
        # KarteAenderung.
        art=karte.art,
        vorderseite=(
            aenderung.vorderseite if aenderung.vorderseite is not None else karte.vorderseite
        ),
        rueckseite=(
            aenderung.rueckseite if aenderung.rueckseite is not None else karte.rueckseite
        ),
        antworten=(
            aenderung.antworten if aenderung.antworten is not None else alte_antworten or None
        ),
        richtige_antwort=(
            aenderung.richtige_antwort
            if aenderung.richtige_antwort is not None
            else alte_richtige
        ),
        erklaerung=(
            aenderung.erklaerung if aenderung.erklaerung is not None else karte.erklaerung
        ),
    )


async def karte_aendern(
    sitzung: AsyncSession, karte_id: str, aenderung: KarteAenderung
) -> tuple[Bundle, Karte]:
    """Aendert einzelne Felder einer Karte.

    Geaendert wird ueber das ORM-Objekt und nicht mit einem
    update()-Statement: geaendert_am traegt onupdate=func.now() und wird
    damit nur vom ORM gesetzt. Ein update() liesse die Spalte stehen.

    Raises:
        MCPFehler: Wenn die ID keine ist, die Karte nicht existiert, gar
            kein Feld angegeben wurde oder die geaenderte Karte die Pruefung
            nicht besteht.
    """
    if not aenderung.model_dump(exclude_none=True):
        raise MCPFehler(
            "Es wurde kein Feld zum Ändern angegeben. Bitte gib an, was sich "
            "ändern soll – zum Beispiel 'vorderseite' oder 'erklaerung'. Mit "
            "bundle_anzeigen siehst du, was aktuell auf der Karte steht."
        )
    karte = await karte_holen(sitzung, karte_id)
    # nummer=1: Die Meldungen aus karte_pruefen stellen "Die Karte auf
    # Position 1" voran. Bei einer einzeln angesprochenen Karte waere jede
    # Nummer irrefuehrend; deshalb wird der Ortszusatz hier ersetzt.
    geprueft = karte_pruefen(_als_eingabe(karte, aenderung), nummer=1)

    for feld, wert in geprueft.items():
        setattr(karte, feld, wert)
    await sitzung.flush()

    bundle = await bundle_holen_nach_id(sitzung, karte.bundle_id)
    return bundle, karte


async def bundle_holen_nach_id(sitzung: AsyncSession, bundle_id) -> Bundle:
    """Das Lernpaket zu einer ID.

    Braucht keine eigene Fehlermeldung: Aufgerufen wird es ausschliesslich
    mit einer bundle_id, die an einer geladenen Karte haengt - das
    Fremdschluesselziel existiert dann zwangslaeufig.
    """
    return await sitzung.get(Bundle, bundle_id)


async def karte_loeschen(sitzung: AsyncSession, karte_id: str) -> tuple[Bundle, int]:
    """Loescht eine Karte und gibt das Lernpaket samt Restzahl zurueck.

    Die Positionen der uebrigen Karten bleiben, wie sie sind (Entscheidung
    E-5). Die Reihenfolge ergibt sich aus der Sortierung nach position;
    Luecken stoeren dabei nicht, und ein Massen-update() entfaellt.

    Raises:
        MCPFehler: Wenn es die Karte nicht gibt oder sie die letzte ihres
            Lernpakets ist.
    """
    karte = await karte_holen(sitzung, karte_id)
    bundle = await bundle_holen_nach_id(sitzung, karte.bundle_id)

    anzahl = await sitzung.scalar(
        select(func.count(Karte.id)).where(Karte.bundle_id == karte.bundle_id)
    )
    if anzahl <= 1:
        raise MCPFehler(
            "Das ist die letzte Karte des Lernpakets, und ein Lernpaket ohne "
            "Karten kann niemand üben. Wenn das Lernpaket weg soll, nimm "
            "bundle_deaktivieren – dann bleibt es erhalten und ist nur nicht "
            "mehr erreichbar."
        )

    await sitzung.delete(karte)
    await sitzung.flush()
    sitzung.expire(bundle, ["karten"])
    return bundle, anzahl - 1


# Der Unterschied zwischen "nicht angegeben" und "geleert": Bei den
# optionalen Textfeldern heisst None "unveraendert" und ein leerer String
# "weg". Ohne diese Trennung liesse sich eine einmal gesetzte Beschreibung
# nie wieder loswerden.
async def bundle_aendern(
    sitzung: AsyncSession,
    slug: str,
    titel: str | None,
    beschreibung: str | None,
    klasse: str | None,
    selbsteinschaetzung: bool | None,
    reihenfolge: str | None,
) -> Bundle:
    """Aendert die Kopfdaten eines Lernpakets.

    Die Adresse bleibt unangetastet - sie ist weitergegeben worden und darf
    sich nicht unter den Lernenden wegbewegen, nur weil der Titel korrigiert
    wird.

    Geaendert wird ueber das ORM-Objekt, nicht mit update(): geaendert_am
    traegt onupdate=func.now() und wird deshalb nur vom ORM gesetzt.

    Raises:
        MCPFehler: Wenn es das Lernpaket nicht gibt, kein Feld angegeben
            wurde oder ein Wert die Pruefung nicht besteht.
    """
    angegeben = {
        "titel": titel,
        "beschreibung": beschreibung,
        "klasse": klasse,
        "selbsteinschaetzung": selbsteinschaetzung,
        "reihenfolge": reihenfolge,
    }
    if all(wert is None for wert in angegeben.values()):
        raise MCPFehler(
            "Es wurde kein Feld zum Ändern angegeben. Bitte gib an, was sich "
            "ändern soll – zum Beispiel 'titel' oder 'klasse'. Mit "
            "bundle_anzeigen siehst du den aktuellen Stand."
        )

    bundle = await bundle_holen(sitzung, slug)

    if titel is not None:
        bundle.titel = titel_pruefen(titel)
    if beschreibung is not None:
        bundle.beschreibung = beschreibung_pruefen(beschreibung)
    if klasse is not None:
        bundle.klasse = klasse_pruefen(klasse)
    if selbsteinschaetzung is not None:
        bundle.selbsteinschaetzung = selbsteinschaetzung
    if reihenfolge is not None:
        bundle.reihenfolge = reihenfolge_pruefen(reihenfolge)

    await sitzung.flush()
    return bundle


async def bundle_umschalten(sitzung: AsyncSession, slug: str, aktiv: bool) -> Bundle:
    """Schaltet ein Lernpaket sichtbar oder unsichtbar.

    Kein endgueltiges Loeschen ueber MCP - so verlangt es die Spec in
    Abschnitt 5 ausdruecklich. Das Lernpaket und alle Karten bleiben
    erhalten; die Lernseite zeigt nur einen freundlichen Hinweis. Ein
    Versehen ist damit ein Handgriff, kein Datenverlust.

    Raises:
        MCPFehler: Wenn es das Lernpaket nicht gibt.
    """
    bundle = await bundle_holen(sitzung, slug)
    bundle.aktiv = aktiv
    await sitzung.flush()
    return bundle
