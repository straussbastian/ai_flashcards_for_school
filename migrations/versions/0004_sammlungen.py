"""adressen, sammlungen, sammlung_pakete

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

Drei Tabellen fuer die Sammlungen (siehe
docs/superpowers/specs/2026-09-03-sammlungen-design.md):

  adressen         der gemeinsame Adressraum von Lernpaketen und Sammlungen
  sammlungen       das Buendel selbst
  sammlung_pakete  welches Paket an welcher Stelle in welcher Sammlung

WICHTIG: Diese Migration darf keine einzige bestehende Adresse veraendern.
bundles.slug steht in Links, die Klassen in der Hand haben. Deshalb wird
adressen aus den vorhandenen Slugs BEFUELLT und danach der Fremdschluessel
gesetzt - nichts wird umgeschrieben, nichts neu vergeben.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "adressen",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("art", sa.String(length=20), nullable=False),
        sa.PrimaryKeyConstraint("slug", name="pk_adressen"),
        sa.CheckConstraint("art IN ('paket', 'sammlung')", name="ck_adressen_art"),
    )

    # Erst befuellen, dann verknuepfen. Andersherum scheiterte der
    # Fremdschluessel an jedem bestehenden Lernpaket.
    op.execute("INSERT INTO adressen (slug, art) SELECT slug, 'paket' FROM bundles")

    op.create_foreign_key(
        "fk_bundles_slug_adressen", "bundles", "adressen", ["slug"], ["slug"]
    )

    op.create_table(
        "sammlungen",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("titel", sa.Text(), nullable=False),
        sa.Column("beschreibung", sa.Text(), nullable=True),
        sa.Column("gruppe", sa.Text(), nullable=True),
        sa.Column("aktiv", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("erstellt_am", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("geaendert_am", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_sammlungen"),
        sa.UniqueConstraint("slug", name="uq_sammlungen_slug"),
        sa.ForeignKeyConstraint(["slug"], ["adressen.slug"],
                                name="fk_sammlungen_slug_adressen"),
        sa.CheckConstraint(
            "length(btrim(titel, ' ' || chr(9) || chr(10) || chr(13) || chr(11)"
            " || chr(12) || chr(160))) > 0",
            name="ck_sammlungen_titel_nicht_leer",
        ),
        sa.CheckConstraint("length(titel) <= 200", name="ck_sammlungen_titel_max_laenge"),
        sa.CheckConstraint(
            "beschreibung IS NULL OR length(btrim(beschreibung, ' ' || chr(9)"
            " || chr(10) || chr(13) || chr(11) || chr(12) || chr(160))) > 0",
            name="ck_sammlungen_beschreibung_nicht_leer",
        ),
        sa.CheckConstraint("length(beschreibung) <= 5000",
                           name="ck_sammlungen_beschreibung_max_laenge"),
        sa.CheckConstraint("length(gruppe) <= 60", name="ck_sammlungen_gruppe_max_laenge"),
    )

    op.create_table(
        "sammlung_pakete",
        sa.Column("sammlung_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bundle_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("sammlung_id", "bundle_id", name="pk_sammlung_pakete"),
        sa.ForeignKeyConstraint(["sammlung_id"], ["sammlungen.id"], ondelete="CASCADE",
                                name="fk_sammlung_pakete_sammlung"),
        sa.ForeignKeyConstraint(["bundle_id"], ["bundles.id"], ondelete="CASCADE",
                                name="fk_sammlung_pakete_bundle"),
        sa.CheckConstraint("position >= 0", name="ck_sammlung_pakete_position_positiv"),
    )
    op.create_index("ix_sammlung_pakete_bundle_id", "sammlung_pakete", ["bundle_id"])

    # DEFERRABLE INITIALLY DEFERRED wie bei uq_karten_bundle_position:
    # Umsortieren erzeugt zwangslaeufig kurzzeitig doppelte Positionen.
    # Alembic kennt dafuer keinen eigenen Schalter, deshalb von Hand.
    op.execute(
        "ALTER TABLE sammlung_pakete ADD CONSTRAINT uq_sammlung_pakete_position "
        "UNIQUE (sammlung_id, position) DEFERRABLE INITIALLY DEFERRED"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("sammlung_pakete")
    op.drop_table("sammlungen")
    op.drop_constraint("fk_bundles_slug_adressen", "bundles", type_="foreignkey")
    op.drop_table("adressen")
