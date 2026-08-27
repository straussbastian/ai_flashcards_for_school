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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Bundle(Base):
    """Eine Lernseite unter einer Drei-Wort-Adresse."""

    __tablename__ = "bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
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
        CheckConstraint(
            "reihenfolge IN ('zufall', 'fest')", name="ck_bundles_reihenfolge"
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
    antworten: Mapped[list[str] | None] = mapped_column(JSONB)
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
        CheckConstraint(
            """
            art <> 'frage'
            OR (jsonb_typeof(antworten) = 'array'
                AND jsonb_array_length(antworten) BETWEEN 2 AND 4)
            """,
            name="ck_karten_antwortanzahl",
        ),
        CheckConstraint(
            """
            art <> 'frage'
            OR (richtige_index >= 0
                AND richtige_index < jsonb_array_length(antworten))
            """,
            name="ck_karten_richtige_index_im_bereich",
        ),
    )
