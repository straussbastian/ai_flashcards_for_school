"""Tests fuer die Schutzkoepfe aus app/sicherheit.py.

Bewusst kein Client aus tests/conftest.py: Die dortige "client"-Fixture
haengt ueber datenbank_override an einer echten Testdatenbank. Die Richtlinie
soll aber gerade an der schutzbeduerftigen Seite selbst geprueft werden - der
Lernseite (GET /{slug}), die den JSON-Datenblock mit MCP-Inhalten und das
Skript des Runners ausliefert - und die braucht Depends(get_session). Statt
einer echten Datenbank bekommt get_session hier einen direkten Override
(dasselbe Muster wie test_healthz_meldet_503_wenn_die_datenbank_nicht_antwortet
in tests/test_main.py): ein Session-Ersatz, der ein fertiges, nie
gespeichertes Bundle zurueckgibt statt eine echte Abfrage zu stellen. Ein
mehrsegmentiger Pfad wie unten passt dagegen zu gar keiner Route (auch nicht
zu /{slug}) und wird schon von Starlettes Router mit 404 beantwortet, bevor
irgendeine Abhaengigkeit aufgeloest wird - siehe der Kommentar bei
_404_als_deutsche_seite in app/main.py; der braucht deshalb keinen Override.
So laufen alle Tests hier auch ohne laufende Datenbank durch, nur die
Gegenprobe auf /healthz (die echte Datenbank braucht) bekommt bewusst die
"client"-Fixture.
"""

from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app
from app.models import Bundle


class _MitVorbereitetemBundle:
    """Session-Ersatz, der jede Abfrage mit einem fertigen Bundle beantwortet.

    Erspart eine echte Datenbank: Die Lernseite fragt genau einmal
    session.scalar(...) nach dem Bundle zum Slug - dieses Objekt liefert es
    direkt zurueck, ohne dass je eine Verbindung aufgebaut wird.
    """

    def __init__(self, bundle: Bundle) -> None:
        self._bundle = bundle

    async def scalar(self, *args, **kwargs):
        return self._bundle


def _lernseite_bundle() -> Bundle:
    """Ein minimales, aktives Bundle - nie an eine Session gehaengt."""
    return Bundle(
        slug="kluge-tafel-leuchtet",
        titel="Testbundle",
        aktiv=True,
        selbsteinschaetzung=True,
        reihenfolge="zufall",
    )


def test_lernseite_traegt_eine_strenge_richtlinie():
    app.dependency_overrides[get_session] = lambda: _MitVorbereitetemBundle(
        _lernseite_bundle()
    )
    try:
        antwort = TestClient(app).get("/kluge-tafel-leuchtet")
    finally:
        del app.dependency_overrides[get_session]

    assert antwort.status_code == 200
    kopf = antwort.headers.get("content-security-policy", "")
    assert "default-src 'none'" in kopf
    assert "script-src 'self'" in kopf
    assert "style-src 'self'" in kopf
    assert "unsafe-inline" not in kopf
    assert "unsafe-eval" not in kopf


def test_weitere_schutzkoepfe_sind_gesetzt():
    koepfe = TestClient(app).get("/ein-pfad/mit-mehreren/segmenten").headers
    assert koepfe.get("x-content-type-options") == "nosniff"
    assert koepfe.get("referrer-policy") == "no-referrer"


def test_schutzkoepfe_gelten_auch_fuer_eine_statikdatei():
    # Die Middleware liegt vor dem Routing (app.add_middleware in app/main.py)
    # und muss deshalb wirklich fuer jede Antwort greifen, nicht nur fuer die
    # per Vorlage gerenderten Seiten.
    kopf = TestClient(app).get("/static/lernseite.css").headers.get(
        "content-security-policy", ""
    )
    assert "default-src 'none'" in kopf


def test_schutzkoepfe_gelten_auch_fuer_healthz(client):
    # /healthz braucht eine echte Datenbankabfrage (app/routen/system.py) und
    # bekommt deshalb bewusst die "client"-Fixture statt eines Overrides.
    kopf = client.get("/healthz").headers.get("content-security-policy", "")
    assert "default-src 'none'" in kopf
