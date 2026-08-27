from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_meldet_ok():
    antwort = client.get("/healthz")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "ok"


def test_landeseite_verraet_keine_bundles():
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "bundle" not in antwort.text.lower()
