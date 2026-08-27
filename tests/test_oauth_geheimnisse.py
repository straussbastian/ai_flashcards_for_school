"""Tests fuer app/oauth/geheimnisse.py.

Braucht keine Datenbank: Hier geht es nur um Zufall, HMAC und die
PKCE-Ableitung.
"""

import base64
import hashlib

import pytest

from app.config import get_settings
from app.oauth.geheimnisse import gleich, neues_geheimnis, pfeffern, pkce_ableiten


def test_geheimnisse_sind_lang_und_url_sicher():
    wert = neues_geheimnis()
    assert len(wert) == 43
    assert set(wert) <= set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    )


def test_zwei_geheimnisse_sind_verschieden():
    assert neues_geheimnis() != neues_geheimnis()


def test_pfeffern_ist_stabil_und_hexadezimal():
    einmal = pfeffern("abc")
    nochmal = pfeffern("abc")
    assert einmal == nochmal
    assert len(einmal) == 64
    int(einmal, 16)  # wirft ValueError, wenn es kein Hex ist


def test_pfeffern_haengt_am_app_secret(monkeypatch):
    """Ein anderer Schluessel muss einen anderen Hash ergeben.

    Sonst waere der Pfeffer wirkungslos und der gespeicherte Hash allein aus
    dem Token berechenbar - ohne Kenntnis von APP_SECRET.
    """
    vorher = pfeffern("abc")
    monkeypatch.setenv("APP_SECRET", "ein-voellig-anderer-schluessel")
    get_settings.cache_clear()
    try:
        nachher = pfeffern("abc")
    finally:
        get_settings.cache_clear()
    assert vorher != nachher


def test_gleich_erkennt_gleiches_und_ungleiches():
    assert gleich("abc", "abc")
    assert not gleich("abc", "abd")
    assert not gleich("abc", "abcd")


def test_pkce_ableitung_entspricht_rfc_7636():
    """Gegenprobe von Hand: base64url(sha256(verifier)) ohne Polsterzeichen."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    erwartet = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    assert pkce_ableiten(verifier) == erwartet
    assert "=" not in pkce_ableiten(verifier)


@pytest.mark.parametrize("kaputt", ["", "x" * 4, "ä" * 50])
def test_pkce_ableitung_lehnt_unbrauchbare_verifier_ab(kaputt):
    """RFC 7636 verlangt 43 bis 128 Zeichen aus dem unreservierten Alphabet."""
    with pytest.raises(ValueError):
        pkce_ableiten(kaputt)
