"""Tests fuer GET/POST /oauth/authorize.

Die Reihenfolge der Pruefungen ist hier sicherheitsrelevant und wird
mitgetestet: Solange nicht feststeht, dass die Rueckadresse zu einem
registrierten Client gehoert, darf NICHTS dorthin weitergeleitet werden -
auch kein Fehler. Sonst waere der Server ein offener Weiterleiter.
"""

from urllib.parse import parse_qs, urlsplit

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.redirect import CLAUDE_RUECKSPRUNG
from tests.conftest import TEST_LEHRERINNEN_PASSWORT


def _client_id(client) -> str:
    antwort = client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_RUECKSPRUNG]},
    )
    return antwort.json()["client_id"]


def _parameter(client_id: str, verifier: str, **abweichungen) -> dict:
    werte = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CLAUDE_RUECKSPRUNG,
        "scope": "lernseiten",
        "state": "zustand-123",
        "code_challenge": pkce_ableiten(verifier),
        "code_challenge_method": "S256",
        "resource": "https://karten.example.de/mcp",
    }
    werte.update(abweichungen)
    return {name: wert for name, wert in werte.items() if wert is not None}


def test_die_seite_fragt_nach_dem_passwort(client, konfiguration):
    kennung = _client_id(client)
    antwort = client.get("/oauth/authorize", params=_parameter(kennung, neues_geheimnis()))
    assert antwort.status_code == 200
    assert 'type="password"' in antwort.text
    assert "Lernseiten" in antwort.text


def test_die_seite_traegt_die_parameter_verborgen_weiter(client, konfiguration):
    """Sonst waeren sie nach dem Absenden weg und der Ablauf braeche ab."""
    kennung = _client_id(client)
    verifier = neues_geheimnis()
    werte = _parameter(kennung, verifier)
    text = client.get("/oauth/authorize", params=werte).text
    for name in ("client_id", "redirect_uri", "state", "code_challenge", "resource"):
        assert f'name="{name}"' in text
    assert werte["code_challenge"] in text


def test_unbekannter_client_bekommt_eine_deutsche_seite_ohne_weiterleitung(
    client, konfiguration
):
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter("gibt-es-nicht", neues_geheimnis()),
        follow_redirects=False,
    )
    assert antwort.status_code == 400
    assert "location" not in antwort.headers
    assert "nicht bekannt" in antwort.text


def test_fremde_rueckadresse_wird_nicht_angesteuert(client, konfiguration):
    """Der Test gegen den offenen Weiterleiter."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(
            kennung, neues_geheimnis(), redirect_uri="https://boese.example/callback"
        ),
        follow_redirects=False,
    )
    assert antwort.status_code == 400
    assert "location" not in antwort.headers


def test_fehlende_pkce_angabe_wird_zur_rueckadresse_gemeldet(client, konfiguration):
    """Ab hier ist die Rueckadresse geprueft, also darf der Fehler dorthin."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), code_challenge=None),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    ziel = urlsplit(antwort.headers["location"])
    assert f"{ziel.scheme}://{ziel.netloc}{ziel.path}" == CLAUDE_RUECKSPRUNG
    parameter = parse_qs(ziel.query)
    assert parameter["error"] == ["invalid_request"]
    assert parameter["state"] == ["zustand-123"]


def test_pkce_ohne_s256_wird_abgelehnt(client, konfiguration):
    """Die Metadaten nennen ausschliesslich S256. "plain" waere kein Schutz."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), code_challenge_method="plain"),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    assert parse_qs(urlsplit(antwort.headers["location"]).query)["error"] == [
        "invalid_request"
    ]


def test_falscher_response_type_wird_abgelehnt(client, konfiguration):
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), response_type="token"),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    assert parse_qs(urlsplit(antwort.headers["location"]).query)["error"] == [
        "unsupported_response_type"
    ]


def test_richtiges_passwort_liefert_einen_code(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": TEST_LEHRERINNEN_PASSWORT},
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    parameter = parse_qs(urlsplit(antwort.headers["location"]).query)
    assert len(parameter["code"][0]) == 43
    assert parameter["state"] == ["zustand-123"]


def test_falsches_passwort_zeigt_die_seite_erneut(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": "falsch"},
        follow_redirects=False,
    )
    assert antwort.status_code == 401
    assert "Das Passwort stimmt nicht" in antwort.text
    assert 'type="password"' in antwort.text
    assert "location" not in antwort.headers


def test_das_passwort_steht_nie_in_der_antwort(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": TEST_LEHRERINNEN_PASSWORT},
        follow_redirects=False,
    )
    assert TEST_LEHRERINNEN_PASSWORT not in antwort.text
    assert TEST_LEHRERINNEN_PASSWORT not in antwort.headers.get("location", "")


def test_die_zustimmungsseite_erlaubt_ihr_eigenes_formular(client, konfiguration):
    """Ohne diese Ausnahme blockiert die Richtlinie das Absenden.

    Die bestehende Richtlinie enthaelt form-action 'none'. Sie gilt fuer das
    Ziel des Formulars UND fuer die Weiterleitung danach - beide muessen
    erlaubt sein, sonst bricht der Ablauf im Browser ab, ohne dass am Server
    etwas auffiele.
    """
    kennung = _client_id(client)
    richtlinie = client.get(
        "/oauth/authorize", params=_parameter(kennung, neues_geheimnis())
    ).headers["content-security-policy"]
    assert "form-action 'self' https://claude.ai" in richtlinie
    assert "http://localhost:*" in richtlinie
    assert "http://127.0.0.1:*" in richtlinie
    assert "form-action 'none'" not in richtlinie
