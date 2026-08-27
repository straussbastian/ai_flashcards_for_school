import pytest
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError

from app.markdown import MAX_LAENGE
from app.models import Bundle, Karte


def _constraint_name(exc_info: pytest.ExceptionInfo) -> str | None:
    """Liest den Namen des verletzten Constraints aus der Originalausnahme.

    exc_info.value ist die von SQLAlchemy geworfene IntegrityError; .orig
    ist die zugrundeliegende psycopg-Ausnahme, deren .diag (Diagnostics)
    bei einer Constraint-Verletzung den Namen des betroffenen Constraints
    traegt. Ohne diese Pruefung wuerde ein Test schon gruen, wenn
    irgendein IntegrityError auftritt - auch wenn ein spaeterer Umbau den
    eigentlich gemeinten Constraint entfernt und stattdessen versehentlich
    ein anderer (z.B. eine simple NOT-NULL-Spalte) den Fehler ausloest.
    """
    return exc_info.value.orig.diag.constraint_name


async def _bundle(session) -> Bundle:
    bundle = Bundle(slug="rote-katze-springt", titel="Hauptstaedte Europas")
    session.add(bundle)
    await session.flush()
    return bundle


async def test_gueltige_flashcard_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Hauptstadt von Kroatien?",
            rueckseite="Zagreb",
        )
    )
    await session.flush()


async def test_gueltige_frage_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Hauptstadt von Kroatien?",
            antworten=["Split", "Zagreb", "Rijeka"],
            richtige_index=1,
            erklaerung="Zagreb liegt im Landesinneren.",
        )
    )
    await session.flush()


async def test_flashcard_ohne_rueckseite_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(bundle_id=bundle.id, position=1, art="flashcard", vorderseite="Frage")
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_felder_passen_zur_art"


async def test_frage_mit_index_ausserhalb_der_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=5,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_richtige_index_im_bereich"


async def test_negativer_richtiger_index_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=-1,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_richtige_index_im_bereich"


async def test_frage_mit_fuenf_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["a", "b", "c", "d", "e"],
            richtige_index=0,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_antwortanzahl"


async def test_frage_mit_einer_antwort_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["a"],
            richtige_index=0,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_antwortanzahl"


async def test_frage_mit_jsonb_objekt_statt_liste_als_antworten_wird_abgelehnt(session):
    """Regressionstest: antworten als JSONB-Objekt statt Array.

    jsonb_array_length() wirft fuer ein JSONB-Objekt den PostgreSQL-Fehler
    22023 ("cannot get array length of a non-array"), den psycopg als
    DataError abbildet - nicht als IntegrityError. Die CASE-WHEN-Form der
    Constraints ck_karten_antwortanzahl/ck_karten_richtige_index_im_bereich
    in app/models.py muss das abfangen: jsonb_array_length() darf nur
    aufgerufen werden, nachdem jsonb_typeof(antworten) = 'array' bereits
    bestaetigt ist. Dieser Test bestaetigt IntegrityError, nicht
    irgendeinen Fehler.

    Insert bewusst ueber SQLAlchemy Core (insert(Karte.__table__)) statt
    ueber Karte(...): MutableList.as_mutable(JSONB) (siehe app/models.py)
    lehnt ein dict beim Zuweisen an das ORM-Attribut bereits in Python ab
    (ValueError), bevor ueberhaupt eine Anfrage die Datenbank erreicht. Das
    ist eine sinnvolle zusaetzliche Absicherung auf Anwendungsseite, ersetzt
    aber nicht die Pflicht der Datenbank, sich selbst gegen jeden Weg zu
    schuetzen, auf dem Daten hineingelangen koennen (z.B. Rohzugriffe, Bulk-
    Operationen, andere Programme) - genau das dieser Test ueberprueft,
    indem er die ORM-Attributpruefung gezielt umgeht.
    """
    bundle = await _bundle(session)
    with pytest.raises(IntegrityError) as exc_info:
        await session.execute(
            insert(Karte.__table__).values(
                bundle_id=bundle.id,
                position=1,
                art="frage",
                vorderseite="Frage",
                antworten={"a": 1, "b": 2},
                richtige_index=0,
            )
        )
    assert _constraint_name(exc_info) == "ck_karten_antwortanzahl"


async def test_flashcard_mit_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Frage",
            rueckseite="Antwort",
            antworten=["a", "b"],
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_felder_passen_zur_art"


async def test_unbekannte_art_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="quiz",
            vorderseite="Frage",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_art"


async def test_karte_mit_negativer_position_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=-1,
            art="flashcard",
            vorderseite="Frage",
            rueckseite="Antwort",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_position_nicht_negativ"


@pytest.mark.parametrize("leerer_wert", ["", "   "], ids=["leerstring", "nur_leerzeichen"])
async def test_karte_mit_leerer_vorderseite_wird_abgelehnt(session, leerer_wert):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite=leerer_wert,
            rueckseite="Antwort",
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_vorderseite_nicht_leer"


@pytest.mark.parametrize("leerer_wert", ["", "   "], ids=["leerstring", "nur_leerzeichen"])
async def test_flashcard_mit_leerer_rueckseite_wird_abgelehnt(session, leerer_wert):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Frage",
            rueckseite=leerer_wert,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_rueckseite_nicht_leer"


@pytest.mark.parametrize("leerer_wert", ["", "   "], ids=["leerstring", "nur_leerzeichen"])
async def test_bundle_mit_leerem_titel_wird_abgelehnt(session, leerer_wert):
    session.add(Bundle(slug="gruene-eule-liest", titel=leerer_wert))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_titel_nicht_leer"


@pytest.mark.parametrize("leerer_wert", ["", "   "], ids=["leerstring", "nur_leerzeichen"])
async def test_bundle_mit_leerem_slug_wird_abgelehnt(session, leerer_wert):
    session.add(Bundle(slug=leerer_wert, titel="Test"))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_slug_nicht_leer"


async def test_doppelte_position_im_selben_bundle_wird_abgelehnt(session):
    bundle = await _bundle(session)
    for _ in range(2):
        session.add(
            Karte(
                bundle_id=bundle.id,
                position=1,
                art="flashcard",
                vorderseite="Frage",
                rueckseite="Antwort",
            )
        )
    # Der Unique-Constraint ist DEFERRABLE INITIALLY DEFERRED (siehe
    # app/models.py), damit spaeteres Umsortieren von Karten funktioniert,
    # ohne dass eine Zwischenstufe mit vertauschten Positionen scheitert.
    # PostgreSQL prueft ihn deshalb erst beim COMMIT, nicht bei flush().
    # Ohne die folgende Zeile wuerde flush() nie einen Fehler werfen und
    # dieser Test waere gruen, ohne irgendetwas zu pruefen.
    await session.execute(text("SET CONSTRAINTS uq_karten_bundle_position IMMEDIATE"))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "uq_karten_bundle_position"


async def test_unbekannte_reihenfolge_wird_abgelehnt(session):
    session.add(Bundle(slug="blaue-ampel-tanzt", titel="Test", reihenfolge="rueckwaerts"))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_reihenfolge"


async def test_antwort_an_bestehende_frage_anhaengen_wird_uebernommen(session):
    """Regressionstest fuer MutableList: In-Place-Aenderungen an "antworten"
    muessen SQLAlchemy als Aenderung erkennen und beim naechsten flush()
    tatsaechlich speichern - nicht nur eine komplette Neuzuweisung.
    """
    bundle = await _bundle(session)
    karte = Karte(
        bundle_id=bundle.id,
        position=1,
        art="frage",
        vorderseite="Frage",
        antworten=["a", "b"],
        richtige_index=0,
    )
    session.add(karte)
    await session.flush()

    karte.antworten.append("c")
    await session.flush()
    await session.refresh(karte)

    assert karte.antworten == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Laengengrenzen
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spalte, constraint",
    [
        ("vorderseite", "ck_karten_vorderseite_max_laenge"),
        ("rueckseite", "ck_karten_rueckseite_max_laenge"),
    ],
)
async def test_markdown_grenze_und_datenbankgrenze_passen_zusammen(
    session, spalte, constraint
):
    """Haelt MAX_LAENGE aus app/markdown.py und die Grenze in der Datenbank zusammen.

    app/markdown.rendern() wirft MarkdownZuLang oberhalb von MAX_LAENGE, und
    gerendert wird erst beim Ausliefern der Lernseite. Waere die Grenze der
    Datenbank groesser, liesse sich eine Karte speichern, die danach die
    ganze Lernseite fuer alle Lernenden dieses Bundles kippt - nicht nur die
    eine Karte. Waere sie kleiner, lehnte die Datenbank Texte ab, die die
    Anwendung problemlos rendert.

    Die Zahl steht bewusst dreimal ausgeschrieben (app/markdown.py,
    app/models.py, migrations/versions/0001_grundmodell.py), weil eine
    Migration nicht davon abhaengen darf, was gerade im Anwendungscode steht.
    Dieser Test ist der Preis dafuer und die Absicherung dagegen: Genau
    MAX_LAENGE Zeichen muessen speicherbar sein, ein Zeichen mehr nicht.
    Laufen die Zahlen kuenftig auseinander, wird er rot.
    """
    bundle = await _bundle(session)
    felder = {
        "bundle_id": bundle.id,
        "art": "flashcard",
        "vorderseite": "Frage",
        "rueckseite": "Antwort",
    }

    # Genau MAX_LAENGE Zeichen: muss durchgehen.
    session.add(Karte(**{**felder, "position": 1, spalte: "a" * MAX_LAENGE}))
    await session.flush()

    # Ein Zeichen mehr: muss an genau diesem Constraint scheitern.
    session.add(Karte(**{**felder, "position": 2, spalte: "a" * (MAX_LAENGE + 1)}))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == constraint


async def test_zu_lange_erklaerung_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=0,
            erklaerung="a" * (MAX_LAENGE + 1),
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_erklaerung_max_laenge"


async def test_zu_lange_beschreibung_wird_abgelehnt(session):
    session.add(
        Bundle(
            slug="gelbe-lampe-summt",
            titel="Test",
            beschreibung="a" * (MAX_LAENGE + 1),
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_beschreibung_max_laenge"


async def test_zu_langer_titel_wird_abgelehnt(session):
    session.add(Bundle(slug="graue-maus-pfeift", titel="a" * 201))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_titel_max_laenge"


async def test_zu_lange_klasse_wird_abgelehnt(session):
    session.add(Bundle(slug="weisse-taube-fliegt", titel="Test", klasse="a" * 61))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_bundles_klasse_max_laenge"


# ---------------------------------------------------------------------------
# antworten ist eine Textliste, nicht irgendein Array
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "antworten",
    [
        pytest.param([1, 2, 3], id="zahlen"),
        pytest.param([None, None], id="null"),
        pytest.param([{"a": 1}, {"b": 2}], id="objekte"),
        pytest.param(["Zagreb", 42], id="gemischt_text_und_zahl"),
    ],
)
async def test_antworten_die_keine_texte_sind_werden_abgelehnt(session, antworten):
    """Die Spec nennt in Abschnitt 4 eine Textliste, nicht irgendein Array.

    Vorher prueften die Constraints nur jsonb_typeof(...) = 'array' und die
    Anzahl; [1, 2, 3], [null, null] und [{"a":1},{"b":2}] gingen durch. Plan 2
    sucht den Text der richtigen Antwort in dieser Liste, um richtige_index zu
    bestimmen - auf Nicht-Strings bricht das ab oder liefert stillschweigend
    Unsinn.

    Der Insert laeuft bewusst ueber SQLAlchemy Core (insert(Karte.__table__))
    statt ueber Karte(...): Nur so ist belegt, dass die Ablehnung wirklich
    von der DATENBANK kommt und nicht schon vorher in Python passiert. Ein
    IntegrityError mit dem Constraint-Namen aus psycopgs Diagnostics kann
    ausschliesslich der Server geworfen haben.
    """
    bundle = await _bundle(session)
    with pytest.raises(IntegrityError) as exc_info:
        await session.execute(
            insert(Karte.__table__).values(
                bundle_id=bundle.id,
                position=1,
                art="frage",
                vorderseite="Frage",
                antworten=antworten,
                richtige_index=0,
            )
        )
    assert _constraint_name(exc_info) == "ck_karten_antworten_sind_texte"


@pytest.mark.parametrize(
    "antworten",
    [
        pytest.param(["Zagreb", ""], id="leerstring"),
        pytest.param(["Zagreb", "   "], id="nur_leerzeichen"),
    ],
)
async def test_leere_antworttexte_werden_abgelehnt(session, antworten):
    """Eine Antwortmoeglichkeit ohne sichtbaren Text ist auf der Karte ein leerer Knopf.

    Auch hier ueber Core statt ueber das ORM, damit die Ablehnung
    nachweislich aus der Datenbank kommt.
    """
    bundle = await _bundle(session)
    with pytest.raises(IntegrityError) as exc_info:
        await session.execute(
            insert(Karte.__table__).values(
                bundle_id=bundle.id,
                position=1,
                art="frage",
                vorderseite="Frage",
                antworten=antworten,
                richtige_index=0,
            )
        )
    assert _constraint_name(exc_info) == "ck_karten_antworten_nicht_leer"


@pytest.mark.parametrize("leerer_wert", ["", "   "], ids=["leerstring", "nur_leerzeichen"])
async def test_frage_mit_leerer_erklaerung_wird_abgelehnt(session, leerer_wert):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=0,
            erklaerung=leerer_wert,
        )
    )
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "ck_karten_erklaerung_nicht_leer"


async def test_doppelter_slug_wird_abgelehnt(session):
    """Die Eindeutigkeit der Adresse, auf der die gesamte Slug-Logik ruht.

    app/slug.py erzeugt Drei-Wort-Adressen und behandelt Kollisionen, indem
    es bei einem Treffer neu wuerfelt. Dieses Verfahren hat nur dann einen
    Sinn, wenn die Datenbank einen doppelten Slug tatsaechlich zurueckweist -
    sonst kaeme eine Kollision unter Last still durch und zwei Lernseiten
    laegen unter derselben Adresse.
    """
    session.add(Bundle(slug="rote-katze-springt", titel="Erstes Bundle"))
    await session.flush()
    session.add(Bundle(slug="rote-katze-springt", titel="Zweites Bundle"))
    with pytest.raises(IntegrityError) as exc_info:
        await session.flush()
    assert _constraint_name(exc_info) == "uq_bundles_slug"
