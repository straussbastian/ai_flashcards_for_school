"""Grundmodell: bundles und karten

Revision ID: ccc906f048c0
Revises:
Create Date: 2026-08-27 16:20:28.026137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'ccc906f048c0'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('bundles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('titel', sa.Text(), nullable=False),
    sa.Column('beschreibung', sa.Text(), nullable=True),
    sa.Column('klasse', sa.String(length=60), nullable=True),
    sa.Column('selbsteinschaetzung', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('reihenfolge', sa.String(length=20), server_default='zufall', nullable=False),
    sa.Column('aktiv', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('geaendert_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reihenfolge IN ('zufall', 'fest')", name='ck_bundles_reihenfolge'),
    # NOT NULL allein liesse einen Leerstring oder reine Leerzeichen durch.
    sa.CheckConstraint("length(btrim(titel)) > 0", name='ck_bundles_titel_nicht_leer'),
    sa.CheckConstraint("length(btrim(slug)) > 0", name='ck_bundles_slug_nicht_leer'),
    sa.PrimaryKeyConstraint('id'),
    # Expliziter Name statt des von PostgreSQL selbst vergebenen
    # "bundles_slug_key", damit ein spaeteres DROP CONSTRAINT oder
    # SET CONSTRAINTS nicht raten muss - wie alle anderen Constraints hier.
    sa.UniqueConstraint('slug', name='uq_bundles_slug')
    )
    op.create_table('karten',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('bundle_id', sa.UUID(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('art', sa.String(length=12), nullable=False),
    sa.Column('vorderseite', sa.Text(), nullable=False),
    sa.Column('rueckseite', sa.Text(), nullable=True),
    sa.Column('antworten', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('richtige_index', sa.Integer(), nullable=True),
    sa.Column('erklaerung', sa.Text(), nullable=True),
    sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('geaendert_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("art IN ('flashcard', 'frage')", name='ck_karten_art'),
    sa.CheckConstraint("position >= 0", name='ck_karten_position_nicht_negativ'),
    # NOT NULL allein liesse einen Leerstring oder reine Leerzeichen durch.
    sa.CheckConstraint("length(btrim(vorderseite)) > 0", name='ck_karten_vorderseite_nicht_leer'),
    # rueckseite ist bei einer Frage NULL (erlaubt) und bei einer Flashcard
    # Pflicht (siehe ck_karten_felder_passen_zur_art). "IS NULL OR ..."
    # deckt beide Faelle ab.
    sa.CheckConstraint("rueckseite IS NULL OR length(btrim(rueckseite)) > 0", name='ck_karten_rueckseite_nicht_leer'),
    sa.CheckConstraint("\n            (art = 'flashcard'\n                AND rueckseite IS NOT NULL\n                AND antworten IS NULL\n                AND richtige_index IS NULL\n                AND erklaerung IS NULL)\n            OR\n            (art = 'frage'\n                AND rueckseite IS NULL\n                AND antworten IS NOT NULL\n                AND richtige_index IS NOT NULL)\n            ", name='ck_karten_felder_passen_zur_art'),
    # CASE WHEN statt "art <> 'frage' OR (...)": PostgreSQL garantiert bei
    # AND/OR ausdruecklich keine Auswertungsreihenfolge und kein
    # Short-Circuit-Verhalten. Ist antworten bei art='frage' z.B. ein
    # JSONB-Objekt statt eines Arrays, wirft jsonb_array_length() den
    # PostgreSQL-Fehler 22023, den psycopg als DataError abbildet - nicht
    # als IntegrityError, was den Fehlerklassen-Vertrag der Anwendung
    # bricht. CASE WHEN ist als sequenziell auswertend dokumentiert:
    # jsonb_array_length() wird nur erreicht, wenn jsonb_typeof(antworten)
    # zuvor bereits als 'array' bestaetigt wurde.
    sa.CheckConstraint("\n            CASE\n                WHEN art <> 'frage' THEN true\n                WHEN jsonb_typeof(antworten) = 'array'\n                    THEN jsonb_array_length(antworten) BETWEEN 2 AND 4\n                ELSE false\n            END\n            ", name='ck_karten_antwortanzahl'),
    sa.CheckConstraint("\n            CASE\n                WHEN art <> 'frage' THEN true\n                WHEN jsonb_typeof(antworten) = 'array'\n                    THEN richtige_index >= 0\n                        AND richtige_index < jsonb_array_length(antworten)\n                ELSE false\n            END\n            ", name='ck_karten_richtige_index_im_bereich'),
    sa.ForeignKeyConstraint(['bundle_id'], ['bundles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('bundle_id', 'position', deferrable=True, initially='DEFERRED', name='uq_karten_bundle_position')
    )
    op.create_index(op.f('ix_karten_bundle_id'), 'karten', ['bundle_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_karten_bundle_id'), table_name='karten')
    op.drop_table('karten')
    op.drop_table('bundles')
