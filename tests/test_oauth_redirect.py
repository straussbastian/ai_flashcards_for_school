"""Tests fuer die Redirect-URI-Regeln.

Die Spec nennt in Abschnitt 5 genau drei erlaubte Formen: die Rueckadresse
von claude.ai exakt, sowie http://localhost/callback und
http://127.0.0.1/callback mit IGNORIERTEM Port (Claude Code waehlt den Port
beim Start zufaellig).
"""

import pytest

from app.oauth.redirect import CLAUDE_RUECKSPRUNG, passt, registrierbar


@pytest.mark.parametrize(
    "uri",
    [
        CLAUDE_RUECKSPRUNG,
        "http://localhost/callback",
        "http://localhost:1455/callback",
        "http://127.0.0.1/callback",
        "http://127.0.0.1:54321/callback",
    ],
)
def test_erlaubte_formen(uri):
    assert registrierbar(uri)


@pytest.mark.parametrize(
    "uri",
    [
        "https://boese.example/callback",
        "http://claude.ai/api/mcp/auth_callback",          # http statt https
        "https://claude.ai/api/mcp/auth_callback/extra",   # Pfad angehaengt
        "https://claude.ai.boese.example/api/mcp/auth_callback",
        "http://localhost/anderswo",
        "https://localhost:1455/callback",                 # https auf Loopback
        "http://[::1]/callback",                           # nicht in der Spec
        "javascript:alert(1)",
        "",
    ],
)
def test_abgelehnte_formen(uri):
    assert not registrierbar(uri)


def test_loopback_passt_mit_beliebigem_port():
    """Registriert wird ohne Port, angefragt wird mit - das muss passen."""
    assert passt("http://127.0.0.1:61234/callback", ["http://127.0.0.1/callback"])
    assert passt("http://localhost/callback", ["http://localhost:8080/callback"])


def test_claude_rueckadresse_passt_nur_exakt():
    assert passt(CLAUDE_RUECKSPRUNG, [CLAUDE_RUECKSPRUNG])
    assert not passt(CLAUDE_RUECKSPRUNG + "?x=1", [CLAUDE_RUECKSPRUNG])


def test_fremde_uri_passt_zu_nichts():
    assert not passt("https://boese.example/callback", [CLAUDE_RUECKSPRUNG])


# ---- Zusaetzlich freigegebene Rueckadressen (EXTRA_REDIRECT_URIS) ----------

N8N = "https://n8n.example.de/rest/oauth2-credential/callback"


def test_zusaetzliche_rueckadresse_ist_nur_mit_freigabe_registrierbar():
    assert not registrierbar(N8N)
    assert registrierbar(N8N, zusaetzliche=(N8N,))


@pytest.mark.parametrize(
    "uri",
    [
        N8N + "/extra",                                       # Pfad angehaengt
        N8N + "?x=1",                                         # Query angehaengt
        "http://n8n.example.de/rest/oauth2-credential/callback",  # http statt https
        "https://n8n.example.de.boese.example/rest/oauth2-credential/callback",
        "https://N8N.example.de/rest/oauth2-credential/callback",  # anders geschrieben
    ],
)
def test_zusaetzliche_rueckadresse_gilt_nur_exakt(uri):
    """Exakter Zeichenvergleich wie bei claude.ai - kein Praefix, keine
    Normalisierung."""
    assert not registrierbar(uri, zusaetzliche=(N8N,))
