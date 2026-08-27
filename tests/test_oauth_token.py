"""Tests fuer POST /oauth/token - inklusive des vollstaendigen Ablaufs.

Der Ablauf laeuft hier ohne Cowork durch: registrieren, zustimmen, Code
einloesen, erneuern. Genau das verlangt die Spec in Abschnitt 8 ("OAuth
vollstaendig") und Abschnitt 9 ("Der OAuth-Ablauf wird lokal ueber Tests
geprueft").
"""

import time
from urllib.parse import parse_qs, urlsplit

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.redirect import CLAUDE_RUECKSPRUNG
from tests.conftest import TEST_LEHRERINNEN_PASSWORT


def _code_besorgen(client) -> tuple[str, str, str]:
    """Fuehrt Registrierung und Zustimmung durch.

    Returns:
        (Autorisierungscode, code_verifier, client_id)
    """
    kennung = client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_RUECKSPRUNG]},
    ).json()["client_id"]
    verifier = neues_geheimnis()
    antwort = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": kennung,
            "redirect_uri": CLAUDE_RUECKSPRUNG,
            "scope": "lernseiten",
            "state": "zustand-123",
            "code_challenge": pkce_ableiten(verifier),
            "code_challenge_method": "S256",
            "resource": "https://karten.example.de/mcp",
            "passwort": TEST_LEHRERINNEN_PASSWORT,
        },
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(antwort.headers["location"]).query)["code"][0]
    return code, verifier, kennung


def _einloesen(client, code, verifier, kennung):
    return client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CLAUDE_RUECKSPRUNG,
            "client_id": kennung,
            "code_verifier": verifier,
        },
    )


def test_der_vollstaendige_ablauf_liefert_ein_tokenpaar(client, konfiguration):
    antwort = _einloesen(client, *_code_besorgen(client))
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["token_type"] == "Bearer"
    assert daten["expires_in"] == 3600
    assert daten["scope"] == "lernseiten"
    assert len(daten["access_token"]) == 43
    assert len(daten["refresh_token"]) == 43
    assert daten["access_token"] != daten["refresh_token"]


def test_die_tokenantwort_wird_nicht_zwischengespeichert(client, konfiguration):
    antwort = _einloesen(client, *_code_besorgen(client))
    assert antwort.headers["cache-control"] == "no-store"


def test_ein_code_gilt_nur_einmal(client, konfiguration):
    code, verifier, kennung = _code_besorgen(client)
    assert _einloesen(client, code, verifier, kennung).status_code == 200
    zweite = _einloesen(client, code, verifier, kennung)
    assert zweite.status_code == 400
    assert zweite.json()["error"] == "invalid_grant"


def test_falscher_verifier_wird_mit_invalid_grant_beantwortet(client, konfiguration):
    code, _, kennung = _code_besorgen(client)
    antwort = _einloesen(client, code, neues_geheimnis(), kennung)
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_grant"
    assert "verbinde den Connector" in antwort.json()["error_description"]


def test_unbekannter_code_wird_mit_invalid_grant_beantwortet(client, konfiguration):
    _, verifier, kennung = _code_besorgen(client)
    antwort = _einloesen(client, neues_geheimnis(), verifier, kennung)
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_grant"


def test_unbekannter_grant_type_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/token", data={"grant_type": "password"})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "unsupported_grant_type"


def test_fehlender_grant_type_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/token", data={})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "unsupported_grant_type"


def test_erneuern_rotiert_den_refresh_token(client, konfiguration):
    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    zweite = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    ).json()
    assert zweite["refresh_token"] != erste["refresh_token"]
    assert zweite["access_token"] != erste["access_token"]


def test_ein_verbrauchter_refresh_token_wird_mit_invalid_grant_beantwortet(
    client, konfiguration
):
    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    nochmal = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    assert nochmal.status_code == 400
    assert nochmal.json()["error"] == "invalid_grant"


def test_der_ablauf_bleibt_deutlich_unter_zehn_sekunden(client, konfiguration):
    """Die Spec verlangt in Abschnitt 5: "Alle OAuth-Endpunkte antworten
    deutlich unter zehn Sekunden." Der Grenzwert ist absichtlich grosszuegig -
    er soll eine eingebaute Verzoegerung finden, nicht die Rechnerlast messen."""
    begonnen = time.monotonic()
    code, verifier, kennung = _code_besorgen(client)
    _einloesen(client, code, verifier, kennung)
    assert time.monotonic() - begonnen < 5.0


async def test_der_familienwiderruf_ueberlebt_die_ablehnung(client, konfiguration, session):
    """Wird ein verbrauchter Refresh-Token noch einmal vorgelegt, gilt die
    ganze Familie als kompromittiert - und dieser Widerruf muss bestehen
    bleiben, obwohl die Anfrage selbst abgelehnt wird."""
    from app.oauth.speicher import zugriffstoken_pruefen

    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    zweite = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    ).json()
    assert await zugriffstoken_pruefen(session, zweite["access_token"]) is not None

    client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    assert await zugriffstoken_pruefen(session, zweite["access_token"]) is None
