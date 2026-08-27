import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# --- Laengengrenzen ---------------------------------------------------------
# MUSS mit MAX_LAENGE in app/markdown.py uebereinstimmen. Der Wert steht hier
# absichtlich ausgeschrieben statt importiert: Die Migration
# migrations/versions/0001_grundmodell.py traegt dieselbe Zahl und darf nicht
# davon abhaengen, was gerade im Anwendungscode steht - eine eingespielte
# Migration beschreibt den Zustand der Datenbank von damals, nicht den von
# heute. Damit die drei Zahlen nicht auseinanderlaufen, haelt
# tests/test_models.py::test_markdown_grenze_und_datenbankgrenze_passen_zusammen
# sie gegeneinander: Genau MAX_LAENGE Zeichen muessen speicherbar sein, ein
# Zeichen mehr nicht.
#
# Der Grund fuer die Grenze: app/markdown.rendern() wirft MarkdownZuLang,
# sobald ein Text MAX_LAENGE ueberschreitet. Gerendert wird erst beim
# Ausliefern der Lernseite. Eine zu lange Karte in der Datenbank macht deshalb
# nicht nur sich selbst kaputt, sondern die ganze Seite fuer alle Lernenden
# dieses Bundles. Was nicht ausgeliefert werden kann, darf gar nicht erst
# hineinkommen.
MAX_MARKDOWN_LAENGE = 5000

# Der Titel steht als einzeilige Ueberschrift auf der Startseite des Bundles
# (siehe docs/design/prototyp.html) und ist kein Markdown. 200 Zeichen sind
# fuer eine Ueberschrift grosszuegig und bleiben trotzdem deutlich unterhalb
# dessen, was das Layout noch traegt.
MAX_TITEL_LAENGE = 200

# "FS 23b" laut Spec, Abschnitt 4. 60 Zeichen fassen auch eine ausgeschriebene
# Klassenbezeichnung wie "Fachinformatiker Systemintegration 23b" bequem.
MAX_KLASSE_LAENGE = 60

# --- Warum CHECK und nicht VARCHAR(n) ---------------------------------------
# Die Laengengrenzen der Inhaltsspalten stehen als CHECK-Constraint da und
# nicht als VARCHAR(n). Eine ueberlange Eingabe soll denselben Fehlertyp
# ausloesen wie jede andere verletzte Regel dieses Schemas (IntegrityError mit
# lesbarem Constraint-Namen) und nicht ein DataError aus der
# Typkonvertierung - siehe die Begruendung bei "art" und "reihenfolge" unten.
# Nur so kann der MCP-Server aus Plan 2 alle Ablehnungen der Datenbank an
# einer Stelle in verstaendliche Meldungen uebersetzen.
# VARCHAR(n) bleibt den Spalten vorbehalten, die die Anwendung selbst fuellt
# (slug, art, reihenfolge): Deren Inhalte stammen aus einem festen Vorrat, den
# eine Eingabe von aussen nie erreicht.
# length(NULL) ist NULL, und ein CHECK gilt bei NULL als erfuellt - die
# optionalen Spalten brauchen deshalb kein zusaetzliches "IS NULL OR".


class Bundle(Base):
    """Eine Lernseite unter einer Drei-Wort-Adresse."""

    __tablename__ = "bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # unique=True wuerde PostgreSQL den Namen "bundles_slug_key" vergeben
    # lassen - der explizite Name "uq_bundles_slug" in __table_args__ unten
    # sorgt dafuer, dass ein spaeteres DROP CONSTRAINT oder SET CONSTRAINTS
    # nicht raten muss, wie alle anderen Constraints dieses Modells auch.
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    klasse: Mapped[str | None] = mapped_column(Text)
    selbsteinschaetzung: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    # String(20) statt String(10): "rueckwaerts" (11 Zeichen) im Test
    # test_unbekannte_reihenfolge_wird_abgelehnt darf nicht schon an der
    # Spaltenlaenge (StringDataRightTruncation) scheitern, sondern muss am
    # CHECK-Constraint ck_bundles_reihenfolge abgelehnt werden - sonst
    # bekaeme man ein DataError statt des erwarteten IntegrityError.
    reihenfolge: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="zufall"
    )
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    karten: Mapped[list["Karte"]] = relationship(
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="Karte.position",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("slug", name="uq_bundles_slug"),
        CheckConstraint(
            "reihenfolge IN ('zufall', 'fest')", name="ck_bundles_reihenfolge"
        ),
        # NOT NULL allein liesse einen Leerstring oder reine Leerzeichen
        # durch (IS NOT NULL ist damit erfuellt). btrim() entfernt
        # fuehrende/folgende Leerzeichen; length(...) > 0 lehnt damit sowohl
        # "" als auch "   " ab. btrim()/length() werfen fuer keinen
        # Text-Wert einen Fehler (anders als z.B. jsonb_array_length() bei
        # falschem JSONB-Typ, siehe Karte unten) - eine einfache Bedingung
        # genuegt hier, ohne CASE WHEN.
        CheckConstraint(
            "length(btrim(titel)) > 0", name="ck_bundles_titel_nicht_leer"
        ),
        CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_bundles_slug_nicht_leer"
        ),
        # Laengengrenzen, siehe Kommentarblock oben.
        CheckConstraint(
            f"length(titel) <= {MAX_TITEL_LAENGE}",
            name="ck_bundles_titel_max_laenge",
        ),
        # beschreibung ist Markdown und geht durch app/markdown.rendern().
        CheckConstraint(
            f"length(beschreibung) <= {MAX_MARKDOWN_LAENGE}",
            name="ck_bundles_beschreibung_max_laenge",
        ),
        CheckConstraint(
            f"length(klasse) <= {MAX_KLASSE_LAENGE}",
            name="ck_bundles_klasse_max_laenge",
        ),
    )


class Karte(Base):
    """Eine Flashcard oder eine Multiple-Choice-Frage innerhalb eines Bundles."""

    __tablename__ = "karten"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # String(30) statt String(12): Wie bei "reihenfolge" oben darf ein
    # unbekannter Bezeichner nicht schon an der Spaltenlaenge scheitern
    # (StringDataRightTruncation -> DataError), sondern muss am
    # CHECK-Constraint ck_karten_art abgelehnt werden (IntegrityError).
    # String(12) fasste "flashcard" (9) und "frage" (5), aber ein kuenftiger
    # Kartentyp mit laengerem Namen waere in genau diese Falle gelaufen und
    # haette den Fehlerklassen-Vertrag gebrochen, auf dem alle
    # Ablehnungstests beruhen. 30 Zeichen sind fuer einen Bezeichner aus
    # einem festen Vorrat reichlich.
    art: Mapped[str] = mapped_column(String(30), nullable=False)
    vorderseite: Mapped[str] = mapped_column(Text, nullable=False)
    rueckseite: Mapped[str | None] = mapped_column(Text)
    # MutableList.as_mutable(...) statt nur JSONB: Ohne das erkennt
    # SQLAlchemy ein karte.antworten.append(...) nicht als Aenderung am
    # Objekt (JSONB wird sonst nur bei kompletter Neuzuweisung als "dirty"
    # markiert) und speichert die Aenderung stillschweigend nicht. Beim
    # spaeteren Bearbeiten von Fragen waere das ein wartendes Raetsel.
    antworten: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSONB))
    richtige_index: Mapped[int | None] = mapped_column(Integer)
    erklaerung: Mapped[str | None] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    bundle: Mapped[Bundle] = relationship(back_populates="karten")

    __table_args__ = (
        UniqueConstraint(
            "bundle_id",
            "position",
            name="uq_karten_bundle_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("art IN ('flashcard', 'frage')", name="ck_karten_art"),
        CheckConstraint("position >= 0", name="ck_karten_position_nicht_negativ"),
        # Siehe Bundle oben: NOT NULL allein reicht nicht, um einen
        # Leerstring abzulehnen.
        CheckConstraint(
            "length(btrim(vorderseite)) > 0", name="ck_karten_vorderseite_nicht_leer"
        ),
        # rueckseite ist bei einer Frage NULL (erlaubt) und bei einer
        # Flashcard Pflicht (siehe ck_karten_felder_passen_zur_art unten).
        # "IS NULL OR ..." deckt beide Faelle ab, ohne CASE WHEN: btrim()
        # auf NULL liefert NULL, nie einen Fehler, und "OR" mit einem davon
        # unabhaengigen ersten Zweig (kein typwechselnder Funktionsaufruf
        # wie bei den JSONB-Checks) ist hier unproblematisch.
        CheckConstraint(
            "rueckseite IS NULL OR length(btrim(rueckseite)) > 0",
            name="ck_karten_rueckseite_nicht_leer",
        ),
        # erklaerung in derselben Machart: optional, aber wenn gesetzt, dann
        # mit Inhalt. Eine Erklaerung aus lauter Leerzeichen erzeugt auf der
        # Rueckseite einen leeren Absatz, den niemand gewollt hat.
        CheckConstraint(
            "erklaerung IS NULL OR length(btrim(erklaerung)) > 0",
            name="ck_karten_erklaerung_nicht_leer",
        ),
        # Laengengrenzen, siehe Kommentarblock oben. Alle drei Spalten sind
        # Markdown und gehen durch app/markdown.rendern().
        CheckConstraint(
            f"length(vorderseite) <= {MAX_MARKDOWN_LAENGE}",
            name="ck_karten_vorderseite_max_laenge",
        ),
        CheckConstraint(
            f"length(rueckseite) <= {MAX_MARKDOWN_LAENGE}",
            name="ck_karten_rueckseite_max_laenge",
        ),
        CheckConstraint(
            f"length(erklaerung) <= {MAX_MARKDOWN_LAENGE}",
            name="ck_karten_erklaerung_max_laenge",
        ),
        CheckConstraint(
            """
            (art = 'flashcard'
                AND rueckseite IS NOT NULL
                AND antworten IS NULL
                AND richtige_index IS NULL
                AND erklaerung IS NULL)
            OR
            (art = 'frage'
                AND rueckseite IS NULL
                AND antworten IS NOT NULL
                AND richtige_index IS NOT NULL)
            """,
            name="ck_karten_felder_passen_zur_art",
        ),
        # CASE WHEN statt "art <> 'frage' OR (...)": PostgreSQL garantiert
        # bei AND/OR ausdruecklich KEINE Auswertungsreihenfolge und schon
        # gar nicht Short-Circuit-Verhalten - der Planer darf beide Seiten
        # auswerten, in beliebiger Reihenfolge. Ist antworten bei einer
        # Frage z.B. ein JSONB-Objekt statt eines Arrays, wirft
        # jsonb_array_length() den PostgreSQL-Fehler 22023 ("cannot get
        # array length of a non-array"), den psycopg als DataError abbildet
        # - nicht als IntegrityError. Damit wuerde der Fehlerklassen-Vertrag
        # brechen, auf dem alle Ablehnungstests aufbauen. CASE WHEN ist in
        # PostgreSQL dagegen als sequenziell auswertend dokumentiert: Sobald
        # ein WHEN zutrifft, wird nur dessen THEN ausgewertet, alles danach
        # nicht mehr. jsonb_array_length(antworten) wird hier also nur
        # erreicht, wenn jsonb_typeof(antworten) zuvor bereits 'array' war.
        CheckConstraint(
            """
            CASE
                WHEN art <> 'frage' THEN true
                WHEN jsonb_typeof(antworten) = 'array'
                    THEN jsonb_array_length(antworten) BETWEEN 2 AND 4
                ELSE false
            END
            """,
            name="ck_karten_antwortanzahl",
        ),
        # Die Spec nennt in Abschnitt 4 ausdruecklich eine Textliste. Ohne
        # diesen Constraint gingen [1, 2, 3], [null, null] oder
        # [{"a":1},{"b":2}] durch: jsonb_typeof(...) = 'array' und die
        # Anzahl stimmen ja. Plan 2 sucht den Text der richtigen Antwort in
        # dieser Liste, um richtige_index zu bestimmen - auf Nicht-Strings
        # bricht das ab oder liefert stillschweigend Unsinn.
        #
        # Ein CHECK-Constraint darf keine Unterabfrage enthalten, ein
        # "EXISTS (SELECT ... FROM jsonb_array_elements(...))" scheidet also
        # aus. Stattdessen der Vergleich zweier Anzahlen:
        # jsonb_path_query_array() liefert (ohne Unterabfrage und als
        # immutable Funktion in einem CHECK zulaessig) genau die Elemente,
        # auf die der Pfadausdruck passt - hier alle vom Typ String. Sind
        # das genauso viele wie insgesamt, ist jedes Element ein String.
        # Der CASE-WHEN-Rahmen wie oben, aus demselben Grund.
        CheckConstraint(
            """
            CASE
                WHEN art <> 'frage' THEN true
                WHEN jsonb_typeof(antworten) = 'array'
                    THEN jsonb_array_length(antworten) = jsonb_array_length(
                        jsonb_path_query_array(
                            antworten, '$[*] ? (@.type() == "string")'))
                ELSE false
            END
            """,
            name="ck_karten_antworten_sind_texte",
        ),
        # Eine Antwortmoeglichkeit ohne sichtbaren Text ist auf der Karte
        # ein leerer Knopf. Der Pfadausdruck sucht das Gegenteil des
        # Erlaubten - ein Element, das ein String ist und kein einziges
        # Zeichen ausserhalb der Leerzeichen enthaelt - und der Constraint
        # verlangt, dass es kein solches gibt. Die Einschraenkung auf
        # @.type() == "string" ist Absicht: Ein Element vom falschen Typ
        # soll ausschliesslich ck_karten_antworten_sind_texte verletzen,
        # damit der gemeldete Constraint-Name eindeutig sagt, was los ist -
        # PostgreSQL garantiert keine Reihenfolge, in der Constraints
        # geprueft werden.
        CheckConstraint(
            """
            CASE
                WHEN art <> 'frage' THEN true
                WHEN jsonb_typeof(antworten) = 'array'
                    THEN NOT jsonb_path_exists(
                        antworten,
                        '$[*] ? (@.type() == "string"'
                        ' && !(@ like_regex "[^[:space:]]"))')
                ELSE false
            END
            """,
            name="ck_karten_antworten_nicht_leer",
        ),
        CheckConstraint(
            """
            CASE
                WHEN art <> 'frage' THEN true
                WHEN jsonb_typeof(antworten) = 'array'
                    THEN richtige_index >= 0
                        AND richtige_index < jsonb_array_length(antworten)
                ELSE false
            END
            """,
            name="ck_karten_richtige_index_im_bereich",
        ),
    )
