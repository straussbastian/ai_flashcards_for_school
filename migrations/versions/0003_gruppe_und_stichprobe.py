"""gruppe statt klasse, karten_pro_durchlauf

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-29

Zwei Aenderungen an bundles:

1. klasse -> gruppe. Eine reine Umbenennung; das Feld trug laengst Faecher
   ("Englisch") neben Klassen ("WBA3"), und der alte Name engte ein.

2. karten_pro_durchlauf: Wie viele Karten ein Durchlauf abfragt. NULL heisst
   "alle" und ist die Vorgabe - das bisherige Verhalten bleibt damit
   unveraendert.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Der Ausdruck des CHECK-Constraints (length(klasse) <= 60) wandert
    # automatisch mit: PostgreSQL speichert ihn mit einem Verweis auf die
    # Spalte, nicht als Text. Nur der NAME des Constraints bleibt sonst
    # stehen und muesste spaeter jemand raten lassen, wozu er gehoert.
    op.alter_column("bundles", "klasse", new_column_name="gruppe")
    op.execute(
        "ALTER TABLE bundles RENAME CONSTRAINT "
        "ck_bundles_klasse_max_laenge TO ck_bundles_gruppe_max_laenge"
    )

    op.add_column(
        "bundles",
        sa.Column("karten_pro_durchlauf", sa.Integer(), nullable=True),
    )
    # Keine Obergrenze, und ausdruecklich keine Pruefung gegen die Kartenzahl:
    # Ein Wert groesser als das Paket bedeutet "alle" und ist kein Fehler.
    # Eine Pruefung gegen die Kartenzahl waere ohnehin nicht haltbar - Karten
    # kommen und gehen, der Wert am Paket bleibt.
    #
    # Die Null bleibt frei: Sie ist als gespeicherter Wert abgelehnt und
    # traegt deshalb ueber MCP die Bedeutung "auf alle zuruecksetzen".
    op.create_check_constraint(
        "ck_bundles_karten_pro_durchlauf_positiv",
        "bundles",
        "karten_pro_durchlauf IS NULL OR karten_pro_durchlauf > 0",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("ck_bundles_karten_pro_durchlauf_positiv", "bundles")
    op.drop_column("bundles", "karten_pro_durchlauf")
    op.execute(
        "ALTER TABLE bundles RENAME CONSTRAINT "
        "ck_bundles_gruppe_max_laenge TO ck_bundles_klasse_max_laenge"
    )
    op.alter_column("bundles", "gruppe", new_column_name="klasse")
