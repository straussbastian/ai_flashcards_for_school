"""Tests fuer die Schutzkoepfe aus app/sicherheit.py.

Bewusst kein Client aus tests/conftest.py: Die dortige "client"-Fixture
haengt ueber datenbank_override an einer echten Testdatenbank und wuerde
beide Tests hier uebergehen, sobald TEST_DATABASE_URL fehlt - obwohl
beide Tests nur Antwortkoepfe pruefen und keine Datenbank brauchen. Die
Landeseite ("/") hat gar keine Depends(get_session)-Abhaengigkeit, und ein
mehrsegmentiger Pfad wie unten passt zu keiner Route (auch nicht zu
/{slug}) und wird schon von Starlettes Router mit 404 beantwortet, bevor
irgendeine Abhaengigkeit aufgeloest wird - siehe der Kommentar bei
_404_als_deutsche_seite in app/main.py. Ein eigener, unabhaengiger
TestClient je Test haelt das so und laesst beide Tests auch ohne laufende
Datenbank durchlaufen statt sie stillschweigend zu uebergehen.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_lernseite_traegt_eine_strenge_richtlinie():
    kopf = TestClient(app).get("/").headers.get("content-security-policy", "")
    assert "default-src 'none'" in kopf
    assert "script-src 'self'" in kopf
    assert "style-src 'self'" in kopf
    assert "unsafe-inline" not in kopf
    assert "unsafe-eval" not in kopf


def test_weitere_schutzkoepfe_sind_gesetzt():
    koepfe = TestClient(app).get("/ein-pfad/mit-mehreren/segmenten").headers
    assert koepfe.get("x-content-type-options") == "nosniff"
    assert koepfe.get("referrer-policy") == "no-referrer"
