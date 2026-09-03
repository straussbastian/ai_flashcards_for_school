"""Die Datenbankarbeit hinter den Werkzeugen.

Kennt kein MCP. Jede Ablehnung verlaesst dieses Modul als MCPFehler mit
deutschem Klartext.
"""

import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.eingaben import KarteAenderung, KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import (
    beschreibung_pruefen,
    karte_pruefen,
    gruppe_pruefen,
    karten_pro_durchlauf_pruefen,
    reihenfolge_pruefen,
    titel_pruefen,
)
from app.models import Bundle, Karte, Sammlung, SammlungPaket
from app.slug import SlugKollision, freien_slug_finden

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
    gruppe: str | None,
    selbsteinschaetzung: bool,
    karten_pro_durchlauf: int | None,
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
        "gruppe": gruppe_pruefen(gruppe),
        "selbsteinschaetzung": selbsteinschaetzung,
        "karten_pro_durchlauf": karten_pro_durchlauf_pruefen(karten_pro_durchlauf),
    }

    # Der Wettlauf um eine Adresse wird nicht mehr hier abgefangen.
    # freien_slug_finden() traegt die Adresse gleich in adressen ein und
    # wuerfelt selbst weiter, wenn ein anderer Aufruf schneller war - Pruefen
    # und Belegen sind dort ein Schritt. Frueher stand hier eine eigene
    # Wiederholschleife mit SAVEPOINT, weil zwischen "ist frei" und "ist
    # eingetragen" eine Luecke lag; die gibt es nicht mehr.
    # SlugKollision ist ein RuntimeError und traegt zwar schon deutschen
    # Klartext, ist aber kein MCPFehler - ohne diese Umhuellung saehe die
    # Lehrerin nur "Error executing tool bundle_anlegen". Nachgemessen: Genau
    # das passierte, als die fruehere Wiederholschleife hier wegfiel, und ein
    # Test hat es gefangen.
    try:
        slug = await freien_slug_finden(sitzung, art="paket")
    except SlugKollision as fehler:
        raise MCPFehler(str(fehler)) from fehler
    bundle = Bundle(slug=slug, **felder)
    bundle.karten = [
        Karte(position=stelle, **werte) for stelle, werte in enumerate(geprueft)
    ]
    sitzung.add(bundle)
    await sitzung.flush()
    return bundle


async def bundles_auflisten(
    sitzung: AsyncSession, gruppe: str | None, nur_aktive: bool
) -> list[tuple[Bundle, int]]:
    """Alle Lernpakete mit ihrer Kartenzahl, neueste zuerst."""
    abfrage = (
        select(Bundle, func.count(Karte.id))
        .outerjoin(Karte, Karte.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(Bundle.erstellt_am.desc())
    )
    if gruppe:
        abfrage = abfrage.where(Bundle.gruppe == gruppe.strip())
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


async def karten_einfuegen(
    sitzung: AsyncSession,
    slug: str,
    karten: list[KarteEingabe],
    position: int | None = None,
) -> tuple[Bundle, list[Karte]]:
    """Fuegt Karten an einer Stelle ein - ohne Angabe hinten.

    Alles oder nichts, wie bei bundle_anlegen: Erst werden alle Karten
    geprueft, dann wird geschrieben. Eine halb angelegte Lieferung waere
    schlimmer als keine.

    OHNE position wird angehaengt, und zwar auf max(position) + 1 und
    ausdruecklich NICHT auf die Anzahl der Karten (Entscheidung E-5). Nach
    dem Loeschen einer mittleren Karte gibt es Luecken; "anzahl" traefe dann
    eine bereits vergebene Position und liefe in uq_karten_bundle_position.

    MIT position ruecken die Karten ab dieser Stelle um die Anzahl der neuen
    Karten nach hinten. Das geht nur, weil uq_karten_bundle_position als
    DEFERRABLE INITIALLY DEFERRED angelegt ist: Waehrend des Verschiebens
    gibt es zwangslaeufig kurz doppelte Positionen, geprueft wird erst beim
    Commit. Ein einziges UPDATE statt einer Schleife - dann stellt sich die
    Frage nach der Reihenfolge des Verschiebens gar nicht erst.

    Returns:
        Das Lernpaket und die neu angelegten Karten in der Reihenfolge der
        Uebergabe.

    Raises:
        MCPFehler: Wenn es das Lernpaket nicht gibt, eine Karte nicht durch
            die Pruefung kommt oder position negativ ist.
    """
    if not karten:
        raise MCPFehler(
            "Es wurden keine Karten übergeben. Bitte gib mindestens eine "
            "Karte an."
        )
    if position is not None and position < 0:
        raise MCPFehler(
            f"'position' ist {position} und damit negativ. Die erste Stelle "
            "ist 0. Lass die Angabe weg, wenn die Karten hinten angehängt "
            "werden sollen."
        )
    bundle = await bundle_holen(sitzung, slug)
    geprueft = [karte_pruefen(eine, nummer) for nummer, eine in enumerate(karten, start=1)]

    hoechste = await sitzung.scalar(
        select(func.max(Karte.position)).where(Karte.bundle_id == bundle.id)
    )
    naechste = 0 if hoechste is None else hoechste + 1

    if position is None or position >= naechste:
        # Ans Ende - auch bei einer Position hinter der letzten Karte. Das
        # ist kein Fehler, sondern die naheliegende Auslegung von "dahinter".
        beginn = naechste
    else:
        beginn = position
        # Platz schaffen. Ein UPDATE fuer alle betroffenen Karten; die
        # Eindeutigkeit wird erst beim Commit geprueft (siehe Docstring).
        await sitzung.execute(
            update(Karte)
            .where(Karte.bundle_id == bundle.id, Karte.position >= beginn)
            .values(position=Karte.position + len(geprueft))
        )

    neue = [
        Karte(bundle_id=bundle.id, position=beginn + abstand, **werte)
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
    gruppe: str | None,
    selbsteinschaetzung: bool | None,
    reihenfolge: str | None,
    karten_pro_durchlauf: int | None,
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
        "gruppe": gruppe,
        "selbsteinschaetzung": selbsteinschaetzung,
        "reihenfolge": reihenfolge,
        "karten_pro_durchlauf": karten_pro_durchlauf,
    }
    if all(wert is None for wert in angegeben.values()):
        raise MCPFehler(
            "Es wurde kein Feld zum Ändern angegeben. Bitte gib an, was sich "
            "ändern soll – zum Beispiel 'titel' oder 'gruppe'. Mit "
            "bundle_anzeigen siehst du den aktuellen Stand."
        )

    bundle = await bundle_holen(sitzung, slug)

    if titel is not None:
        bundle.titel = titel_pruefen(titel)
    if beschreibung is not None:
        bundle.beschreibung = beschreibung_pruefen(beschreibung)
    if gruppe is not None:
        bundle.gruppe = gruppe_pruefen(gruppe)
    if selbsteinschaetzung is not None:
        bundle.selbsteinschaetzung = selbsteinschaetzung
    if reihenfolge is not None:
        bundle.reihenfolge = reihenfolge_pruefen(reihenfolge)
    if karten_pro_durchlauf is not None:
        bundle.karten_pro_durchlauf = karten_pro_durchlauf_pruefen(karten_pro_durchlauf)

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


# ====================== Sammlungen ======================


async def sammlung_holen(sitzung: AsyncSession, slug: str) -> Sammlung:
    """Die Sammlung zu einer Adresse.

    Raises:
        MCPFehler: Wenn es keine gibt.
    """
    eintrag = await sitzung.scalar(select(Sammlung).where(Sammlung.slug == slug))
    if eintrag is None:
        raise MCPFehler(
            f"Eine Sammlung mit der Adresse „{slug}“ gibt es nicht. Mit "
            "sammlung_liste siehst du alle vorhandenen."
        )
    return eintrag


async def _pakete_zuordnen(
    sitzung: AsyncSession, sammlung: Sammlung, slugs: list[str]
) -> list[Bundle]:
    """Ersetzt die Paketliste einer Sammlung vollstaendig.

    Ein Werkzeug statt dreier (hinzufuegen/entfernen/verschieben): Der Agent
    liest mit sammlung_anzeigen, ordnet und schreibt zurueck. Das haelt die
    Werkzeugliste kurz - und jedes zusaetzliche Werkzeug ist eines, bei dem
    danebengegriffen werden kann.

    Eine leere Liste ist erlaubt und leert die Sammlung.

    Raises:
        MCPFehler: Bei einer unbekannten Adresse oder einer Dopplung.
    """
    beschnitten = [eintrag.strip() for eintrag in slugs]

    doppelt = sorted({s for s in beschnitten if beschnitten.count(s) > 1})
    if doppelt:
        raise MCPFehler(
            f"Diese Lernpakete stehen mehrfach in der Liste: {', '.join(doppelt)}. "
            "Ein Lernpaket kann in einer Sammlung nur an einer Stelle stehen."
        )

    gefunden: list[Bundle] = []
    for adresse in beschnitten:
        paket = await sitzung.scalar(select(Bundle).where(Bundle.slug == adresse))
        if paket is None:
            raise MCPFehler(
                f"Ein Lernpaket mit der Adresse „{adresse}“ gibt es nicht. Mit "
                "bundle_liste siehst du alle vorhandenen."
            )
        gefunden.append(paket)

    # Erst alles weg, dann neu setzen. Das Constraint auf (sammlung_id,
    # position) ist DEFERRABLE, doppelte Positionen zwischendurch sind also
    # unbedenklich - geprueft wird beim Commit.
    await sitzung.execute(
        delete(SammlungPaket).where(SammlungPaket.sammlung_id == sammlung.id)
    )
    for stelle, paket in enumerate(gefunden):
        sitzung.add(
            SammlungPaket(sammlung_id=sammlung.id, bundle_id=paket.id, position=stelle)
        )
    await sitzung.flush()
    sitzung.expire(sammlung, ["zuordnungen"])
    return gefunden


async def sammlung_anlegen(
    sitzung: AsyncSession,
    titel: str,
    beschreibung: str | None,
    gruppe: str | None,
    pakete: list[str] | None,
) -> Sammlung:
    """Legt eine Sammlung an, optional gleich mit ihren Lernpaketen."""
    try:
        slug = await freien_slug_finden(sitzung, art="sammlung")
    except SlugKollision as fehler:
        raise MCPFehler(str(fehler)) from fehler

    sammlung = Sammlung(
        slug=slug,
        titel=titel_pruefen(titel),
        beschreibung=beschreibung_pruefen(beschreibung),
        gruppe=gruppe_pruefen(gruppe),
    )
    sitzung.add(sammlung)
    await sitzung.flush()

    if pakete:
        await _pakete_zuordnen(sitzung, sammlung, pakete)
    return sammlung


async def sammlungen_auflisten(
    sitzung: AsyncSession, gruppe: str | None, nur_aktive: bool
) -> list[tuple[Sammlung, int]]:
    """Alle Sammlungen mit ihrer Paketzahl, neueste zuerst."""
    abfrage = (
        select(Sammlung, func.count(SammlungPaket.bundle_id))
        .outerjoin(SammlungPaket, SammlungPaket.sammlung_id == Sammlung.id)
        .group_by(Sammlung.id)
        .order_by(Sammlung.erstellt_am.desc())
    )
    if gruppe:
        abfrage = abfrage.where(Sammlung.gruppe == gruppe.strip())
    if nur_aktive:
        abfrage = abfrage.where(Sammlung.aktiv.is_(True))
    return [(eine, anzahl) for eine, anzahl in (await sitzung.execute(abfrage)).all()]


async def sammlung_pakete(sitzung: AsyncSession, sammlung: Sammlung) -> list[Bundle]:
    """Die Lernpakete einer Sammlung in ihrer Reihenfolge.

    Deaktivierte Lernpakete bleiben draussen - eine Sammlung soll nichts
    anbieten, was hinter dem Link ohnehin nicht mehr da ist.
    """
    zeilen = await sitzung.scalars(
        select(Bundle)
        .join(SammlungPaket, SammlungPaket.bundle_id == Bundle.id)
        .where(SammlungPaket.sammlung_id == sammlung.id, Bundle.aktiv.is_(True))
        .order_by(SammlungPaket.position)
    )
    return list(zeilen)


async def sammlung_aendern(
    sitzung: AsyncSession,
    slug: str,
    titel: str | None,
    beschreibung: str | None,
    gruppe: str | None,
) -> Sammlung:
    """Aendert die Kopfdaten einer Sammlung. Die Adresse bleibt unangetastet."""
    angegeben = {"titel": titel, "beschreibung": beschreibung, "gruppe": gruppe}
    if all(wert is None for wert in angegeben.values()):
        raise MCPFehler(
            "Es wurde kein Feld zum Ändern angegeben. Bitte gib an, was sich "
            "ändern soll – zum Beispiel 'titel' oder 'gruppe'. Mit "
            "sammlung_anzeigen siehst du den aktuellen Stand."
        )
    sammlung = await sammlung_holen(sitzung, slug)
    if titel is not None:
        sammlung.titel = titel_pruefen(titel)
    if beschreibung is not None:
        sammlung.beschreibung = beschreibung_pruefen(beschreibung)
    if gruppe is not None:
        sammlung.gruppe = gruppe_pruefen(gruppe)
    await sitzung.flush()
    return sammlung


async def sammlung_pakete_setzen(
    sitzung: AsyncSession, slug: str, pakete: list[str]
) -> tuple[Sammlung, list[Bundle]]:
    """Ersetzt die Paketliste einer Sammlung durch die uebergebene."""
    sammlung = await sammlung_holen(sitzung, slug)
    gefunden = await _pakete_zuordnen(sitzung, sammlung, pakete)
    return sammlung, gefunden


async def sammlung_umschalten(
    sitzung: AsyncSession, slug: str, aktiv: bool
) -> Sammlung:
    """Schaltet eine Sammlung sichtbar oder unsichtbar."""
    sammlung = await sammlung_holen(sitzung, slug)
    sammlung.aktiv = aktiv
    await sitzung.flush()
    return sammlung
