import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Der einzige Scope dieses Servers. Ein Ein-Personen-Login braucht keine
# Rechtestufen; der Scope existiert, weil OAuth ihn im Metadatendokument und
# in AuthSettings.required_scopes erwartet.
STANDARD_SCOPE = "lernseiten"

# Die beiden Tokenarten. Deutsche Werte, weil sie in der Datenbank stehen und
# dort niemand englische Bezeichner braucht.
ART_ZUGRIFF = "zugriff"
ART_ERNEUERUNG = "erneuerung"

# Gepfefferte SHA-256-Hashes in Hexdarstellung sind immer 64 Zeichen lang.
HASH_LAENGE = 64

# RFC 7591 setzt keine Obergrenze fuer eine Redirect-URI. 2000 Zeichen sind
# das, was Browser und Proxys sicher tragen, und begrenzen zugleich, was ein
# unauthentifizierter Registrierungsaufruf in die Datenbank schreiben kann.
MAX_REDIRECT_URI_LAENGE = 2000


class OAuthClient(Base):
    """Ein per Dynamic Client Registration angemeldeter Client (RFC 7591)."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_name: Mapped[str | None] = mapped_column(Text)
    # MutableList.as_mutable wie bei Karte.antworten in app/models.py: Ohne
    # das bemerkt SQLAlchemy eine Aenderung an der Liste selbst nicht.
    redirect_uris: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Dieselbe Machart wie ck_karten_antworten_sind_texte in
        # migrations/versions/0001_grundmodell.py, inklusive des
        # "strict"-Schluesselworts: Ohne "strict" packt der jsonpath-Modus
        # "lax" ein verschachteltes Array eine Ebene tief aus, bevor der
        # Filter greift - [["https://x"]] kaeme dann durch. CASE WHEN statt
        # AND/OR, weil PostgreSQL bei AND/OR keine Auswertungsreihenfolge
        # garantiert und jsonb_array_length() auf einem Objekt einen
        # DataError statt eines IntegrityError werfen wuerde.
        CheckConstraint(
            """
            CASE
                WHEN jsonb_typeof(redirect_uris) = 'array'
                    THEN jsonb_array_length(redirect_uris) >= 1
                        AND jsonb_array_length(redirect_uris) = jsonb_array_length(
                            jsonb_path_query_array(
                                redirect_uris, 'strict $[*] ? (@.type() == "string")'))
                ELSE false
            END
            """,
            name="ck_oauth_clients_redirect_uris",
        ),
    )


class OAuthCode(Base):
    """Ein ausgegebener Autorisierungscode. Genau einmal einloesbar."""

    __tablename__ = "oauth_codes"

    code_hash: Mapped[str] = mapped_column(String(HASH_LAENGE), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    # RFC 8707. Wird mitgeschrieben, aber nicht erzwungen - siehe E-3 im Plan.
    resource: Mapped[str | None] = mapped_column(Text)
    # Alle Tokens, die aus diesem Code hervorgehen, tragen dieselbe
    # familie_id. Wird ein bereits eingeloester Code oder ein bereits
    # rotierter Refresh-Token ein zweites Mal vorgelegt, gilt die ganze
    # Familie als kompromittiert und wird zurueckgezogen.
    familie_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eingeloest_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            f"length(redirect_uri) <= {MAX_REDIRECT_URI_LAENGE}",
            name="ck_oauth_codes_redirect_uri_max_laenge",
        ),
    )


class OAuthToken(Base):
    """Ein ausgegebener Zugriffs- oder Erneuerungstoken.

    Gespeichert wird ausschliesslich der gepfefferte Hash (siehe
    app/oauth/geheimnisse.py). Ein gestohlener Datenbankauszug enthaelt damit
    keine benutzbaren Tokens.
    """

    __tablename__ = "oauth_tokens"

    token_hash: Mapped[str] = mapped_column(String(HASH_LAENGE), primary_key=True)
    art: Mapped[str] = mapped_column(String(30), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    familie_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    resource: Mapped[str | None] = mapped_column(Text)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zurueckgezogen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # String(30) statt String(12) aus demselben Grund wie bei Karte.art in
        # app/models.py: Eine unbekannte Art soll am CHECK scheitern
        # (IntegrityError), nicht schon an der Spaltenlaenge (DataError).
        CheckConstraint(
            f"art IN ('{ART_ZUGRIFF}', '{ART_ERNEUERUNG}')",
            name="ck_oauth_tokens_art",
        ),
    )
