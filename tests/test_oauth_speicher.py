"""Tests fuer app/oauth/speicher.py - die Datenbankarbeit des OAuth-Servers.

Ohne HTTP. Geprueft wird, was die Spec in Abschnitt 5 verlangt: Codes sind
genau einmal einloesbar, PKCE ist Pflicht, Refresh-Tokens rotieren, und ein
zurueckgezogener Token wird mit invalid_grant beantwortet - nicht mit einem
eigenen Fehlercode.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.modelle import ART_ERNEUERUNG, ART_ZUGRIFF, OAuthCode, OAuthToken
from app.oauth.speicher import (
    OAuthFehler,
    client_anlegen,
    client_holen,
    code_ausgeben,
    code_einloesen,
    erneuern,
    tokenpaar_ausgeben,
    zugriffstoken_pruefen,
)

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


async def _client(session):
    return await client_anlegen(session, client_name="Claude", redirect_uris=[REDIRECT])


async def _code_mit_verifier(session, kunde):
    verifier = neues_geheimnis()
    code = await code_ausgeben(
        session,
        client=kunde,
        redirect_uri=REDIRECT,
        code_challenge=pkce_ableiten(verifier),
        resource="https://karten.example.de/mcp",
    )
    return code, verifier


async def test_client_anlegen_und_wiederfinden(session):
    kunde = await _client(session)
    assert len(kunde.client_id) >= 20
    gefunden = await client_holen(session, kunde.client_id)
    assert gefunden is not None
    assert gefunden.redirect_uris == [REDIRECT]


async def test_unbekannter_client_ist_none(session):
    assert await client_holen(session, "gibt-es-nicht") is None


async def test_code_wird_genau_einmal_eingeloest(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)

    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    assert eingeloest.eingeloest_am is not None

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_falscher_verifier_wird_abgelehnt(session):
    kunde = await _client(session)
    code, _ = await _code_mit_verifier(session, kunde)

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=neues_geheimnis(),
        )
    assert fehler.value.code == "invalid_grant"


async def test_falsche_redirect_uri_wird_abgelehnt(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id,
            redirect_uri="http://127.0.0.1:9999/callback", code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_abgelaufener_code_wird_abgelehnt(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)
    gespeichert = await session.scalar(select(OAuthCode))
    gespeichert.ablauf_am = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.flush()

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_tokenpaar_ist_pruefbar(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)
    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    zugriff, erneuerung, gueltigkeit = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=eingeloest.familie_id,
        scope=eingeloest.scope, resource=eingeloest.resource,
    )
    assert gueltigkeit == 3600
    assert zugriff != erneuerung

    geprueft = await zugriffstoken_pruefen(session, zugriff)
    assert geprueft is not None
    assert geprueft.client_id == kunde.client_id
    assert geprueft.art == ART_ZUGRIFF


async def test_der_klartext_token_steht_nirgends_in_der_datenbank(session):
    """Gespeichert wird nur der gepfefferte Hash - das ist der ganze Punkt."""
    kunde = await _client(session)
    zugriff, erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id,
        familie_id=(await _code_und_familie(session, kunde)), scope="lernseiten",
        resource=None,
    )
    hashes = (await session.scalars(select(OAuthToken.token_hash))).all()
    assert zugriff not in hashes
    assert erneuerung not in hashes


async def _code_und_familie(session, kunde):
    code, verifier = await _code_mit_verifier(session, kunde)
    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    return eingeloest.familie_id


async def test_erneuern_rotiert_und_zieht_den_alten_zurueck(session):
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erste_erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )

    zweiter_zugriff, zweite_erneuerung, _ = await erneuern(
        session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
    )
    assert zweite_erneuerung != erste_erneuerung
    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is not None

    with pytest.raises(OAuthFehler) as fehler:
        await erneuern(
            session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
        )
    assert fehler.value.code == "invalid_grant"


async def test_wiederverwendung_zieht_die_ganze_familie_zurueck(session):
    """Ein zweites Mal vorgelegter Erneuerungstoken heisst: er wurde gestohlen.

    Dann ist auch der frisch ausgegebene nichts mehr wert - sonst arbeitete
    der Dieb einfach mit dem neueren weiter.
    """
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erste_erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    zweiter_zugriff, _, _ = await erneuern(
        session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
    )
    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is not None

    with pytest.raises(OAuthFehler):
        await erneuern(
            session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
        )

    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is None


async def test_abgelaufener_zugriffstoken_gilt_nicht(session):
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    zugriff, _, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    gespeichert = await session.scalar(
        select(OAuthToken).where(OAuthToken.art == ART_ZUGRIFF)
    )
    gespeichert.ablauf_am = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.flush()

    assert await zugriffstoken_pruefen(session, zugriff) is None


async def test_unbekannter_zugriffstoken_gilt_nicht(session):
    assert await zugriffstoken_pruefen(session, neues_geheimnis()) is None


async def test_ein_erneuerungstoken_taugt_nicht_als_zugriffstoken(session):
    """Sonst waere der langlebige Token unmittelbar ein Schluessel zu /mcp."""
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    assert await zugriffstoken_pruefen(session, erneuerung) is None
    assert ART_ERNEUERUNG != ART_ZUGRIFF
