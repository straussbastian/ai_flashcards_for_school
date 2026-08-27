def test_healthz_meldet_ok(client):
    antwort = client.get("/healthz")
    assert antwort.status_code == 200
    assert antwort.json()["status"] == "ok"


def test_landeseite_verraet_keine_bundles(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "bundle" not in antwort.text.lower()


def test_healthz_meldet_datenbank_ok(client):
    antwort = client.get("/healthz")
    assert antwort.json()["datenbank"] == "ok"
