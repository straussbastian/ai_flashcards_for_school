from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db import get_session
from app.main import app


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


class _KaputteSession:
    """Eine Session, deren Abfrage scheitert - so, wie es eine weggefallene Datenbank tut."""

    async def scalar(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("Verbindung weg"))


def test_healthz_meldet_503_wenn_die_datenbank_nicht_antwortet():
    """Der Fehlerzweig von /healthz, an dem der HEALTHCHECK im Dockerfile haengt.

    Die Spec fuehrt "Datenbank weg -> /healthz schlaegt an" als zugesagtes
    Verhalten. Getestet war bisher nur der Gutfall; ein Umbau, der das
    try/except in app/main.py entfernt, waere gruen durchgegangen und der
    Container haette sich im Betrieb als gesund gemeldet, waehrend keine
    einzige Lernseite mehr ausgeliefert werden kann.

    Der Override wird hier direkt gesetzt statt ueber die client-Fixture:
    Diese Fixture haengt an einer echten Testdatenbank, und genau die soll
    hier ja gerade fehlen. Der Test braucht deshalb auch keine Datenbank.
    """
    app.dependency_overrides[get_session] = lambda: _KaputteSession()
    try:
        antwort = TestClient(app).get("/healthz")
    finally:
        del app.dependency_overrides[get_session]

    assert antwort.status_code == 503
    assert antwort.json() == {"status": "fehler", "datenbank": "nicht erreichbar"}
