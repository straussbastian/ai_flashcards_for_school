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
    klasse: Mapped[str | None] = mapped_column(String(60))
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
    art: Mapped[str] = mapped_column(String(12), nullable=False)
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
