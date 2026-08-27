"""Tests fuer die beiden Discovery-Dokumente.

Der wichtigste Test dieser Datei ist der letzte: Die Dokumente duerfen
niemals aus Request-Headern entstehen. Der Container startet uvicorn mit
--forwarded-allow-ips='*' (siehe docker/app-start.sh), weil hinter Coolify
ein Reverse Proxy sitzt - X-Forwarded-Host und X-Forwarded-Proto sind damit
faelschbar. Die Spec verlangt in Abschnitt 5, dass "resource" exakt der von
der Lehrerin eingetragenen URL entspricht.
"""

from tests.conftest import TEST_BASIS_URL

WELLKNOWN_KURZ = "/.well-known/oauth-protected-resource"
WELLKNOWN_LANG = "/.well-known/oauth-protected-resource/mcp"
WELLKNOWN_AS = "/.well-known/oauth-authorization-server"


def test_geschuetzte_resource_nennt_genau_die_mcp_adresse(client, konfiguration):
    antwort = client.get(WELLKNOWN_LANG)
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["resource"] == f"{TEST_BASIS_URL}/mcp"
    assert daten["authorization_servers"] == [TEST_BASIS_URL]
    assert daten["scopes_supported"] == ["lernseiten"]
    assert daten["bearer_methods_supported"] == ["header"]


def test_beide_pfade_liefern_dasselbe_dokument(client, konfiguration):
    """RFC 9728 verlangt den Pfad mit angehaengtem /mcp, die Spec nennt den
    kurzen. Es gibt beide, damit keiner ins Leere laeuft."""
    assert client.get(WELLKNOWN_KURZ).json() == client.get(WELLKNOWN_LANG).json()


def test_autorisierungsserver_nennt_die_drei_endpunkte(client, konfiguration):
    daten = client.get(WELLKNOWN_AS).json()
    assert daten["issuer"] == TEST_BASIS_URL
    assert daten["authorization_endpoint"] == f"{TEST_BASIS_URL}/oauth/authorize"
    assert daten["token_endpoint"] == f"{TEST_BASIS_URL}/oauth/token"
    assert daten["registration_endpoint"] == f"{TEST_BASIS_URL}/oauth/register"


def test_pkce_mit_s256_steht_in_den_metadaten(client, konfiguration):
    """Die Spec verlangt code_challenge_methods_supported: ["S256"]."""
    daten = client.get(WELLKNOWN_AS).json()
    assert daten["code_challenge_methods_supported"] == ["S256"]
    assert daten["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert daten["response_types_supported"] == ["code"]


def test_die_dokumente_sind_von_ueberall_lesbar(client, konfiguration):
    """Die Verbindungsmaske von claude.ai laeuft im Browser und holt die
    Dokumente per fetch. Ohne CORS-Kopf bricht sie mit einer Meldung ab, die
    nichts ueber die Ursache sagt."""
    for pfad in (WELLKNOWN_KURZ, WELLKNOWN_LANG, WELLKNOWN_AS):
        antwort = client.get(pfad)
        assert antwort.headers["access-control-allow-origin"] == "*"


def test_gefaelschte_weiterleitungskoepfe_aendern_nichts(client, konfiguration):
    """Der Kern des Ganzen: X-Forwarded-* darf die Dokumente nicht anfassen."""
    antwort = client.get(
        WELLKNOWN_LANG,
        headers={
            "Host": "boese.example",
            "X-Forwarded-Host": "boese.example",
            "X-Forwarded-Proto": "http",
        },
    )
    daten = antwort.json()
    assert daten["resource"] == f"{TEST_BASIS_URL}/mcp"
    assert "boese.example" not in antwort.text

    daten = client.get(
        WELLKNOWN_AS, headers={"X-Forwarded-Host": "boese.example"}
    ).json()
    assert daten["issuer"] == TEST_BASIS_URL
