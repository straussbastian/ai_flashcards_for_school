"""Tests fuer POST /oauth/register (RFC 7591).

Der Endpunkt ist unauthentifiziert - so ist Dynamic Client Registration
gedacht. Eine Registrierung allein ist wertlos: Ohne das Passwort der
Lehrerin auf der Zustimmungsseite bekommt der Client nie einen Token.
"""

from app.oauth.redirect import CLAUDE_RUECKSPRUNG


def _registrieren(client, **abweichungen):
    koerper = {
        "client_name": "Claude",
        "redirect_uris": [CLAUDE_RUECKSPRUNG],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    koerper.update(abweichungen)
    return client.post("/oauth/register", json=koerper)


def test_registrierung_gibt_eine_client_id_zurueck(client, konfiguration):
    antwort = _registrieren(client)
    assert antwort.status_code == 201
    daten = antwort.json()
    assert len(daten["client_id"]) >= 20
    assert daten["redirect_uris"] == [CLAUDE_RUECKSPRUNG]
    assert daten["token_endpoint_auth_method"] == "none"
    assert daten["grant_types"] == ["authorization_code", "refresh_token"]
    assert daten["response_types"] == ["code"]
    assert daten["scope"] == "lernseiten"
    assert isinstance(daten["client_id_issued_at"], int)


def test_kein_client_secret_in_der_antwort(client, konfiguration):
    """Oeffentlicher Client mit PKCE. Ein Geheimnis in Anthropics Cloud waere
    keines - und die Metadaten sagen token_endpoint_auth_method: none."""
    assert "client_secret" not in _registrieren(client).json()


def test_zwei_registrierungen_ergeben_zwei_ids(client, konfiguration):
    erste = _registrieren(client).json()["client_id"]
    zweite = _registrieren(client).json()["client_id"]
    assert erste != zweite


def test_fremde_rueckadresse_wird_abgelehnt(client, konfiguration):
    antwort = _registrieren(client, redirect_uris=["https://boese.example/callback"])
    assert antwort.status_code == 400
    daten = antwort.json()
    assert daten["error"] == "invalid_redirect_uri"
    assert "boese.example" in daten["error_description"]
    assert "claude.ai" in daten["error_description"]


def test_eine_gute_und_eine_schlechte_adresse_wird_abgelehnt(client, konfiguration):
    """Alles oder nichts - sonst haette der Client eine Adresse registriert,
    von der er annimmt, sie sei erlaubt."""
    antwort = _registrieren(
        client, redirect_uris=[CLAUDE_RUECKSPRUNG, "https://boese.example/callback"]
    )
    assert antwort.status_code == 400


def test_leere_liste_wird_abgelehnt(client, konfiguration):
    antwort = _registrieren(client, redirect_uris=[])
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_redirect_uri"


def test_fehlendes_feld_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/register", json={"client_name": "Claude"})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_client_metadata"


def test_registrierung_ist_von_ueberall_aufrufbar(client, konfiguration):
    assert _registrieren(client).headers["access-control-allow-origin"] == "*"


def test_die_antwort_wird_nicht_zwischengespeichert(client, konfiguration):
    assert _registrieren(client).headers["cache-control"] == "no-store"
