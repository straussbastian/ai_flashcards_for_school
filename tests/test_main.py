import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _mit_testdatenbank(datenbank_override):
    """Aktiviert fuer alle Tests dieser Datei den Datenbank-Override aus conftest.py.

    So treffen Anfragen ueber den TestClient die Testdatenbank statt der
    echten Entwicklungsdatenbank.
    """
    yield


def test_healthz_meldet_ok():
    antwort = client.get("/healthz")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "ok"


def test_landeseite_verraet_keine_bundles():
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "bundle" not in antwort.text.lower()


def test_healthz_meldet_datenbank_ok():
    antwort = client.get("/healthz")
    assert antwort.json()["datenbank"] == "ok"
