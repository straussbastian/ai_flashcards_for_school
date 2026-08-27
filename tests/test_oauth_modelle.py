"""Tests fuer die OAuth-Tabellen.

Dieselbe Haltung wie in tests/test_models.py: Falsche Daten duerfen gar
nicht erst hineinkommen, und geprueft wird das gegen echtes PostgreSQL -
die Constraints sind der Kern des Modells und in SQLite nicht vorhanden.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.oauth.modelle import ART_ERNEUERUNG, ART_ZUGRIFF, OAuthClient, OAuthCode, OAuthToken


def _client(**abweichungen) -> OAuthClient:
    felder = {
        "client_id": "kunde-" + uuid.uuid4().hex[:8],
        "client_name": "Claude",
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "scope": "lernseiten",
    }
    felder.update(abweichungen)
    return OAuthClient(**felder)


def _in_einer_stunde() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def test_ein_client_laesst_sich_speichern(session):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    assert kunde.erstellt_am is not None


async def test_redirect_uris_darf_keine_leere_liste_sein(session):
    session.add(_client(redirect_uris=[]))
    with pytest.raises(IntegrityError, match="ck_oauth_clients_redirect_uris"):
        await session.flush()


async def test_redirect_uris_darf_keine_zahlen_enthalten(session):
    session.add(_client(redirect_uris=[1, 2]))
    with pytest.raises(IntegrityError, match="ck_oauth_clients_redirect_uris"):
        await session.flush()


async def test_unbekannte_tokenart_wird_abgelehnt(session):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthToken(
            token_hash="a" * 64,
            art="zauberstab",
            client_id=kunde.client_id,
            familie_id=uuid.uuid4(),
            scope="lernseiten",
            ablauf_am=_in_einer_stunde(),
        )
    )
    with pytest.raises(IntegrityError, match="ck_oauth_tokens_art"):
        await session.flush()


@pytest.mark.parametrize("art", [ART_ZUGRIFF, ART_ERNEUERUNG])
async def test_beide_tokenarten_sind_erlaubt(session, art):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthToken(
            token_hash=uuid.uuid4().hex * 2,
            art=art,
            client_id=kunde.client_id,
            familie_id=uuid.uuid4(),
            scope="lernseiten",
            ablauf_am=_in_einer_stunde(),
        )
    )
    await session.flush()


async def test_ein_code_haengt_am_client_und_faellt_mit_ihm(session):
    """ON DELETE CASCADE: Wird ein Client geloescht, verschwinden seine Codes."""
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthCode(
            code_hash="b" * 64,
            client_id=kunde.client_id,
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            code_challenge="c" * 43,
            scope="lernseiten",
            familie_id=uuid.uuid4(),
            ablauf_am=_in_einer_stunde(),
        )
    )
    await session.flush()

    await session.delete(kunde)
    await session.flush()

    uebrig = await session.scalar(select(func.count()).select_from(OAuthCode.__table__))
    assert uebrig == 0
