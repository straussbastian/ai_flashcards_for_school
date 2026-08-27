# Die Lernseite – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unter der Drei-Wort-Adresse liefert der Server eine Lernseite aus, die sich genau so verhält wie der abgenommene Prototyp – mit echten Daten aus der Datenbank statt fest eingebauten Beispielkarten.

**Architecture:** `GET /{slug}` holt das Bundle samt Karten, rendert das Markdown serverseitig zu gesäubertem HTML und legt das Ergebnis als JSON in die Seite. Ein Runner im Browser übernimmt danach alles Weitere – Mischen, Umklappen, Punktestand, Ergebnis – ohne eine weitere Serveranfrage. Damit ist „es wird nichts gespeichert" technisch erzwungen und nicht nur versprochen. Der Runner ist kein Neubau: Sein Verhalten steckt bereits vollständig in `docs/design/prototyp.html`.

**Voraussetzung:** Plan 1 ist abgeschlossen und gepusht. Datenmodell, Markdown-Säuberung, Container und CI stehen; 82 Tests sind grün.

**Nicht Teil dieses Plans:** Der MCP-Server samt OAuth (Plan 2). Gefüllt wird die Datenbank in diesem Plan per SQL.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy 2 (async), vanilla JavaScript ohne Build-Schritt, pytest, Playwright.

**Spec:** [docs/superpowers/specs/2026-08-27-flashcards-design.md](../specs/2026-08-27-flashcards-design.md)
**Verbindliche Verhaltensreferenz:** [docs/design/prototyp.html](../../design/prototyp.html)

## Global Constraints

- Python 3.13, PostgreSQL 17. Alle Bezeichner, Kommentare, Docstrings und Meldungen auf **Deutsch**; etablierte Fachbegriffe ausgenommen.
- **Keine Cookies, kein LocalStorage, keine SessionStorage.** Neu laden heißt neu anfangen. Das gilt ausnahmslos.
- **Nach dem ersten Seitenaufruf gibt es keine weitere Serveranfrage.** Kein Nachladen von Karten, kein Melden von Ergebnissen.
- Der Prototyp ist die verbindliche Referenz: Wo die Umsetzung sich anders verhält, ist die Umsetzung falsch — es sei denn, jemand entscheidet ausdrücklich anders und hält das fest.
- Farbwerte, Winkel, Schatten und die Dauer der Umklapp-Animation werden **wörtlich** aus dem Prototyp übernommen, nicht neu gewählt.
- Tastaturregel: **Wo zwei Möglichkeiten zur Wahl stehen, sind es immer A und B.** Kürzel stehen sichtbar auf den Knöpfen. Die Tastenleiste zeigt nur, was gerade wirklich geht.
- Nur diese vier Felder enthalten HTML, und dieses HTML kommt **ausschließlich** aus `app.markdown.rendern()`: `vorderseite`, `rueckseite`, `erklaerung`, `beschreibung`. Alles andere — insbesondere die Antworttexte, `titel` und `klasse` — ist Klartext und wird als Klartext eingesetzt.
- Jede Aufgabe endet mit einem Commit, Nachricht deutsch.
- Nach jeder Aufgabe muss die gesamte Suite grün sein, 0 übersprungen, 0 Warnungen.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `app/routen/__init__.py` | Sammelstelle der Router |
| `app/routen/system.py` | `/healthz`, Landeseite |
| `app/routen/lernseite.py` | `GET /{slug}` |
| `app/bundle_json.py` | Aus Bundle und Karten die Auslieferungsform bauen |
| `app/templates/basis.html` | Grundgerüst |
| `app/templates/lernseite.html` | Die Lernseite mit eingebettetem Bundle |
| `app/templates/landeseite.html` | Die schlichte Startseite |
| `app/templates/fehler.html` | 404 und 410 |
| `app/static/lernseite.css` | Die Optik, wörtlich aus dem Prototyp |
| `app/static/runner.js` | Der Ablauf im Browser, wörtlich aus dem Prototyp |
| `app/main.py` | Nur noch App-Erzeugung und Router-Einhängung |
| `tests/test_bundle_json.py` | Auslieferungsform |
| `tests/test_lernseite.py` | Route, 404, 410, leeres Bundle, Einbettung |
| `tests/browser/` | Playwright |

Die Trennung folgt der Verantwortung: `bundle_json.py` ist ohne HTTP testbar und wird später auch vom MCP-Server gebraucht, wenn er eine Vorschau liefern soll.

---

### Task 1: Routen aufteilen und Templates einführen

Reiner Umbau ohne Verhaltensänderung. Er kommt zuerst, weil `app/main.py` sonst mit jeder weiteren Route unübersichtlicher wird und die Aufteilung später ein Eingriff statt eines Handgriffs wäre.

**Files:**
- Create: `app/routen/__init__.py`, `app/routen/system.py`, `app/templates/basis.html`, `app/templates/landeseite.html`
- Modify: `app/main.py`, `pyproject.toml` (Templates ins Paket aufnehmen)
- Test: `tests/test_main.py` (bestehende Tests müssen unverändert grün bleiben)

**Interfaces:**
- Consumes: `app.db.get_session`
- Produces: `app.routen.system.router` (APIRouter mit `/healthz` und `/`), `app.templates` als Jinja2-Umgebung mit `app.templates.rendern(name, **kontext) -> HTMLResponse`

- [ ] **Step 1: Bestehende Tests laufen lassen und Ausgangsstand festhalten**

Run: `set -a; . ./.env; set +a; uv run pytest -q`
Expected: 82 passed. Diese Zahl darf am Ende dieses Tasks weder kleiner noch größer sein — es ist ein Umbau, kein Zuwachs.

- [ ] **Step 2: Jinja2-Umgebung anlegen**

`app/templates/__init__.py`:

```python
"""Jinja2-Umgebung. Eine Stelle, an der HTML entsteht - sonst gibt es zwei Wege."""

from pathlib import Path

from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

VERZEICHNIS = Path(__file__).parent

_umgebung = Jinja2Templates(directory=str(VERZEICHNIS))
# autoescape ist bei Jinja2Templates fuer .html voreingestellt und bleibt an.
# Wo bereits gesaeubertes HTML eingesetzt wird, steht im Template ausdruecklich
# ein `| safe` mit Begruendung - nirgends sonst.


def rendern(request, name: str, status_code: int = 200, **kontext) -> HTMLResponse:
    return _umgebung.TemplateResponse(
        request=request, name=name, context=kontext, status_code=status_code
    )
```

- [ ] **Step 3: Templates schreiben**

`app/templates/basis.html`:

```html
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex, nofollow">
  <title>{% block titel %}Lernkarten{% endblock %}</title>
  {% block kopf %}{% endblock %}
</head>
<body>
{% block inhalt %}{% endblock %}
</body>
</html>
```

`noindex` ist Absicht: Die Adressen sollen über den Link der Lehrkraft gefunden werden, nicht über eine Suchmaschine.

`app/templates/landeseite.html`:

```html
{% extends "basis.html" %}
{% block inhalt %}
<p>Diese Seite wird ueber einen Link aufgerufen, den du von deiner Lehrkraft bekommst.</p>
{% endblock %}
```

- [ ] **Step 4: Router anlegen**

`app/routen/system.py`:

```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.templates import rendern

router = APIRouter()


@router.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.scalar(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "fehler", "datenbank": "nicht erreichbar"}, status_code=503
        )
    return JSONResponse({"status": "ok", "datenbank": "ok"})


@router.get("/", response_class=HTMLResponse)
async def landeseite(request: Request) -> HTMLResponse:
    return rendern(request, "landeseite.html")
```

`app/routen/__init__.py`: leer.

- [ ] **Step 5: `app/main.py` auf das Nötige zurückführen**

```python
from fastapi import FastAPI

from app.routen import system

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

app.include_router(system.router)
```

Die Konstante `LANDESEITE` entfällt.

- [ ] **Step 6: Templates ins Paket aufnehmen**

In `pyproject.toml` sicherstellen, dass `app/templates/*.html` und später `app/static/*` mit ins Wheel wandern. Bei hatchling reicht in der Regel, dass sie unter `app/` liegen — **prüf es**, indem du `uv build` ausführst und in das erzeugte Wheel schaust, statt es anzunehmen. Fehlen die Dateien, greift im Container `TemplateNotFound`, und zwar erst zur Laufzeit.

- [ ] **Step 7: Tests laufen lassen**

Run: `set -a; . ./.env; set +a; uv run pytest -q`
Expected: 82 passed, unverändert. `test_landeseite_verraet_keine_bundles` prüft weiterhin, dass das Wort „bundle" nicht vorkommt.

- [ ] **Step 8: Commit**

```bash
git add app pyproject.toml
git commit -m "Routen aufteilen und Templates einfuehren"
```

---

### Task 2: Die Auslieferungsform des Bundles

**Files:**
- Create: `app/bundle_json.py`
- Test: `tests/test_bundle_json.py`

**Interfaces:**
- Consumes: `app.models.Bundle`, `app.models.Karte`, `app.markdown.rendern`
- Produces: `app.bundle_json.bauen(bundle: Bundle) -> dict`

Diese Funktion ist der einzige Ort, an dem entschieden wird, was der Browser zu sehen bekommt. Sie ist ohne HTTP testbar.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`tests/test_bundle_json.py`:

```python
import pytest

from app.bundle_json import bauen
from app.models import Bundle, Karte


def _bundle(**abweichungen) -> Bundle:
    werte = dict(slug="kluge-tafel-leuchtet", titel="Arbeitsrecht kompakt",
                 beschreibung=None, klasse=None, selbsteinschaetzung=True,
                 reihenfolge="zufall")
    werte.update(abweichungen)
    bundle = Bundle(**werte)
    bundle.karten = []
    return bundle


def _flashcard(position: int, vorn: str, hinten: str) -> Karte:
    return Karte(position=position, art="flashcard", vorderseite=vorn, rueckseite=hinten)


def _frage(position: int, frage: str, antworten: list[str], index: int,
           erklaerung: str | None = None) -> Karte:
    return Karte(position=position, art="frage", vorderseite=frage,
                 antworten=antworten, richtige_index=index, erklaerung=erklaerung)


def test_kopfdaten_wandern_unveraendert_durch():
    bundle = _bundle(klasse="FS 23b")
    ergebnis = bauen(bundle)
    assert ergebnis["titel"] == "Arbeitsrecht kompakt"
    assert ergebnis["klasse"] == "FS 23b"
    assert ergebnis["selbsteinschaetzung"] is True
    assert ergebnis["reihenfolge"] == "zufall"


def test_markdown_wird_zu_html_gerendert():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "Das ist **wichtig**", "Antwort")]
    karte = bauen(bundle)["karten"][0]
    assert "<strong>wichtig</strong>" in karte["vorderseite"]


def test_antworttexte_bleiben_klartext():
    bundle = _bundle()
    bundle.karten = [_frage(1, "Frage", ["**nicht fett**", "zwei"], 0)]
    karte = bauen(bundle)["karten"][0]
    assert karte["antworten"] == ["**nicht fett**", "zwei"]


def test_skript_in_einer_karte_wird_entfernt():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "Hallo <script>alert(1)</script>", "Antwort")]
    karte = bauen(bundle)["karten"][0]
    assert "script" not in karte["vorderseite"].lower()


def test_karten_kommen_in_position_sreihenfolge():
    bundle = _bundle()
    bundle.karten = [_flashcard(2, "zwei", "b"), _flashcard(1, "eins", "a")]
    reihenfolge = [k["vorderseite"] for k in bauen(bundle)["karten"]]
    assert "eins" in reihenfolge[0]
    assert "zwei" in reihenfolge[1]


def test_zusammensetzung_wird_gezaehlt():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "a", "b"), _frage(2, "c", ["d", "e"], 0)]
    ergebnis = bauen(bundle)
    assert ergebnis["anzahl"] == {"gesamt": 2, "flashcards": 1, "fragen": 1}


def test_flashcard_traegt_keine_antwortfelder():
    bundle = _bundle()
    bundle.karten = [_flashcard(1, "a", "b")]
    karte = bauen(bundle)["karten"][0]
    assert "antworten" not in karte
    assert "richtige_index" not in karte


def test_leere_erklaerung_wird_weggelassen():
    bundle = _bundle()
    bundle.karten = [_frage(1, "Frage", ["a", "b"], 0, erklaerung=None)]
    assert "erklaerung" not in bauen(bundle)["karten"][0]
```

- [ ] **Step 2: Tests laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_bundle_json.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.bundle_json'`

- [ ] **Step 3: Umsetzung**

`app/bundle_json.py`:

```python
"""Aus Bundle und Karten die Form bauen, die der Browser bekommt.

Der einzige Ort, an dem entschieden wird, was ausgeliefert wird. Wichtig
dabei: Nur `vorderseite`, `rueckseite`, `erklaerung` und `beschreibung`
enthalten HTML, und dieses HTML kommt ausschliesslich aus `rendern()`.
Antworttexte, Titel und Klasse bleiben Klartext - der Browser setzt sie
als Text ein, nicht als HTML.
"""

from app.markdown import rendern
from app.models import Bundle, Karte


def _karte(karte: Karte) -> dict:
    daten: dict = {"art": karte.art, "vorderseite": rendern(karte.vorderseite)}
    if karte.art == "flashcard":
        daten["rueckseite"] = rendern(karte.rueckseite)
        return daten
    daten["antworten"] = list(karte.antworten or [])
    daten["richtige_index"] = karte.richtige_index
    erklaerung = rendern(karte.erklaerung)
    if erklaerung:
        daten["erklaerung"] = erklaerung
    return daten


def bauen(bundle: Bundle) -> dict:
    karten = sorted(bundle.karten, key=lambda k: k.position)
    flashcards = sum(1 for k in karten if k.art == "flashcard")
    return {
        "titel": bundle.titel,
        "beschreibung": rendern(bundle.beschreibung),
        "klasse": bundle.klasse,
        "selbsteinschaetzung": bundle.selbsteinschaetzung,
        "reihenfolge": bundle.reihenfolge,
        "anzahl": {
            "gesamt": len(karten),
            "flashcards": flashcards,
            "fragen": len(karten) - flashcards,
        },
        "karten": [_karte(k) for k in karten],
    }
```

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_bundle_json.py -v`
Expected: 8 passed

- [ ] **Step 5: Gesamte Suite**

Run: `set -a; . ./.env; set +a; uv run pytest -q`
Expected: 90 passed

- [ ] **Step 6: Commit**

```bash
git add app/bundle_json.py tests/test_bundle_json.py
git commit -m "Auslieferungsform des Bundles"
```

---

### Task 3: Die Route unter der Drei-Wort-Adresse

**Files:**
- Create: `app/routen/lernseite.py`, `app/templates/lernseite.html`, `app/templates/fehler.html`
- Modify: `app/main.py`
- Test: `tests/test_lernseite.py`

**Interfaces:**
- Consumes: `app.bundle_json.bauen`, `app.models.Bundle`, `app.db.get_session`, `app.templates.rendern`
- Produces: `app.routen.lernseite.router` mit `GET /{slug}`

**Zwei Dinge, die hier leicht schiefgehen und teuer sind:**

Die Route ist ein Muster, kein Auffangbecken. Ohne Muster schluckt `/{slug}` auch `/healthz`, `/mcp`, `/.well-known/*` und `/static/*` — je nach Reihenfolge der Registrierung. Das Muster ist dasselbe, das `tests/test_slug.py` erzwingt: drei Kleinbuchstabenwörter, bindestrichgetrennt. Damit beantwortet `/favicon.ico` sich selbst mit 404, ohne die Datenbank zu fragen.

Der Router wird **als letzter** eingehängt. Beides zusammen, nicht eines davon.

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`tests/test_lernseite.py`:

```python
import pytest

from app.models import Bundle, Karte


async def _bundle_anlegen(session, slug="kluge-tafel-leuchtet", aktiv=True, mit_karten=True):
    bundle = Bundle(slug=slug, titel="Arbeitsrecht kompakt", aktiv=aktiv,
                    klasse="FS 23b", beschreibung="Erst lernen, dann fragen.")
    session.add(bundle)
    await session.flush()
    if mit_karten:
        session.add(Karte(bundle_id=bundle.id, position=1, art="flashcard",
                          vorderseite="Probezeit?", rueckseite="Sechs Monate"))
        session.add(Karte(bundle_id=bundle.id, position=2, art="frage",
                          vorderseite="Ruhezeit?", antworten=["neun", "elf"],
                          richtige_index=1))
        await session.flush()
    return bundle


async def test_bundle_wird_ausgeliefert(client, session):
    await _bundle_anlegen(session)
    antwort = client.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200
    assert "Arbeitsrecht kompakt" in antwort.text


async def test_das_bundle_steckt_als_json_in_der_seite(client, session):
    await _bundle_anlegen(session)
    antwort = client.get("/kluge-tafel-leuchtet")
    assert 'id="bundle-daten"' in antwort.text
    assert '"art": "flashcard"' in antwort.text or '"art":"flashcard"' in antwort.text


async def test_unbekannte_adresse_ergibt_404(client, session):
    antwort = client.get("/gibt-es-nicht")
    assert antwort.status_code == 404
    assert "kluge" not in antwort.text.lower()   # verraet keine anderen Adressen


async def test_inaktives_bundle_ergibt_410(client, session):
    await _bundle_anlegen(session, aktiv=False)
    antwort = client.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 410
    assert "nicht mehr aktiv" in antwort.text


async def test_bundle_ohne_karten_erklaert_sich(client, session):
    await _bundle_anlegen(session, mit_karten=False)
    antwort = client.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200
    assert "noch keine Karten" in antwort.text


@pytest.mark.parametrize("pfad", ["/favicon.ico", "/healthz2", "/zwei-woerter", "/GROSS-und-klein-hier"])
async def test_was_nicht_wie_eine_adresse_aussieht_wird_nicht_gesucht(client, session, pfad):
    antwort = client.get(pfad)
    assert antwort.status_code == 404


async def test_healthz_bleibt_erreichbar(client, session):
    assert client.get("/healthz").status_code == 200


async def test_skript_ende_in_einer_karte_zerlegt_die_seite_nicht(client, session):
    bundle = await _bundle_anlegen(session, mit_karten=False)
    session.add(Karte(bundle_id=bundle.id, position=1, art="flashcard",
                      vorderseite="Vorsicht </script><script>alert(1)</script>",
                      rueckseite="Antwort"))
    await session.flush()
    antwort = client.get("/kluge-tafel-leuchtet")
    assert antwort.status_code == 200
    assert "</script><script>" not in antwort.text
```

Der letzte Test ist der wichtigste dieses Tasks. Enthält eine Karte die Zeichenfolge `</script>`, beendet sie beim naiven Einbetten den Datenblock und alles danach wird als Skript ausgeführt. Die Markdown-Säuberung fängt das **nicht** ab, weil sie nur den Inhalt säubert, nicht die Art der Einbettung.

- [ ] **Step 2: Tests laufen lassen und Fehlschlag bestätigen**

Run: `set -a; . ./.env; set +a; uv run pytest tests/test_lernseite.py -v`
Expected: FAIL — es gibt weder Route noch Template

- [ ] **Step 3: Die Route schreiben**

`app/routen/lernseite.py`:

```python
import json
import re

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bundle_json import bauen
from app.db import get_session
from app.models import Bundle
from app.templates import rendern

router = APIRouter()

# Dasselbe Muster, das app/slug.py erzeugt und tests/test_slug.py erzwingt.
# Ohne dieses Muster wuerde die Route auch /favicon.ico und alles andere
# schlucken und fuer jeden Unsinn die Datenbank fragen.
ADRESSE = r"^[a-z]+-[a-z]+-[a-z]+$"


def _einbetten(daten: dict) -> str:
    """JSON so einbetten, dass eine Karte den Datenblock nicht beenden kann.

    Enthaelt ein Karteninhalt die Zeichenfolge `</script>`, wuerde sie beim
    naiven Einbetten den Block beenden und alles danach wuerde als Skript
    ausgefuehrt. Das faengt die Markdown-Saeuberung nicht ab, weil sie den
    Inhalt saeubert und nicht die Art der Einbettung.
    """
    roh = json.dumps(daten, ensure_ascii=False)
    return roh.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


@router.get("/{slug}", response_class=HTMLResponse)
async def lernseite(
    request: Request,
    slug: str = Path(pattern=ADRESSE),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    bundle = await session.scalar(select(Bundle).where(Bundle.slug == slug))

    if bundle is None:
        return rendern(request, "fehler.html", status_code=404,
                       ueberschrift="Diese Lernseite gibt es nicht",
                       text="Pruef den Link, den du bekommen hast.")

    if not bundle.aktiv:
        return rendern(request, "fehler.html", status_code=410,
                       ueberschrift="Diese Lernseite ist nicht mehr aktiv",
                       text="Deine Lehrkraft hat sie stillgelegt.")

    daten = bauen(bundle)
    return rendern(request, "lernseite.html", bundle=daten, daten=_einbetten(daten))
```

`Path(pattern=...)` sorgt dafür, dass eine nicht passende Adresse mit 404 beantwortet wird, ohne dass die Datenbank überhaupt gefragt wird.

- [ ] **Step 4: Templates schreiben**

`app/templates/fehler.html`:

```html
{% extends "basis.html" %}
{% block titel %}{{ ueberschrift }}{% endblock %}
{% block kopf %}<link rel="stylesheet" href="/static/lernseite.css">{% endblock %}
{% block inhalt %}
<div class="buehne">
  <main class="mitte">
    <div class="stapel">
      <div class="karte"><div class="karte-innen">
        <div class="seite">
          <h1 class="titel">{{ ueberschrift }}</h1>
          <p class="beschreibung">{{ text }}</p>
        </div>
      </div></div>
    </div>
  </main>
</div>
{% endblock %}
```

`app/templates/lernseite.html` — das Grundgerüst, das der Runner füllt:

```html
{% extends "basis.html" %}
{% block titel %}{{ bundle.titel }}{% endblock %}
{% block kopf %}<link rel="stylesheet" href="/static/lernseite.css">{% endblock %}
{% block inhalt %}
<div class="buehne">
  <header class="kopf" id="kopf" hidden>
    <div class="kopf-zeile">
      <span id="fortschritt-text"></span>
      <button class="beenden" id="beenden-knopf" type="button">beenden &#10005;</button>
    </div>
    <div class="balken"><span id="fortschritt-balken"></span></div>
  </header>

  <main class="mitte">
    <div class="stapel">
      <div class="geist geist-1" id="geist-1" hidden></div>
      <div class="geist geist-2" id="geist-2" hidden></div>
      <div class="karte" id="karte" tabindex="-1"><div class="karte-innen" id="karte-innen"></div></div>
    </div>
  </main>

  <p class="nur-fuer-screenreader" role="status" aria-live="polite" id="ansage"></p>

  <footer class="fuss" id="fuss" hidden>
    <button class="navi" id="zurueck" type="button">&#8592; zur&uuml;ck</button>
    <button class="navi" id="weiter" type="button">weiter &#8594;</button>
  </footer>

  <p class="tastenleiste" id="tastenleiste"></p>
  <p class="fussnote">Es wird nichts gespeichert: Neu laden hei&szlig;t neu anfangen.</p>
</div>

<script type="application/json" id="bundle-daten">{{ daten | safe }}</script>
<script src="/static/runner.js"></script>
{% endblock %}
```

Das `| safe` steht hier bewusst und ist die einzige Stelle im Projekt: `daten` ist bereits JSON, in dem `<`, `>` und `&` zu Unicode-Fluchtsequenzen geworden sind. Jinjas Autoescape würde daraus `&lt;` machen und das JSON unlesbar. Schreib genau diese Begründung als Kommentar ins Template.

- [ ] **Step 5: Router einhängen — als letzten**

In `app/main.py`:

```python
from app.routen import lernseite, system

app.include_router(system.router)
# Muss als letzter kommen: /{slug} ist zwar durch ein Muster begrenzt, aber
# eine spaetere Route mit gleicher Form wuerde sonst verdeckt.
app.include_router(lernseite.router)
```

- [ ] **Step 6: Statisches Verzeichnis einhängen**

```python
from fastapi.staticfiles import StaticFiles
from app.templates import VERZEICHNIS

app.mount("/static", StaticFiles(directory=str(VERZEICHNIS.parent / "static")), name="static")
```

Vor dem Lernseiten-Router. Lege `app/static/` mit einer vorläufig leeren `lernseite.css` und `runner.js` an, damit die Tests dieses Tasks nicht an fehlenden Dateien scheitern.

- [ ] **Step 7: Tests laufen lassen**

Run: `set -a; . ./.env; set +a; uv run pytest -q`
Expected: alle grün. Prüf besonders `test_skript_ende_in_einer_karte_zerlegt_die_seite_nicht`.

- [ ] **Step 8: Von Hand ansehen**

```bash
uv run uvicorn app.main:app --reload
```

Dann `http://localhost:8000/kluge-tafel-leuchtet` aufrufen — das Bundle aus Plan 1 liegt in der Entwicklungsdatenbank, sofern sie noch existiert. Falls nicht, leg es per SQL an. Erwartet: Die Seite lädt, der Datenblock steht im Quelltext, sichtbar ist noch fast nichts — der Runner kommt in Task 5.

- [ ] **Step 9: Commit**

```bash
git add app tests/test_lernseite.py
git commit -m "Lernseite unter der Drei-Wort-Adresse ausliefern"
```

---

### Task 4: Inhaltssicherheitsrichtlinie

**Files:**
- Create: `app/sicherheit.py`
- Modify: `app/main.py`
- Test: `tests/test_sicherheit.py`

Die Markdown-Säuberung ist bisher die einzige Verteidigungslinie für Inhalte, die später über MCP hereinkommen. Eine Richtlinie im Antwortkopf ist die zweite, und sie ist hier ungewöhnlich billig: Die Seite braucht keine fremden Skripte, keine Bilder, keine externen Schriften.

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/test_sicherheit.py`:

```python
def test_lernseite_traegt_eine_strenge_richtlinie(client, session):
    kopf = client.get("/healthz").headers.get("content-security-policy", "")
    assert "default-src 'none'" in kopf
    assert "script-src 'self'" in kopf
    assert "style-src 'self'" in kopf
    assert "unsafe-inline" not in kopf
    assert "unsafe-eval" not in kopf


def test_weitere_schutzkoepfe_sind_gesetzt(client, session):
    koepfe = client.get("/healthz").headers
    assert koepfe.get("x-content-type-options") == "nosniff"
    assert koepfe.get("referrer-policy") == "no-referrer"
```

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `set -a; . ./.env; set +a; uv run pytest tests/test_sicherheit.py -v`
Expected: FAIL — die Köpfe fehlen

- [ ] **Step 3: Umsetzung**

`app/sicherheit.py`:

```python
"""Schutzkoepfe fuer alle Antworten.

Die Markdown-Saeuberung ist die erste Verteidigungslinie fuer Inhalte, die
ueber MCP hereinkommen. Diese Richtlinie ist die zweite - und hier besonders
billig, weil die Seite nichts Fremdes braucht: keine externen Skripte, keine
Bilder, keine Webfonts (die Spec legt system-ui fest).
"""

from starlette.middleware.base import BaseHTTPMiddleware

RICHTLINIE = "; ".join([
    "default-src 'none'",
    "script-src 'self'",
    "style-src 'self'",
    "connect-src 'none'",   # der Runner spricht nach dem Laden mit niemandem
    "img-src 'none'",
    "font-src 'none'",
    "form-action 'none'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
])


class Schutzkoepfe(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        antwort = await call_next(request)
        antwort.headers["Content-Security-Policy"] = RICHTLINIE
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        return antwort
```

In `app/main.py`: `app.add_middleware(Schutzkoepfe)`.

`connect-src 'none'` ist die technische Durchsetzung des Versprechens, dass nach dem ersten Aufruf keine Serveranfrage mehr stattfindet. Wer den Runner später erweitert und heimlich etwas nachladen will, scheitert an der Richtlinie statt unbemerkt durchzukommen.

- [ ] **Step 4: Tests laufen lassen**

Run: `set -a; . ./.env; set +a; uv run pytest -q`
Expected: alle grün

- [ ] **Step 5: Commit**

```bash
git add app/sicherheit.py app/main.py tests/test_sicherheit.py
git commit -m "Inhaltssicherheitsrichtlinie und Schutzkoepfe"
```

---

### Task 5: Der Runner

**Files:**
- Modify: `app/static/lernseite.css`, `app/static/runner.js`
- Test: von Hand plus Task 6

Dies ist **kein Neubau.** Verhalten und Optik stecken vollständig in `docs/design/prototyp.html`, das vom Auftraggeber am Handy und am Rechner durchgespielt und abgenommen wurde. Die Aufgabe ist, den Prototyp in zwei Dateien zu zerlegen und an die echten Daten zu hängen.

- [ ] **Step 1: Den Prototyp lesen**

Lies `docs/design/prototyp.html` vollständig, bevor du irgendetwas schreibst. Er ist die verbindliche Referenz.

- [ ] **Step 2: CSS übernehmen**

Der `<style>`-Block wandert unverändert nach `app/static/lernseite.css`. **Ändere keine Farbwerte, keine Winkel, keine Zeiten.** Ergänze nur, was für die Fehlerseiten gebraucht wird.

- [ ] **Step 3: JavaScript übernehmen und an die Daten hängen**

Der `<script>`-Block wandert nach `app/static/runner.js`, mit genau zwei Änderungen:

Erstens ersetzt das eingebettete JSON die fest eingebaute Konstante:

```javascript
const BUNDLE = JSON.parse(document.getElementById("bundle-daten").textContent);
```

Zweitens werden die vier HTML-Felder als HTML eingesetzt statt als Text. Im Prototyp steht überall `textContent`, weil er kein Markdown rendert. Hier gilt:

- `vorderseite`, `rueckseite`, `erklaerung`, `beschreibung` → `innerHTML`
- **alles andere**, insbesondere `antworten[]`, `titel` und `klasse` → weiterhin `textContent`

Schreib an jede dieser Stellen einen Kommentar, der festhält: Dieses HTML kommt ausschließlich aus `app.markdown.rendern()` und ist dort gesäubert worden; alles, was nicht durch `rendern()` gelaufen ist, wird niemals als HTML eingesetzt.

Der Prototyp enthält an genau diesen Stellen bereits Kommentare, die darauf hinweisen — sie wurden dort hinterlassen, damit dieser Schritt nicht übersehen wird.

- [ ] **Step 4: Reihenfolge berücksichtigen**

Der Prototyp mischt immer. Das Bundle trägt jetzt ein Feld `reihenfolge`: Bei `fest` bleibt die Kartenreihenfolge, wie sie aus der Datenbank kommt; die **Antworten werden trotzdem gemischt.** Das steht so in der Spec.

- [ ] **Step 5: Leeres Bundle abfangen**

Hat ein Bundle keine Karten, zeigt die Startseite den Hinweis aus Task 3 und **keinen** Start-Knopf.

- [ ] **Step 6: Von Hand durchspielen**

Server starten, `/kluge-tafel-leuchtet` aufrufen und den **kompletten Ablauf ohne Maus** durchgehen: starten, umdrehen, einschätzen, Fragen beantworten, blättern, Ergebnis, „Nur die Fehler". Dann dasselbe am schmalen Fenster.

Vergleich mit dem Prototypen, nebeneinander im Browser. Jede Abweichung ist ein Fehler in der Umsetzung, nicht im Prototyp.

- [ ] **Step 7: Commit**

```bash
git add app/static
git commit -m "Runner aus dem Prototyp an echte Daten haengen"
```

---

### Task 6: Browsertests

**Files:**
- Create: `tests/browser/conftest.py`, `tests/browser/test_ablauf.py`
- Modify: `pyproject.toml` (Playwright als Dev-Abhängigkeit)
- Test: sich selbst

**Interfaces:**
- Consumes: die laufende Anwendung
- Produces: Fixtures `seite` (Playwright-Page gegen einen Testserver mit vorbereitetem Bundle)

- [ ] **Step 1: Playwright einrichten**

`uv add --dev playwright pytest-playwright`, dann `uv run playwright install chromium`.

In der CI kommt ein Schritt dazu, der `playwright install --with-deps chromium` ausführt. **Ergänze ihn im Workflow**, sonst ist die CI ab diesem Task rot.

- [ ] **Step 2: Fixtures schreiben**

`tests/browser/conftest.py`: startet uvicorn in einem Unterprozess gegen die Testdatenbank, legt ein Bundle mit bekanntem Inhalt an, gibt die Adresse zurück und räumt danach auf. Warte auf `/healthz`, statt blind zu schlafen. Setz eine Zeitgrenze auf jeden Unterprozessaufruf.

Das Bundle soll bewusst klein und vorhersagbar sein: zwei Flashcards und zwei Fragen mit bekannten richtigen Antworten. Große Bundles machen Tests langsam und die Fehlersuche schwer.

- [ ] **Step 3: Die Tests schreiben**

`tests/browser/test_ablauf.py` — jeder Test prüft echtes Verhalten, keine Attrappen:

```python
def test_startseite_zeigt_titel_und_zusammensetzung(seite): ...
def test_flashcard_dreht_sich_und_zeigt_die_rueckseite(seite): ...
def test_selbsteinschaetzung_per_tastatur(seite): ...
def test_richtige_antwort_wird_gruen(seite): ...
def test_falsche_antwort_zeigt_die_loesung(seite): ...
def test_punktestand_am_ende_stimmt(seite): ...
def test_nur_die_fehler_enthaelt_genau_die_falschen(seite): ...
def test_zurueckblaettern_behaelt_das_ergebnis(seite): ...
def test_kompletter_durchlauf_nur_mit_tastatur(seite): ...
def test_neu_laden_setzt_alles_zurueck(seite): ...
def test_markdown_wird_als_html_dargestellt(seite): ...
def test_am_handy_gibt_es_keine_seitliche_scrollleiste(seite): ...
```

Zwei davon sind die wichtigsten und dürfen nicht weggelassen werden:

`test_kompletter_durchlauf_nur_mit_tastatur` geht vom Start bis zum Ergebnis, ohne einen einzigen Klick — das war ausdrückliches Feedback des Auftraggebers und ist die Regel, an der die Bedienung hängt.

`test_neu_laden_setzt_alles_zurueck` beweist die Zusage, dass nichts gespeichert wird. Prüf zusätzlich, dass `document.cookie` leer ist und `localStorage` sowie `sessionStorage` keine Einträge haben.

- [ ] **Step 4: Tests laufen lassen**

Run: `set -a; . ./.env; set +a; uv run pytest tests/browser -v`
Expected: alle grün

- [ ] **Step 5: Gesamte Suite und CI-Workflow prüfen**

Run: `set -a; . ./.env; set +a; uv run pytest -q`

Prüf, dass der Workflow den Playwright-Schritt enthält, bevor du committest.

- [ ] **Step 6: Commit**

```bash
git add tests/browser pyproject.toml uv.lock .github
git commit -m "Browsertests fuer den Ablauf der Lernseite"
```

---

### Task 7: Abgleich gegen die Entwürfe

**Files:**
- Create: `tests/browser/test_optik.py`, `docs/design/screenshots/`
- Test: sich selbst

Die Spec legt fest, wie verhindert wird, dass das Ergebnis anders aussieht als der Entwurf. Dieser Task löst das ein.

- [ ] **Step 1: Screenshots erzeugen**

Ein Test, der die Lernseite in drei Breiten aufnimmt — 390, 820 und 1440 Pixel — und zwar je einmal die Startseite, eine Flashcard-Vorderseite, eine aufgedeckte Frage und die Ergebnisseite. Ablage unter `docs/design/screenshots/`.

Die Bilder gehören ins Git: Sie sind der Nachweis, wie es zum Zeitpunkt der Abnahme aussah.

- [ ] **Step 2: Nebeneinanderlegen**

Erzeuge eine schlichte HTML-Seite `docs/design/abgleich.html`, die je Ansicht den Screenshot neben den passenden Ausschnitt aus `docs/design/mockups/` stellt. Kein Werkzeug, keine Bibliothek — zwei Bilder nebeneinander genügen.

- [ ] **Step 3: Abnahme**

Leg die Seite dem Auftraggeber vor. **Erst wenn er zustimmt, gilt die Optik als umgesetzt.** Das ist der letzte Schritt dieses Plans; halte an dieser Stelle an und frag, statt weiterzulaufen.

- [ ] **Step 4: Commit**

```bash
git add docs/design tests/browser/test_optik.py
git commit -m "Screenshots und Abgleich gegen die Entwuerfe"
```

---

## Selbstprüfung des Plans

**Abdeckung der Spec:** Abschnitt 6 (Auslieferung, Zustände des Runners, Interaktion, Tastaturregeln, Optik, Responsiv, Barrierefreiheit) liegt in den Tasks 3, 5, 6 und 7. Abschnitt 7 (404, 410, leeres Bundle) in Task 3. Die Testzusagen aus Abschnitt 8 in den Tasks 2, 3, 6 und 7. Die Markdown-Verarbeitung aus Abschnitt 6 in Task 2, ihre Absicherung in Task 4.

**Bewusst nicht in diesem Plan:** Der MCP-Server samt OAuth (Abschnitt 5 der Spec) — das ist Plan 2. Gefüllt wird die Datenbank hier per SQL.

**Namensgleichheit geprüft:** `bauen`, `rendern`, `get_session`, `Bundle`, `Karte`, `ADRESSE`, `Schutzkoepfe`, `bundle-daten` werden in allen Tasks identisch geschrieben. Die Felder der Auslieferungsform (`titel`, `beschreibung`, `klasse`, `selbsteinschaetzung`, `reihenfolge`, `anzahl`, `karten`, `art`, `vorderseite`, `rueckseite`, `antworten`, `richtige_index`, `erklaerung`) stimmen zwischen Task 2, Task 3 und Task 5 überein.

**Zwei Stellen, die beim Bau leicht übersehen werden** und deshalb hier ausdrücklich stehen: Der Lernseiten-Router wird **als letzter** eingehängt und trägt ein Muster; und das eingebettete JSON wird so entschärft, dass eine Karte mit der Zeichenfolge `</script>` den Datenblock nicht beenden kann. Für beides gibt es einen Test.
