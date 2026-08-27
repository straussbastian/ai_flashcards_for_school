"""Tests fuer den MCP-Endpunkt als Transport - noch ohne Werkzeuge.

Der 401 mit WWW-Authenticate ist laut Spec, Abschnitt 5, der Ausloeser des
gesamten OAuth-Ablaufs. Geht er verloren, meldet Claude nur "Couldn't reach
the MCP server" und niemand sieht, woran es lag.
"""

import pytest

from app.oauth.geheimnisse import neues_geheimnis
from app.oauth.speicher import client_anlegen, tokenpaar_ausgeben
from tests.conftest import TEST_BASIS_URL

import uuid

KOEPFE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def _zugriffstoken(session) -> str:
    kunde = await client_anlegen(
        session, client_name="Claude",
        redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
    )
    zugriff, _, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=uuid.uuid4(),
        scope="lernseiten", resource=f"{TEST_BASIS_URL}/mcp",
    )
    return zugriff


async def test_ohne_token_kommt_401_mit_wegweiser(klient, konfiguration, mcp_sitzung):
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    assert antwort.status_code == 401
    wegweiser = antwort.headers["www-authenticate"]
    assert wegweiser.startswith("Bearer")
    assert (
        f'resource_metadata="{TEST_BASIS_URL}/.well-known/oauth-protected-resource/mcp"'
        in wegweiser
    )


async def test_der_genannte_wegweiser_ist_auch_erreichbar(klient, konfiguration, mcp_sitzung):
    """Ein Kopf, der auf eine 404 zeigt, waere schlimmer als keiner."""
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    wegweiser = antwort.headers["www-authenticate"]
    pfad = wegweiser.split('resource_metadata="')[1].split('"')[0]
    pfad = pfad[len(TEST_BASIS_URL):]
    dokument = await klient.get(pfad)
    assert dokument.status_code == 200
    assert dokument.json()["resource"] == f"{TEST_BASIS_URL}/mcp"


async def test_erfundener_token_wird_abgelehnt(klient, konfiguration, mcp_sitzung):
    antwort = await klient.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={**KOEPFE, "Authorization": f"Bearer {neues_geheimnis()}"},
    )
    assert antwort.status_code == 401


async def test_handschlag_mit_gueltigem_token(klient, konfiguration, mcp_sitzung, mcp_laeuft):
    token = await _zugriffstoken(mcp_sitzung)
    antwort = await klient.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        headers={**KOEPFE, "Authorization": f"Bearer {token}"},
    )
    assert antwort.status_code == 200
    assert antwort.headers["mcp-session-id"]


async def test_fremder_host_wird_nicht_abgewiesen(klient, konfiguration, mcp_sitzung, mcp_laeuft):
    """Der DNS-Rebinding-Schutz des SDK ist ausdruecklich abgeschaltet (E-2).

    Faellt jemand versehentlich auf die Voreinstellung zurueck, akzeptiert
    das SDK nur localhost-Hostnamen und antwortet allem anderen mit 421 -
    also jeder Anfrage aus Anthropics Cloud. Dieser Test ist die Sperre
    dagegen.
    """
    token = await _zugriffstoken(mcp_sitzung)
    antwort = await klient.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        headers={
            **KOEPFE,
            "Authorization": f"Bearer {token}",
            "Host": "karten.example.de",
            "Origin": "https://claude.ai",
        },
    )
    assert antwort.status_code == 200


async def test_der_mcp_endpunkt_traegt_keine_inhaltsrichtlinie(klient, konfiguration, mcp_sitzung):
    """Dort wird kein Dokument ausgeliefert - siehe app/sicherheit.py."""
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    assert "content-security-policy" not in antwort.headers


async def test_die_lernseite_bleibt_erreichbar(klient, konfiguration, mcp_sitzung):
    """Die MCP-Route darf /{slug} nicht verdecken. Ein Mount an "" wuerde
    genau das tun (nachgemessen) - deshalb ist es eine Route, kein Mount."""
    antwort = await klient.get("/gibt-es-nicht-wirklich")
    assert antwort.status_code == 404
    assert "Diese Lernseite gibt es nicht" in antwort.text


async def test_ein_mehrsegmentiger_pfad_bleibt_die_deutsche_404_seite(
    klient, konfiguration, mcp_sitzung
):
    antwort = await klient.get("/ein-zwei-drei/vier")
    assert antwort.status_code == 404
    assert "Diese Lernseite gibt es nicht" in antwort.text


def test_der_rebinding_schutz_ist_ausdruecklich_abgeschaltet(konfiguration):
    """Gegenprobe auf der Ebene der Einstellung, nicht nur der Wirkung.

    Wird transport_security gar nicht uebergeben, schaltet das SDK bei
    host="127.0.0.1" selbsttaetig den localhost-Schutz ein. Dieser Test
    scheitert dann, weil das Feld None waere.
    """
    from app.mcp import TRANSPORTSICHERHEIT

    assert TRANSPORTSICHERHEIT is not None
    assert TRANSPORTSICHERHEIT.enable_dns_rebinding_protection is False
