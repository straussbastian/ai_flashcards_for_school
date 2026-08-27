"""Grundmodell: bundles und karten

Revision ID: 0001
Revises:
Create Date: 2026-08-27 16:20:28.026137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
# Nummeriert statt gehasht: So heisst die Datei wie die Revision und die
# Reihenfolge der Migrationen ist am Verzeichnis ablesbar. Naechste Migration
# anlegen mit
#     uv run alembic revision --autogenerate --rev-id 0002 -m "..."
# siehe die Erklaerung bei file_template in alembic.ini.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Die 5000 in den Constraints ck_*_max_laenge unten MUSS mit MAX_LAENGE in
# app/markdown.py und MAX_MARKDOWN_LAENGE in app/models.py uebereinstimmen.
# Die Zahl steht hier absichtlich ausgeschrieben und wird nicht importiert:
# Eine Migration beschreibt den Zustand der Datenbank zu ihrem Zeitpunkt und
# darf sich nicht mitverschieben, wenn sich der Anwendungscode aendert.
# Bewacht von
# tests/test_models.py::test_markdown_grenze_und_datenbankgrenze_passen_zusammen.
#
# Warum es diese Grenze gibt: app/markdown.rendern() wirft MarkdownZuLang bei
# laengeren Texten, und gerendert wird erst beim Ausliefern der Lernseite. Eine
# zu lange Karte in der Datenbank macht die ganze Seite fuer alle Lernenden
# dieses Bundles kaputt, nicht nur die eine Karte.
#
# Alle Laengengrenzen der Inhaltsspalten stehen als CHECK-Constraint da und
# nicht als VARCHAR(n): Eine ueberlange Eingabe soll denselben Fehlertyp
# ausloesen wie jede andere verletzte Regel (IntegrityError mit lesbarem
# Constraint-Namen), nicht ein DataError aus der Typkonvertierung.


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('bundles',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('slug', sa.String(length=120), nullable=False),
    sa.Column('titel', sa.Text(), nullable=False),
    sa.Column('beschreibung', sa.Text(), nullable=True),
    sa.Column('klasse', sa.Text(), nullable=True),
    sa.Column('selbsteinschaetzung', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('reihenfolge', sa.String(length=20), server_default='zufall', nullable=False),
    sa.Column('aktiv', sa.Boolean(), server_default='true', nullable=False),
    sa.Column('erstellt_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('geaendert_am', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("reihenfolge IN ('zufall', 'fest')", name='ck_bundles_reihenfolge'),
    # NOT NULL allein liesse einen Leerstring oder reine Leerzeichen durch.
    sa.CheckConstraint("length(btrim(titel)) > 0", name='ck_bundles_titel_nicht_leer'),
    sa.CheckConstraint("length(btrim(slug)) > 0", name='ck_bundles_slug_nicht_leer'),
    # Laengengrenzen, siehe Kommentarblock oben. length(NULL) ist NULL und ein
    # CHECK gilt bei NULL als erfuellt - die optionalen Spalten brauchen
    # deshalb kein zusaetzliches "IS NULL OR".
    # 200 Zeichen fuer den Titel: eine einzeilige Ueberschrift, kein Markdown.
    sa.CheckConstraint("length(titel) <= 200", name='ck_bundles_titel_max_laenge'),
    # beschreibung ist Markdown und geht durch app/markdown.rendern().
    sa.CheckConstraint("length(beschreibung) <= 5000", name='ck_bundles_beschreibung_max_laenge'),
    # 60 Zeichen fuer die Klasse: fasst auch "Fachinformatiker
    # Systemintegration 23b" und nicht nur "FS 23b".
    sa.CheckConstraint("length(klasse) <= 60", name='ck_bundles_klasse_max_laenge'),
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
    # String(30), nicht String(12): Ein kuenftiger Kartentyp mit laengerem
    # Bezeichner soll am CHECK ck_karten_art scheitern (IntegrityError) und
    # nicht schon an der Spaltenlaenge (StringDataRightTruncation ->
    # DataError). Siehe reihenfolge in bundles, gleiche Ueberlegung.
    sa.Column('art', sa.String(length=30), nullable=False),
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
    # erklaerung in derselben Machart: optional, aber wenn gesetzt, mit Inhalt.
    sa.CheckConstraint("erklaerung IS NULL OR length(btrim(erklaerung)) > 0", name='ck_karten_erklaerung_nicht_leer'),
    # Laengengrenzen, siehe Kommentarblock oben. Alle drei Spalten sind
    # Markdown und gehen durch app/markdown.rendern().
    sa.CheckConstraint("length(vorderseite) <= 5000", name='ck_karten_vorderseite_max_laenge'),
    sa.CheckConstraint("length(rueckseite) <= 5000", name='ck_karten_rueckseite_max_laenge'),
    sa.CheckConstraint("length(erklaerung) <= 5000", name='ck_karten_erklaerung_max_laenge'),
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
    # Die Spec nennt in Abschnitt 4 eine Textliste. Ohne diesen Constraint
    # gingen [1, 2, 3], [null, null] oder [{"a":1},{"b":2}] durch - Typ und
    # Anzahl stimmen ja. Ein CHECK darf keine Unterabfrage enthalten, also
    # kein EXISTS ueber jsonb_array_elements(). Stattdessen der Vergleich
    # zweier Anzahlen: jsonb_path_query_array() ist immutable, kommt ohne
    # Unterabfrage aus und liefert genau die Elemente vom Typ String. Sind
    # das genauso viele wie insgesamt, ist jedes Element ein String.
    sa.CheckConstraint("\n            CASE\n                WHEN art <> 'frage' THEN true\n                WHEN jsonb_typeof(antworten) = 'array'\n                    THEN jsonb_array_length(antworten) = jsonb_array_length(\n                        jsonb_path_query_array(\n                            antworten, '$[*] ? (@.type() == \"string\")'))\n                ELSE false\n            END\n            ", name='ck_karten_antworten_sind_texte'),
    # Eine Antwortmoeglichkeit ohne sichtbaren Text ist auf der Karte ein
    # leerer Knopf. Der Pfadausdruck sucht ein Element, das ein String ist
    # und kein Zeichen ausserhalb der Leerzeichen enthaelt; der Constraint
    # verlangt, dass es kein solches gibt. Die Einschraenkung auf
    # @.type() == "string" ist Absicht: Ein Element vom falschen Typ soll
    # ausschliesslich ck_karten_antworten_sind_texte verletzen, damit der
    # gemeldete Constraint-Name eindeutig ist - PostgreSQL garantiert keine
    # Reihenfolge, in der Constraints geprueft werden.
    sa.CheckConstraint("\n            CASE\n                WHEN art <> 'frage' THEN true\n                WHEN jsonb_typeof(antworten) = 'array'\n                    THEN NOT jsonb_path_exists(\n                        antworten,\n                        '$[*] ? (@.type() == \"string\"'\n                        ' && !(@ like_regex \"[^[:space:]]\"))')\n                ELSE false\n            END\n            ", name='ck_karten_antworten_nicht_leer'),
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
