# Der MCP-Server – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Lehrerin sagt ihrem Agenten in Claude Cowork „bau mir aus diesem Arbeitsblatt ein Lernpaket" und bekommt einen fertigen Link zurück – über einen MCP-Server, der mit OAuth 2.1 abgesichert ist und acht deutschsprachige Werkzeuge anbietet.

**Architecture:** Ein einziger FastAPI-Prozess trägt drei Dinge: die Lernseiten (steht schon), einen eigenen OAuth-Autorisierungsserver unter `/oauth/*` und den MCP-Endpunkt unter `POST /mcp`. Der MCP-Endpunkt ist eine Starlette-App aus dem offiziellen `mcp`-SDK, die als ASGI-Anwendung an genau zwei Pfaden in die bestehende FastAPI-Anwendung eingehängt wird – nicht per `Mount`, weil ein Mount entweder alle anderen Routen verschluckt oder den Pfad `/mcp` nur mit Schrägstrich am Ende erreichbar macht (beides nachgemessen, siehe Task 8). Das SDK ist ausschließlich **Resource Server**: Es prüft Bearer-Tokens über einen `TokenVerifier` und stellt selbst keine aus. Tokens, Codes und registrierte Clients liegen in PostgreSQL.

**Voraussetzung:** Plan 1 (Fundament, Container, CI) und Plan 2 (Lernseite) sind abgeschlossen. Datenmodell, Markdown-Säuberung, Slug-Erzeugung, Schutzköpfe und CI stehen; 117 Tests sind grün, 0 übersprungen, 0 Warnungen.

**Nicht Teil dieses Plans:** Änderungen am Runner im Browser, an der Optik, an den Playwright-Tests. Kein endgültiges Löschen über MCP (die Spec verbietet es ausdrücklich). Kein Admin-Frontend.

**Tech Stack:** Python 3.13, FastAPI, Starlette, SQLAlchemy 2 (async), Alembic, PostgreSQL 17, das offizielle `mcp`-SDK (Version 2.x), pytest, pytest-asyncio, httpx2.

**Spec:** [docs/superpowers/specs/2026-08-27-flashcards-design.md](../specs/2026-08-27-flashcards-design.md) – Abschnitt 5 ist der Gegenstand, Abschnitt 1 (wer die Nutzerin ist), Abschnitt 4 (Datenmodell) und Abschnitt 10 (Risiken) sind mitzulesen.

---

## Global Constraints

- **Python 3.13, PostgreSQL 17.** Tests laufen gegen echtes PostgreSQL, nie gegen SQLite – die Constraints sind der Kern des Modells.
- **Alles auf Deutsch:** Bezeichner, Kommentare, Docstrings, Meldungen, Commit-Nachrichten. Etablierte Fachbegriffe (OAuth, Token, Slug, Bundle, Migration, Fixture) ausgenommen.
- **Code und Kommentare in ASCII, sichtbarer Text in korrektem Deutsch.** Bezeichner, Kommentare und Commit-Nachrichten bleiben umlautfrei. Alles, was ein Mensch liest – und dazu gehört **jede Fehlermeldung eines Werkzeugs**, weil der Agent sie der Lehrerin vorliest –, wird richtig geschrieben: „über", nicht „ueber".
- **Fehlermeldungen der Werkzeuge sind deutsch und im Klartext.** Sie nennen, *was* falsch ist **und** *was zu tun ist*, nicht nur, dass etwas falsch ist. Die Spec gibt in Abschnitt 5 drei Beispiele vor; jede weitere Meldung folgt derselben Machart.
- **Jede schreibende Antwort enthält den fertigen Link.** Gebaut wird er ausschließlich mit `Settings.bundle_url(slug)`.
- **OAuth-URLs werden ausschließlich aus `BASE_URL` gebaut, nie aus Request-Headern.** Der Container startet uvicorn mit `--forwarded-allow-ips='*'` (siehe `docker/app-start.sh`), weil hinter Coolify ein Reverse Proxy sitzt; `X-Forwarded-Host` und `X-Forwarded-Proto` sind damit fälschbar. Die Spec verlangt, dass das Feld `resource` **exakt** der von der Lehrerin eingetragenen URL entspricht – das darf von keinem Header abhängen. `request.base_url`, `request.url_for()` und `request.headers["host"]` kommen in diesem Plan an keiner Stelle vor.
- **Kein Massen-`update()` auf `karten` oder `bundles`.** `geaendert_am` trägt `onupdate=func.now()` und wird damit **nur vom ORM** gesetzt; ein `update()`-Statement fasst die Spalte nicht an. Geändert wird über ORM-Objekte.
- **Das Anlegen eines Bundles fängt `IntegrityError` auf `uq_bundles_slug` ab und würfelt neu.** `freien_slug_finden()` prüft und schreibt nicht atomar (Spec, Abschnitt 4). Ein Wettlauf ist kein Fehler, den die Lehrerin lesen soll.
- **Längen werden beim Schreiben geprüft, nicht erst beim Ausliefern.** `MAX_LAENGE`/`MarkdownZuLang` aus `app/markdown.py` liefern die Meldung; die Datenbank-Constraints bleiben das Netz darunter, nicht die Fehlerquelle für die Lehrerin.
- **Die nächste Migration heißt `0002`.** Alembic kennt keinen Zähler-Platzhalter; die Nummer entsteht dadurch, dass die Revisions-ID die Nummer **ist**. Anlegen mit `uv run alembic revision --autogenerate --rev-id 0002 -m "..."` (dokumentiert bei `file_template` in `alembic.ini`).
- **`uq_karten_bundle_position` ist `DEFERRABLE INITIALLY DEFERRED`** – Absicht, damit beim Umsortieren mehrere Positionen gleichzeitig wandern können. Ein Test, der einen Verstoß erwartet, muss den Constraint vorher mit `SET CONSTRAINTS uq_karten_bundle_position IMMEDIATE` scharf stellen, sonst prüft er nichts.
- **Keine Geheimnisse in Git oder Image.** Konfiguration über `.env`, dokumentiert in `.env.example`. Dieser Plan braucht **keine neue Umgebungsvariable**: `APP_SECRET`, `TEACHER_PASSWORD` und `BASE_URL` stehen bereits dort.
- **Jede Aufgabe endet mit einem Commit** (Nachricht deutsch, ASCII). **Nach jeder Aufgabe ist die gesamte Suite grün: 0 fehlgeschlagen, 0 übersprungen, 0 Warnungen.**
- Testlauf: `docker compose -f compose.dev.yml up -d`, dann `set -a; . ./.env; set +a`, dann `uv run pytest`.

---

## Was am SDK anders ist, als man es im Kopf hat

**Lies das, bevor du Task 8 anfängst.** Diese Angaben sind gegen die tatsächlich aufgelöste Version `mcp==2.1.1` nachgemessen worden, nicht aus dem Gedächtnis geschrieben.

- Das SDK ist bei **Version 2.x**. `mcp.server.fastmcp` existiert nicht mehr und wirft beim Import einen `ModuleNotFoundError` mit Migrationshinweis. Die Klasse heißt jetzt `MCPServer` und liegt in `mcp.server.mcpserver`.
- `MCPServer.streamable_http_app(...)` liefert eine `starlette.applications.Starlette` mit dem Lifespan `lambda app: session_manager.run()`. **Ein eingehängter Sub-App-Lifespan wird von Starlette nicht ausgeführt.** Die Wirtsanwendung muss `server.session_manager.run()` in ihrem eigenen Lifespan betreten, sonst antwortet jede Anfrage mit `RuntimeError: Task group is not initialized. Make sure to use run().`
- `session_manager.run()` lässt sich **genau einmal pro Instanz** betreten (`_has_started` wird nie zurückgesetzt). Für Tests heißt das: pro Test eine frische Serverinstanz bauen, nicht eine geteilte wiederverwenden.
- Ohne `transport_security` und mit dem Standardwert `host="127.0.0.1"` schaltet das SDK selbsttätig einen DNS-Rebinding-Schutz ein, der ausschließlich `localhost`-Hostnamen akzeptiert und alles andere mit **421** beantwortet. Für einen öffentlich erreichbaren Server muss `transport_security` ausdrücklich übergeben werden.
- Der Anschlusspunkt für OAuth ist `TokenVerifier` – ein Protokoll mit der einen Methode `async def verify_token(self, token: str) -> AccessToken | None`. Wird zusätzlich `auth=AuthSettings(...)` übergeben (ohne `auth_server_provider`), hängt das SDK `RequireAuthMiddleware` vor `/mcp` und liefert bei fehlendem Token den `401` samt `WWW-Authenticate: Bearer ... resource_metadata="..."`. Genau dieser Header ist laut Spec der Auslöser des ganzen Ablaufs.
- Ein per `raise ToolError("...")` gemeldeter Fehler kommt beim Client als `isError: true` mit dem Text `Error executing tool <name>: <deine Meldung>` an. Das englische Präfix stammt aus dem SDK und ist nicht abschaltbar; die deutsche Meldung steht dahinter. Siehe Entscheidung E-7.
- `@mcp_server.custom_route(path, methods)` gibt es weiterhin, wird in diesem Plan aber **nicht** benutzt: Alle unauthentifizierten Endpunkte sind gewöhnliche FastAPI-Routen, damit sie unter denselben Schutzköpfen und demselben 404-Handler laufen wie der Rest der Anwendung.

---

## Dateistruktur

| Datei | Verantwortung |
|---|---|
| `app/sitzung.py` | **Überschreibbare** Datenbank-Sitzungsquelle für alles, was keine FastAPI-Abhängigkeit ist (MCP-Werkzeuge, Token-Prüfer) |
| `app/oauth/__init__.py` | Leer, macht das Paket |
| `app/oauth/modelle.py` | `OAuthClient`, `OAuthCode`, `OAuthToken` |
| `app/oauth/geheimnisse.py` | Zufallsgeheimnisse erzeugen, mit `APP_SECRET` peppern, konstantzeitig vergleichen, PKCE `S256` |
| `app/oauth/speicher.py` | Datenbankarbeit: Client anlegen/lesen, Code ausgeben/einlösen, Tokenpaar ausgeben, Rotation, Familienwiderruf |
| `app/oauth/redirect.py` | Zulässige Redirect-URIs, Loopback-Regel mit ignoriertem Port |
| `app/oauth/metadaten.py` | Die beiden Discovery-Dokumente, gebaut aus `BASE_URL` |
| `app/oauth/pruefer.py` | `TokenPruefer` – die `TokenVerifier`-Umsetzung für das SDK |
| `app/routen/oauth.py` | `/.well-known/*`, `/oauth/register`, `/oauth/authorize`, `/oauth/token` |
| `app/templates/zustimmung.html` | Die Zustimmungsseite mit Passwortfeld |
| `app/static/zustimmung.css` | Ihr Aussehen, in derselben Bildsprache wie die Lernseite |
| `app/mcp/__init__.py` | `mcp_bauen()` – baut `MCPServer` und ASGI-App faul und gecacht |
| `app/mcp/fehler.py` | `MCPFehler` und die Bausteine der deutschen Meldungen |
| `app/mcp/eingaben.py` | Pydantic-Eingabemodelle der Werkzeuge |
| `app/mcp/karten.py` | Kartenprüfung: `richtige_antwort` (Text) → `richtige_index`, Längen, Feldkombinationen |
| `app/mcp/dienste.py` | Die Datenbankarbeit hinter den Werkzeugen |
| `app/mcp/werkzeuge.py` | Die acht Werkzeuge, dünne Hüllen um `dienste.py` |
| `app/sicherheit.py` | (Änderung) Richtlinie je nach Pfad: Formular auf der Zustimmungsseite, keine Richtlinie auf `/mcp` |
| `app/main.py` | (Änderung) Lifespan, MCP-Weiche, OAuth-Router |
| `tests/conftest.py` | (Änderung) Sperre gegen die Entwicklungsdatenbank für MCP, Fixtures `mcp_sitzung`, `mcp_laeuft`, `konfiguration` |
| `migrations/versions/0002_oauth.py` | Die drei OAuth-Tabellen |

Die Trennung folgt der Verantwortung, nicht der Schicht: `karten.py` ist ohne Datenbank testbar, `speicher.py` ohne HTTP, `routen/oauth.py` ohne MCP. Nur `werkzeuge.py` und `main.py` kennen alles.

---

## Entscheidungen, die dieser Plan trifft

Die Spec lässt diese Punkte offen. Sie sind hier entschieden, damit niemand sie beim Bauen neu erfindet. Wer eine umstößt, ändert genau eine Stelle.

- **E-1 – Tokens sind zufällig und liegen gepfeffert in der Datenbank, nicht als JWT.** Die Spec sagt in Abschnitt 5, ausgegebene Tokens liegen in Postgres und überstehen Deployments. Ein JWT läge nicht dort und wäre bis zum Ablauf nicht zurückziehbar. Gespeichert wird nur `hmac_sha256(APP_SECRET, token)`; ein gestohlener Datenbankauszug enthält damit keine benutzbaren Tokens. Kosten falls falsch: eine Datenbankabfrage pro MCP-Anfrage – bei einer Nutzerin ohne Bedeutung.
- **E-2 – Der DNS-Rebinding-Schutz des SDK wird ausdrücklich abgeschaltet.** Er ist gegen Server gedacht, die auf `localhost` lauschen und von einer Webseite aus angreifbar wären. Unserer ist ein öffentlicher HTTPS-Endpunkt, dessen einziger Schutz das Bearer-Token ist, und der `Host`-Header ist hinter Coolifys Proxy ohnehin nicht vertrauenswürdig. Eine Positivliste für `Origin` wäre zudem die wahrscheinlichste Ursache für ein stummes „Couldn't reach the MCP server", das lokal nicht nachstellbar ist. Abgeschaltet wird **ausdrücklich** und mit Test, damit niemand versehentlich in die localhost-Voreinstellung zurückfällt. Kosten falls falsch: gering, ein Feld in einem Aufruf.
- **E-3 – Der `resource`-Parameter (RFC 8707) wird angenommen und mitgespeichert, aber nicht erzwungen.** Es gibt genau eine Resource. Eine Prüfung, die niemals anschlägt, wäre nur eine weitere Stelle, an der der Ablauf stumm scheitern kann. Kosten falls falsch: gering, die Spalte ist da.
- **E-4 – Der Vergleich `richtige_antwort` gegen `antworten` normalisiert mit `.strip()` und `.casefold()`.** Ein Agent, der „zagreb" statt „Zagreb" tippt, soll nicht scheitern. Kommt derselbe normalisierte Text mehrfach vor, ist das ein Fehler – zwei Antwortmöglichkeiten, die sich nur in der Groß-/Kleinschreibung unterscheiden, wären auf der Karte ohnehin verwirrend.
- **E-5 – Beim Löschen einer Karte werden die Positionen nicht neu vergeben.** Die Reihenfolge ergibt sich aus der Sortierung nach `position`; Lücken stören dabei nicht. Damit entfällt jedes Massen-`update()` und die `geaendert_am`-Falle entsteht gar nicht erst. `karten_hinzufuegen` hängt hinten an mit `max(position) + 1`, nicht mit `anzahl`.
- **E-6 – Das Protected-Resource-Dokument wird unter beiden Pfaden ausgeliefert:** `/.well-known/oauth-protected-resource` (so nennt es die Spec in Abschnitt 3) und `/.well-known/oauth-protected-resource/mcp` (so verlangt es RFC 9728 §3.1 für die Resource `BASE_URL/mcp`, und genau diesen Pfad nennt der `WWW-Authenticate`-Header des SDK). Zwei Routen, ein Dokument, eine Funktion.
- **E-7 – Werkzeugfehler werden als `ToolError` geworfen und tragen das englische SDK-Präfix.** Die Alternative wäre, Fehler als erfolgreiche Antwort zurückzugeben – dann wüsste der Agent aber nicht, dass etwas schiefging, und könnte auf einem kaputten Ergebnis weiterbauen. Das Präfix ist Maschinenrauschen vor einem deutschen Satz; der Satz ist, was die Lehrerin hört.
- **E-8 – Die Zustimmungsseite bekommt eine eigene Content-Security-Policy.** Die bestehende Richtlinie enthält `form-action 'none'` und würde das Absenden des Passwortformulars und die anschließende Weiterleitung zu `claude.ai` blockieren. `/mcp` bekommt gar keine Richtlinie, weil dort kein Dokument ausgeliefert wird.

---

## Reihenfolge und warum sie so ist

Die Spec sagt in Abschnitt 10: „OAuth ist der fehleranfälligste Teil … deshalb wird OAuth als eigenes Implementierungspaket gebaut und vollständig getestet, bevor die Werkzeuge dazukommen." Der Plan hält sich daran. Tasks 1–7 bauen den Autorisierungsserver ohne eine Zeile MCP; Task 8 hängt den MCP-Endpunkt ein und schließt den Handschlag; erst Tasks 9–12 bringen Werkzeuge. Task 13 ist der Praxistest, der als einziger etwas voraussetzt, das nicht auf diesem Rechner liegt.

---

### Task 1: Das SDK aufnehmen und die Sitzungsquelle absichern

Der MCP-Endpunkt ist keine FastAPI-Route. Er bekommt seine Datenbanksitzung deshalb **nicht** über `Depends(get_session)` – und der Schutz in `tests/conftest.py` ist genau das: ein Eintrag in `app.dependency_overrides`, der ausschließlich für FastAPI-Abhängigkeiten greift. Holte sich die MCP-Schicht ihre Sitzung direkt über `get_session_factory()`, träfen alle MCP-Tests die **Entwicklungsdatenbank**, und zwar grün. Diese Aufgabe baut die eine Naht, an der das nicht passieren kann, und nimmt dabei das SDK auf.

**Files:**
- Create: `app/sitzung.py`, `tests/test_sitzung.py`
- Modify: `pyproject.toml`, `uv.lock`, `tests/conftest.py`
- Test: `tests/test_sitzung.py`

**Interfaces:**
- Consumes: `app.db.get_session_factory`
- Produces:
  - `app.sitzung.sitzung() -> AbstractAsyncContextManager[AsyncSession]` – die einzige Sitzungsquelle für Nicht-FastAPI-Code
  - `app.sitzung.quelle_setzen(neue: Callable[[], AbstractAsyncContextManager[AsyncSession]]) -> None`
  - `app.sitzung.quelle_zuruecksetzen() -> None`
  - `app.sitzung.KeineSitzungsquelle` (Exception)
  - Fixture `mcp_sitzung` in `tests/conftest.py`, die `sitzung()` auf die Testsession umbiegt

- [ ] **Step 1: Ausgangsstand festhalten**

```bash
docker compose -f compose.dev.yml up -d
set -a; . ./.env; set +a
uv run pytest -q
```
Erwartet: `117 passed`, keine Warnungen, nichts übersprungen. Weicht das ab, ist der Ausgangsstand nicht der angenommene – nicht weiterarbeiten, sondern klären.

- [ ] **Step 2: Das SDK aufnehmen und die Version festhalten**

In `pyproject.toml` unter `dependencies` ergänzen (alphabetisch hinter `markdown-it-py`):

```toml
    # Das offizielle MCP-SDK. Untergrenze 2.1: Erst ab 2.x heisst die Klasse
    # MCPServer (mcp.server.mcpserver) und liefert streamable_http_app() eine
    # Starlette-App, die sich als ASGI-Anwendung einhaengen laesst. Obergrenze
    # 3: Ein Hauptversionssprung hat dieses SDK bereits einmal komplett
    # umbenannt (mcp.server.fastmcp wirft heute einen ModuleNotFoundError mit
    # Migrationshinweis) - das soll die CI melden und nicht der Betrieb.
    "mcp>=2.1,<3",
```

Dann:

```bash
uv lock
uv sync
```

- [ ] **Step 3: Den Versionstest schreiben und laufen lassen**

`tests/test_sitzung.py` anlegen mit diesem ersten Test:

```python
"""Tests fuer die Sitzungsquelle aus app/sitzung.py und fuer das MCP-SDK.

Warum beides in einer Datei: Die Sitzungsquelle existiert ausschliesslich,
damit die MCP-Schicht nicht an tests/conftest.py vorbei auf die
Entwicklungsdatenbank zugreift. Ohne SDK gaebe es sie nicht.
"""

import pytest

from app.sitzung import KeineSitzungsquelle, quelle_setzen, quelle_zuruecksetzen, sitzung


def test_das_sdk_ist_version_zwei():
    """Version 1 des SDK haette eine voellig andere API.

    In Version 1 hiess die Klasse FastMCP und lag in mcp.server.fastmcp.
    Wuerde jemand versehentlich auf 1.x zurueckfallen, scheiterte der Import
    hier - und nicht erst irgendwo mitten im Betrieb.
    """
    from mcp.server.mcpserver import MCPServer

    assert MCPServer is not None

    with pytest.raises(ModuleNotFoundError):
        import mcp.server.fastmcp  # noqa: F401
```

Laufen lassen:

```bash
uv run pytest tests/test_sitzung.py -q
```
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'app.sitzung'`.

- [ ] **Step 4: Den Sperrtest schreiben und laufen lassen**

An `tests/test_sitzung.py` anhängen:

```python
async def test_ohne_gesetzte_quelle_fliegt_ein_klarer_fehler():
    """Die Standardquelle wird in Tests durch eine Sperre ersetzt.

    Der Sinn der Sperre steht in tests/conftest.py bei der Fixture
    "sitzungsquelle_gesperrt": Ein MCP-Test, der die Fixture "mcp_sitzung"
    vergisst, soll laut scheitern statt still die Entwicklungsdatenbank zu
    treffen.
    """
    with pytest.raises(KeineSitzungsquelle):
        async with sitzung():
            pass


async def test_gesetzte_quelle_wird_benutzt(session):
    """quelle_setzen biegt sitzung() auf eine beliebige Sitzung um."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def eigene():
        yield session

    quelle_setzen(eigene)
    try:
        async with sitzung() as gefunden:
            assert gefunden is session
    finally:
        quelle_zuruecksetzen()
```

```bash
uv run pytest tests/test_sitzung.py -q
```
Erwartet: FAIL, `app.sitzung` gibt es noch nicht.

- [ ] **Step 5: `app/sitzung.py` schreiben**

```python
"""Die Sitzungsquelle fuer alles, was keine FastAPI-Abhaengigkeit ist.

Der MCP-Endpunkt und der Token-Pruefer laufen ausserhalb von FastAPIs
Abhaengigkeitsaufloesung: Der eine ist eine eingehaengte ASGI-Anwendung, der
andere wird vom SDK aus einer Middleware heraus aufgerufen. Beide koennen
Depends(get_session) nicht benutzen.

Das ist keine Kleinigkeit, sondern eine Sicherheitsnaht: Die Absicherung in
tests/conftest.py ist ein Eintrag in app.dependency_overrides und greift
ausschliesslich fuer FastAPI-Abhaengigkeiten. Griffe die MCP-Schicht direkt
zu get_session_factory(), traefen alle MCP-Tests die
ENTWICKLUNGSDATENBANK - und zwar gruen, ohne dass irgendetwas auffiele.

Deshalb gibt es genau eine Stelle, an der eine Sitzung entsteht, und diese
Stelle ist ausdruecklich ueberschreibbar.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session_factory

Quelle = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class KeineSitzungsquelle(RuntimeError):
    """Es wurde keine Sitzungsquelle gesetzt.

    Kann im Betrieb nicht auftreten - dort steht die Standardquelle. Der
    Fehler existiert fuer die Testsperre in tests/conftest.py.
    """


@asynccontextmanager
async def _standardquelle() -> AsyncIterator[AsyncSession]:
    """Eine Sitzung aus der gecachten Fabrik, wie get_session sie auch nimmt."""
    async with get_session_factory()() as offene:
        yield offene


_quelle: Quelle = _standardquelle


def quelle_setzen(neue: Quelle) -> None:
    """Ersetzt die Sitzungsquelle. Nur fuer Tests gedacht."""
    global _quelle
    _quelle = neue


def quelle_zuruecksetzen() -> None:
    """Stellt die Standardquelle wieder her."""
    global _quelle
    _quelle = _standardquelle


def sitzung() -> AbstractAsyncContextManager[AsyncSession]:
    """Die einzige Sitzungsquelle fuer Nicht-FastAPI-Code.

    Benutzung:

        async with sitzung() as offene:
            ...
    """
    return _quelle()
```

- [ ] **Step 6: Die Sperre und die Fixture in `tests/conftest.py` ergänzen**

Am Ende von `tests/conftest.py` anhängen:

```python
@pytest.fixture(autouse=True)
def sitzungsquelle_gesperrt():
    """Sperrt die Sitzungsquelle aus app/sitzung.py fuer JEDEN Test.

    Ohne diese Sperre wuerde ein MCP-Test, der die Fixture "mcp_sitzung"
    vergisst, still die Entwicklungsdatenbank (DATABASE_URL) treffen und
    gruen werden. Der Override in "datenbank_override" kann das nicht
    verhindern: Er ist ein Eintrag in app.dependency_overrides und greift
    ausschliesslich fuer FastAPI-Abhaengigkeiten - der MCP-Endpunkt ist
    keine.

    autouse und ohne Datenbankbezug: Die Sperre braucht kein PostgreSQL und
    darf deshalb auch in Tests gelten, die gar keine Datenbank anfassen.
    """
    from app.sitzung import KeineSitzungsquelle, quelle_setzen, quelle_zuruecksetzen

    @asynccontextmanager
    async def gesperrt():
        raise KeineSitzungsquelle(
            "Es ist keine Sitzungsquelle gesetzt. In Tests fordert man dafuer "
            "die Fixture 'mcp_sitzung' an (siehe tests/conftest.py)."
        )
        yield  # pragma: no cover -- macht die Funktion zum Generator

    quelle_setzen(gesperrt)
    yield
    quelle_zuruecksetzen()


@pytest.fixture
def mcp_sitzung(session: AsyncSession, sitzungsquelle_gesperrt: None) -> AsyncSession:
    """Biegt app.sitzung.sitzung() auf die Testsession um.

    Jeder Test, der MCP-Werkzeuge oder den Token-Pruefer aufruft, fordert
    diese Fixture an und bekommt damit dieselbe Session wie die
    HTTP-Anfragen ueber "client"/"klient" - eine Transaktion, ein
    Rollback am Ende.
    """
    from app.sitzung import quelle_setzen

    @asynccontextmanager
    async def testquelle():
        yield session

    quelle_setzen(testquelle)
    return session
```

Und ganz oben in `tests/conftest.py` den fehlenden Import ergänzen:

```python
from contextlib import asynccontextmanager
```

- [ ] **Step 7: Tests laufen lassen**

```bash
uv run pytest -q
```
Erwartet: `120 passed`, 0 übersprungen, 0 Warnungen. Insbesondere müssen die 117 bestehenden Tests unverändert grün bleiben – die autouse-Sperre darf keinen davon berühren, weil bisher niemand `app.sitzung` benutzt.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock app/sitzung.py tests/conftest.py tests/test_sitzung.py
git commit -m "MCP-SDK aufgenommen und die Sitzungsquelle gegen die Entwicklungsdatenbank abgedichtet"
```

---

### Task 2: OAuth-Tabellen und Migration 0002

Registrierte Clients, ausgegebene Codes und Tokens müssen Deployments überstehen (Spec, Abschnitt 5). Diese Aufgabe baut das Schema und nichts weiter – am Ende steht eine eingespielte Migration, die `alembic check` durchlässt.

**Files:**
- Create: `app/oauth/__init__.py`, `app/oauth/modelle.py`, `migrations/versions/0002_oauth.py`, `tests/test_oauth_modelle.py`
- Modify: `tests/conftest.py` (Modelle registrieren), `migrations/env.py` (Modelle registrieren)
- Test: `tests/test_oauth_modelle.py`

**Interfaces:**
- Consumes: `app.db.Base`
- Produces:
  - `app.oauth.modelle.OAuthClient` mit `client_id: str` (PK), `client_name: str | None`, `redirect_uris: list[str]` (JSONB), `scope: str`, `erstellt_am: datetime`
  - `app.oauth.modelle.OAuthCode` mit `code_hash: str` (PK), `client_id: str`, `redirect_uri: str`, `code_challenge: str`, `scope: str`, `resource: str | None`, `familie_id: uuid.UUID`, `ablauf_am: datetime`, `eingeloest_am: datetime | None`, `erstellt_am: datetime`
  - `app.oauth.modelle.OAuthToken` mit `token_hash: str` (PK), `art: str` (`"zugriff"` oder `"erneuerung"`), `client_id: str`, `familie_id: uuid.UUID`, `scope: str`, `resource: str | None`, `ablauf_am: datetime`, `zurueckgezogen_am: datetime | None`, `erstellt_am: datetime`
  - Konstanten `ART_ZUGRIFF = "zugriff"`, `ART_ERNEUERUNG = "erneuerung"`, `STANDARD_SCOPE = "lernseiten"`

- [ ] **Step 1: Die Constraint-Tests schreiben**

`tests/test_oauth_modelle.py`:

```python
"""Tests fuer die OAuth-Tabellen.

Dieselbe Haltung wie in tests/test_models.py: Falsche Daten duerfen gar
nicht erst hineinkommen, und geprueft wird das gegen echtes PostgreSQL -
die Constraints sind der Kern des Modells und in SQLite nicht vorhanden.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.oauth.modelle import ART_ERNEUERUNG, ART_ZUGRIFF, OAuthClient, OAuthCode, OAuthToken


def _client(**abweichungen) -> OAuthClient:
    felder = {
        "client_id": "kunde-" + uuid.uuid4().hex[:8],
        "client_name": "Claude",
        "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        "scope": "lernseiten",
    }
    felder.update(abweichungen)
    return OAuthClient(**felder)


def _in_einer_stunde() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=1)


async def test_ein_client_laesst_sich_speichern(session):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    assert kunde.erstellt_am is not None


async def test_redirect_uris_darf_keine_leere_liste_sein(session):
    session.add(_client(redirect_uris=[]))
    with pytest.raises(IntegrityError, match="ck_oauth_clients_redirect_uris"):
        await session.flush()


async def test_redirect_uris_darf_keine_zahlen_enthalten(session):
    session.add(_client(redirect_uris=[1, 2]))
    with pytest.raises(IntegrityError, match="ck_oauth_clients_redirect_uris"):
        await session.flush()


async def test_unbekannte_tokenart_wird_abgelehnt(session):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthToken(
            token_hash="a" * 64,
            art="zauberstab",
            client_id=kunde.client_id,
            familie_id=uuid.uuid4(),
            scope="lernseiten",
            ablauf_am=_in_einer_stunde(),
        )
    )
    with pytest.raises(IntegrityError, match="ck_oauth_tokens_art"):
        await session.flush()


@pytest.mark.parametrize("art", [ART_ZUGRIFF, ART_ERNEUERUNG])
async def test_beide_tokenarten_sind_erlaubt(session, art):
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthToken(
            token_hash=uuid.uuid4().hex * 2,
            art=art,
            client_id=kunde.client_id,
            familie_id=uuid.uuid4(),
            scope="lernseiten",
            ablauf_am=_in_einer_stunde(),
        )
    )
    await session.flush()


async def test_ein_code_haengt_am_client_und_faellt_mit_ihm(session):
    """ON DELETE CASCADE: Wird ein Client geloescht, verschwinden seine Codes."""
    kunde = _client()
    session.add(kunde)
    await session.flush()
    session.add(
        OAuthCode(
            code_hash="b" * 64,
            client_id=kunde.client_id,
            redirect_uri="https://claude.ai/api/mcp/auth_callback",
            code_challenge="c" * 43,
            scope="lernseiten",
            familie_id=uuid.uuid4(),
            ablauf_am=_in_einer_stunde(),
        )
    )
    await session.flush()

    await session.delete(kunde)
    await session.flush()

    uebrig = await session.scalar(select(func.count()).select_from(OAuthCode.__table__))
    assert uebrig == 0
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_modelle.py -q
```
Erwartet: FAIL, `ModuleNotFoundError: No module named 'app.oauth'`.

- [ ] **Step 3: `app/oauth/__init__.py` und `app/oauth/modelle.py` schreiben**

`app/oauth/__init__.py` bleibt leer bis auf einen Docstring:

```python
"""Der eigene OAuth-Autorisierungsserver.

Das MCP-SDK ist in diesem Projekt ausschliesslich Resource Server: Es prueft
Tokens, gibt aber keine aus. Ausgegeben werden sie hier.
"""
```

`app/oauth/modelle.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Der einzige Scope dieses Servers. Ein Ein-Personen-Login braucht keine
# Rechtestufen; der Scope existiert, weil OAuth ihn im Metadatendokument und
# in AuthSettings.required_scopes erwartet.
STANDARD_SCOPE = "lernseiten"

# Die beiden Tokenarten. Deutsche Werte, weil sie in der Datenbank stehen und
# dort niemand englische Bezeichner braucht.
ART_ZUGRIFF = "zugriff"
ART_ERNEUERUNG = "erneuerung"

# Gepfefferte SHA-256-Hashes in Hexdarstellung sind immer 64 Zeichen lang.
HASH_LAENGE = 64

# RFC 7591 setzt keine Obergrenze fuer eine Redirect-URI. 2000 Zeichen sind
# das, was Browser und Proxys sicher tragen, und begrenzen zugleich, was ein
# unauthentifizierter Registrierungsaufruf in die Datenbank schreiben kann.
MAX_REDIRECT_URI_LAENGE = 2000


class OAuthClient(Base):
    """Ein per Dynamic Client Registration angemeldeter Client (RFC 7591)."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_name: Mapped[str | None] = mapped_column(Text)
    # MutableList.as_mutable wie bei Karte.antworten in app/models.py: Ohne
    # das bemerkt SQLAlchemy eine Aenderung an der Liste selbst nicht.
    redirect_uris: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSONB), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Dieselbe Machart wie ck_karten_antworten_sind_texte in
        # migrations/versions/0001_grundmodell.py, inklusive des
        # "strict"-Schluesselworts: Ohne "strict" packt der jsonpath-Modus
        # "lax" ein verschachteltes Array eine Ebene tief aus, bevor der
        # Filter greift - [["https://x"]] kaeme dann durch. CASE WHEN statt
        # AND/OR, weil PostgreSQL bei AND/OR keine Auswertungsreihenfolge
        # garantiert und jsonb_array_length() auf einem Objekt einen
        # DataError statt eines IntegrityError werfen wuerde.
        CheckConstraint(
            """
            CASE
                WHEN jsonb_typeof(redirect_uris) = 'array'
                    THEN jsonb_array_length(redirect_uris) >= 1
                        AND jsonb_array_length(redirect_uris) = jsonb_array_length(
                            jsonb_path_query_array(
                                redirect_uris, 'strict $[*] ? (@.type() == "string")'))
                ELSE false
            END
            """,
            name="ck_oauth_clients_redirect_uris",
        ),
    )


class OAuthCode(Base):
    """Ein ausgegebener Autorisierungscode. Genau einmal einloesbar."""

    __tablename__ = "oauth_codes"

    code_hash: Mapped[str] = mapped_column(String(HASH_LAENGE), primary_key=True)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    code_challenge: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    # RFC 8707. Wird mitgeschrieben, aber nicht erzwungen - siehe E-3 im Plan.
    resource: Mapped[str | None] = mapped_column(Text)
    # Alle Tokens, die aus diesem Code hervorgehen, tragen dieselbe
    # familie_id. Wird ein bereits eingeloester Code oder ein bereits
    # rotierter Refresh-Token ein zweites Mal vorgelegt, gilt die ganze
    # Familie als kompromittiert und wird zurueckgezogen.
    familie_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eingeloest_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            f"length(redirect_uri) <= {MAX_REDIRECT_URI_LAENGE}",
            name="ck_oauth_codes_redirect_uri_max_laenge",
        ),
    )


class OAuthToken(Base):
    """Ein ausgegebener Zugriffs- oder Erneuerungstoken.

    Gespeichert wird ausschliesslich der gepfefferte Hash (siehe
    app/oauth/geheimnisse.py). Ein gestohlener Datenbankauszug enthaelt damit
    keine benutzbaren Tokens.
    """

    __tablename__ = "oauth_tokens"

    token_hash: Mapped[str] = mapped_column(String(HASH_LAENGE), primary_key=True)
    art: Mapped[str] = mapped_column(String(30), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("oauth_clients.client_id", ondelete="CASCADE"), nullable=False
    )
    familie_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )
    scope: Mapped[str] = mapped_column(String(120), nullable=False)
    resource: Mapped[str | None] = mapped_column(Text)
    ablauf_am: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    zurueckgezogen_am: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # String(30) statt String(12) aus demselben Grund wie bei Karte.art in
        # app/models.py: Eine unbekannte Art soll am CHECK scheitern
        # (IntegrityError), nicht schon an der Spaltenlaenge (DataError).
        CheckConstraint(
            f"art IN ('{ART_ZUGRIFF}', '{ART_ERNEUERUNG}')",
            name="ck_oauth_tokens_art",
        ),
    )
```

- [ ] **Step 4: Die Modelle bei `Base.metadata` registrieren**

In `tests/conftest.py` direkt unter dem bestehenden Modell-Import:

```python
from app.oauth import modelle as oauth_modelle  # noqa: F401 -- registriert die OAuth-Tabellen
```

In `migrations/env.py` direkt unter `from app import models`:

```python
from app.oauth import modelle as oauth_modelle  # noqa: F401  -- OAuth-Tabellen registrieren
```

- [ ] **Step 5: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_modelle.py -q
```
Erwartet: PASS (6 Tests). Das Testschema entsteht aus `Base.metadata.create_all`, deshalb greifen die Constraints schon vor der Migration.

- [ ] **Step 6: Die Migration 0002 erzeugen**

```bash
uv run alembic revision --autogenerate --rev-id 0002 -m "oauth-tabellen"
```

Erwartet: `migrations/versions/0002_oauth_tabellen.py`. Die Datei öffnen und prüfen, dass `revision: str = '0002'` und `down_revision = '0001'` darin stehen und dass genau die drei Tabellen `oauth_clients`, `oauth_codes`, `oauth_tokens` samt der drei benannten Constraints angelegt werden. Ins `upgrade()` gehört nichts anderes – findet Alembic Änderungen an `bundles` oder `karten`, ist etwas anderes schiefgelaufen; dann anhalten und klären.

- [ ] **Step 7: Migration einspielen und gegenprüfen**

```bash
uv run alembic upgrade head
uv run alembic check
```
Erwartet: `upgrade` läuft durch, `check` meldet `No new upgrade operations detected.`

- [ ] **Step 8: Gesamte Suite laufen lassen**

```bash
uv run pytest -q
```
Erwartet: `126 passed`, 0 übersprungen, 0 Warnungen.

- [ ] **Step 9: Commit**

```bash
git add app/oauth migrations/versions/0002_oauth_tabellen.py migrations/env.py tests/conftest.py tests/test_oauth_modelle.py
git commit -m "OAuth-Tabellen fuer Clients, Codes und Tokens samt Migration 0002"
```

---

### Task 3: Geheimnisse und Speicher

Der ganze OAuth-Ablauf besteht aus zwei Sorten Arbeit: Geheimnisse erzeugen und vergleichen, und sie in der Datenbank verwalten. Beides ist ohne HTTP prüfbar und wird deshalb hier erledigt, bevor irgendeine Route entsteht.

**Files:**
- Create: `app/oauth/geheimnisse.py`, `app/oauth/speicher.py`, `tests/test_oauth_geheimnisse.py`, `tests/test_oauth_speicher.py`
- Test: `tests/test_oauth_geheimnisse.py`, `tests/test_oauth_speicher.py`

**Interfaces:**
- Consumes: `app.config.get_settings`, `app.oauth.modelle.*`
- Produces:
  - `app.oauth.geheimnisse.neues_geheimnis() -> str` – 43 Zeichen URL-sicher (32 Byte)
  - `app.oauth.geheimnisse.pfeffern(wert: str) -> str` – 64 Zeichen hex, HMAC-SHA256 mit `APP_SECRET`
  - `app.oauth.geheimnisse.gleich(links: str, rechts: str) -> bool` – konstantzeitig
  - `app.oauth.geheimnisse.pkce_ableiten(code_verifier: str) -> str` – base64url ohne Polster, RFC 7636 `S256`
  - `app.oauth.speicher.client_anlegen(sitzung, client_name, redirect_uris) -> OAuthClient`
  - `app.oauth.speicher.client_holen(sitzung, client_id) -> OAuthClient | None`
  - `app.oauth.speicher.code_ausgeben(sitzung, client, redirect_uri, code_challenge, resource) -> str` (der Klartext-Code)
  - `app.oauth.speicher.code_einloesen(sitzung, code, client_id, redirect_uri, code_verifier) -> OAuthCode` (wirft `OAuthFehler`)
  - `app.oauth.speicher.tokenpaar_ausgeben(sitzung, client_id, familie_id, scope, resource) -> tuple[str, str, int]` (Zugriffstoken, Erneuerungstoken, Gültigkeit in Sekunden)
  - `app.oauth.speicher.erneuern(sitzung, erneuerungstoken, client_id) -> tuple[str, str, int]` (wirft `OAuthFehler`)
  - `app.oauth.speicher.zugriffstoken_pruefen(sitzung, token) -> OAuthToken | None`
  - `app.oauth.speicher.OAuthFehler(code: str, beschreibung: str)` – `code` ist der RFC-Code (`invalid_grant`, …), `beschreibung` der deutsche Klartext
  - Konstanten `CODE_GUELTIGKEIT = timedelta(minutes=10)`, `ZUGRIFF_GUELTIGKEIT = timedelta(hours=1)`, `ERNEUERUNG_GUELTIGKEIT = timedelta(days=30)`

- [ ] **Step 1: Tests für die Geheimnisse schreiben**

`tests/test_oauth_geheimnisse.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_geheimnisse.py -q
```
Erwartet: FAIL, `No module named 'app.oauth.geheimnisse'`.

- [ ] **Step 3: `app/oauth/geheimnisse.py` schreiben**

```python
"""Zufall, Pfeffer und PKCE.

Alle Geheimnisse dieses Servers entstehen hier, und alle Vergleiche laufen
konstantzeitig. Gespeichert wird nie ein Geheimnis, sondern immer nur sein
mit APP_SECRET gepfefferter HMAC-SHA256 - ein gestohlener
Datenbankauszug enthaelt damit keine benutzbaren Tokens.
"""

import base64
import hashlib
import hmac
import re
import secrets

from app.config import get_settings

# 32 Byte Zufall, base64url ohne Polster: 43 Zeichen. Das ist zugleich die
# Untergrenze, die RFC 7636 fuer einen code_verifier vorschreibt.
GEHEIMNIS_BYTES = 32

# RFC 7636, Abschnitt 4.1: 43 bis 128 Zeichen aus [A-Za-z0-9-._~].
_VERIFIER_MUSTER = re.compile(r"[A-Za-z0-9\-._~]{43,128}")


def _ohne_polster(rohbytes: bytes) -> str:
    return base64.urlsafe_b64encode(rohbytes).decode("ascii").rstrip("=")


def neues_geheimnis() -> str:
    """Ein frisches, URL-sicheres Geheimnis mit 256 Bit Entropie."""
    return _ohne_polster(secrets.token_bytes(GEHEIMNIS_BYTES))


def pfeffern(wert: str) -> str:
    """Der HMAC-SHA256 des Wertes unter APP_SECRET, hexadezimal.

    HMAC statt eines nackten sha256: Ohne Schluessel liesse sich zu einem
    erbeuteten Hash der zugehoerige Token offline suchen. Mit Schluessel
    braucht es dafuer zusaetzlich APP_SECRET, und das steht nicht in der
    Datenbank.

    Absichtlich KEIN Passwort-Hash (argon2, bcrypt): Die Werte sind
    256-Bit-Zufall, nicht ratbare Passwoerter. Ein langsamer Hash brauchte
    hier bei jeder MCP-Anfrage Rechenzeit, ohne etwas zu schuetzen.
    """
    schluessel = get_settings().app_secret.encode("utf-8")
    return hmac.new(schluessel, wert.encode("utf-8"), hashlib.sha256).hexdigest()


def gleich(links: str, rechts: str) -> bool:
    """Konstantzeitiger Vergleich zweier Zeichenketten."""
    return hmac.compare_digest(links, rechts)


def pkce_ableiten(code_verifier: str) -> str:
    """Die code_challenge zu einem code_verifier nach RFC 7636, Methode S256.

    Raises:
        ValueError: Wenn der Verifier nicht dem Format aus RFC 7636 entspricht.
            Die Pruefung gehoert hierher und nicht zum Aufrufer: Ein zu kurzer
            Verifier haette weniger Entropie als vorgeschrieben, und das darf
            nicht davon abhaengen, ob eine Route daran gedacht hat.
    """
    if not _VERIFIER_MUSTER.fullmatch(code_verifier):
        raise ValueError(
            "Der code_verifier entspricht nicht RFC 7636: erwartet werden 43 "
            "bis 128 Zeichen aus A-Z, a-z, 0-9 und den Zeichen - . _ ~"
        )
    return _ohne_polster(hashlib.sha256(code_verifier.encode("ascii")).digest())
```

- [ ] **Step 4: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_geheimnisse.py -q
```
Erwartet: PASS (9 Tests).

- [ ] **Step 5: Tests für den Speicher schreiben**

`tests/test_oauth_speicher.py`:

```python
"""Tests fuer app/oauth/speicher.py - die Datenbankarbeit des OAuth-Servers.

Ohne HTTP. Geprueft wird, was die Spec in Abschnitt 5 verlangt: Codes sind
genau einmal einloesbar, PKCE ist Pflicht, Refresh-Tokens rotieren, und ein
zurueckgezogener Token wird mit invalid_grant beantwortet - nicht mit einem
eigenen Fehlercode.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.modelle import ART_ERNEUERUNG, ART_ZUGRIFF, OAuthToken
from app.oauth.speicher import (
    OAuthFehler,
    client_anlegen,
    client_holen,
    code_ausgeben,
    code_einloesen,
    erneuern,
    tokenpaar_ausgeben,
    zugriffstoken_pruefen,
)

REDIRECT = "https://claude.ai/api/mcp/auth_callback"


async def _client(session):
    return await client_anlegen(session, client_name="Claude", redirect_uris=[REDIRECT])


async def _code_mit_verifier(session, kunde):
    verifier = neues_geheimnis()
    code = await code_ausgeben(
        session,
        client=kunde,
        redirect_uri=REDIRECT,
        code_challenge=pkce_ableiten(verifier),
        resource="https://karten.example.de/mcp",
    )
    return code, verifier


async def test_client_anlegen_und_wiederfinden(session):
    kunde = await _client(session)
    assert len(kunde.client_id) >= 20
    gefunden = await client_holen(session, kunde.client_id)
    assert gefunden is not None
    assert gefunden.redirect_uris == [REDIRECT]


async def test_unbekannter_client_ist_none(session):
    assert await client_holen(session, "gibt-es-nicht") is None


async def test_code_wird_genau_einmal_eingeloest(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)

    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    assert eingeloest.eingeloest_am is not None

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_falscher_verifier_wird_abgelehnt(session):
    kunde = await _client(session)
    code, _ = await _code_mit_verifier(session, kunde)

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=neues_geheimnis(),
        )
    assert fehler.value.code == "invalid_grant"


async def test_falsche_redirect_uri_wird_abgelehnt(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id,
            redirect_uri="http://127.0.0.1:9999/callback", code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_abgelaufener_code_wird_abgelehnt(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)
    gespeichert = await session.scalar(
        select(__import__("app.oauth.modelle", fromlist=["OAuthCode"]).OAuthCode)
    )
    gespeichert.ablauf_am = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.flush()

    with pytest.raises(OAuthFehler) as fehler:
        await code_einloesen(
            session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
            code_verifier=verifier,
        )
    assert fehler.value.code == "invalid_grant"


async def test_tokenpaar_ist_pruefbar(session):
    kunde = await _client(session)
    code, verifier = await _code_mit_verifier(session, kunde)
    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    zugriff, erneuerung, gueltigkeit = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=eingeloest.familie_id,
        scope=eingeloest.scope, resource=eingeloest.resource,
    )
    assert gueltigkeit == 3600
    assert zugriff != erneuerung

    geprueft = await zugriffstoken_pruefen(session, zugriff)
    assert geprueft is not None
    assert geprueft.client_id == kunde.client_id
    assert geprueft.art == ART_ZUGRIFF


async def test_der_klartext_token_steht_nirgends_in_der_datenbank(session):
    """Gespeichert wird nur der gepfefferte Hash - das ist der ganze Punkt."""
    kunde = await _client(session)
    zugriff, erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id,
        familie_id=(await _code_und_familie(session, kunde)), scope="lernseiten",
        resource=None,
    )
    hashes = (await session.scalars(select(OAuthToken.token_hash))).all()
    assert zugriff not in hashes
    assert erneuerung not in hashes


async def _code_und_familie(session, kunde):
    code, verifier = await _code_mit_verifier(session, kunde)
    eingeloest = await code_einloesen(
        session, code=code, client_id=kunde.client_id, redirect_uri=REDIRECT,
        code_verifier=verifier,
    )
    return eingeloest.familie_id


async def test_erneuern_rotiert_und_zieht_den_alten_zurueck(session):
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erste_erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )

    zweiter_zugriff, zweite_erneuerung, _ = await erneuern(
        session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
    )
    assert zweite_erneuerung != erste_erneuerung
    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is not None

    with pytest.raises(OAuthFehler) as fehler:
        await erneuern(
            session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
        )
    assert fehler.value.code == "invalid_grant"


async def test_wiederverwendung_zieht_die_ganze_familie_zurueck(session):
    """Ein zweites Mal vorgelegter Erneuerungstoken heisst: er wurde gestohlen.

    Dann ist auch der frisch ausgegebene nichts mehr wert - sonst arbeitete
    der Dieb einfach mit dem neueren weiter.
    """
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erste_erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    zweiter_zugriff, _, _ = await erneuern(
        session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
    )
    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is not None

    with pytest.raises(OAuthFehler):
        await erneuern(
            session, erneuerungstoken=erste_erneuerung, client_id=kunde.client_id
        )

    assert await zugriffstoken_pruefen(session, zweiter_zugriff) is None


async def test_abgelaufener_zugriffstoken_gilt_nicht(session):
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    zugriff, _, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    gespeichert = await session.scalar(
        select(OAuthToken).where(OAuthToken.art == ART_ZUGRIFF)
    )
    gespeichert.ablauf_am = datetime.now(timezone.utc) - timedelta(seconds=1)
    await session.flush()

    assert await zugriffstoken_pruefen(session, zugriff) is None


async def test_unbekannter_zugriffstoken_gilt_nicht(session):
    assert await zugriffstoken_pruefen(session, neues_geheimnis()) is None


async def test_ein_erneuerungstoken_taugt_nicht_als_zugriffstoken(session):
    """Sonst waere der langlebige Token unmittelbar ein Schluessel zu /mcp."""
    kunde = await _client(session)
    familie = await _code_und_familie(session, kunde)
    _, erneuerung, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=familie, scope="lernseiten",
        resource=None,
    )
    assert await zugriffstoken_pruefen(session, erneuerung) is None
    assert ART_ERNEUERUNG != ART_ZUGRIFF
```

- [ ] **Step 6: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_speicher.py -q
```
Erwartet: FAIL, `No module named 'app.oauth.speicher'`.

- [ ] **Step 7: `app/oauth/speicher.py` schreiben**

```python
"""Die Datenbankarbeit des OAuth-Servers.

Kennt kein HTTP. Jede Ablehnung verlaesst dieses Modul als OAuthFehler mit
einem RFC-Code und einem deutschen Klartext; welche der beiden Angaben in
der Antwort landet, entscheidet die Route.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.oauth.geheimnisse import gleich, neues_geheimnis, pfeffern, pkce_ableiten
from app.oauth.modelle import (
    ART_ERNEUERUNG,
    ART_ZUGRIFF,
    STANDARD_SCOPE,
    OAuthClient,
    OAuthCode,
    OAuthToken,
)

# Zehn Minuten sind grosszuegig fuer einen Klick auf "Zugriff geben" und
# knapp genug, dass ein abgefangener Code nicht lange nuetzt.
CODE_GUELTIGKEIT = timedelta(minutes=10)
# Eine Stunde, wie die Spec es in Abschnitt 5 vorgibt.
ZUGRIFF_GUELTIGKEIT = timedelta(hours=1)
# 30 Tage. Laenger waere unnoetig, kuerzer hiesse, dass die Lehrerin den
# Connector regelmaessig neu verbinden muss.
ERNEUERUNG_GUELTIGKEIT = timedelta(days=30)


class OAuthFehler(Exception):
    """Eine Ablehnung mit RFC-Code und deutschem Klartext."""

    def __init__(self, code: str, beschreibung: str) -> None:
        super().__init__(f"{code}: {beschreibung}")
        self.code = code
        self.beschreibung = beschreibung


def _jetzt() -> datetime:
    return datetime.now(timezone.utc)


async def client_anlegen(
    sitzung: AsyncSession, client_name: str | None, redirect_uris: list[str]
) -> OAuthClient:
    """Legt einen Client an und gibt ihn zurueck (RFC 7591)."""
    kunde = OAuthClient(
        client_id=neues_geheimnis(),
        client_name=client_name,
        redirect_uris=list(redirect_uris),
        scope=STANDARD_SCOPE,
    )
    sitzung.add(kunde)
    await sitzung.flush()
    return kunde


async def client_holen(sitzung: AsyncSession, client_id: str) -> OAuthClient | None:
    return await sitzung.scalar(
        select(OAuthClient).where(OAuthClient.client_id == client_id)
    )


async def code_ausgeben(
    sitzung: AsyncSession,
    client: OAuthClient,
    redirect_uri: str,
    code_challenge: str,
    resource: str | None,
) -> str:
    """Gibt einen frischen Autorisierungscode aus und gibt ihn im Klartext zurueck.

    In der Datenbank landet nur der gepfefferte Hash. Die familie_id, die
    hier entsteht, begleitet alle Tokens, die spaeter aus diesem Code
    hervorgehen.
    """
    code = neues_geheimnis()
    sitzung.add(
        OAuthCode(
            code_hash=pfeffern(code),
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            scope=client.scope,
            resource=resource,
            familie_id=uuid.uuid4(),
            ablauf_am=_jetzt() + CODE_GUELTIGKEIT,
        )
    )
    await sitzung.flush()
    return code


async def code_einloesen(
    sitzung: AsyncSession,
    code: str,
    client_id: str,
    redirect_uri: str,
    code_verifier: str,
) -> OAuthCode:
    """Loest einen Autorisierungscode ein. Genau einmal.

    Raises:
        OAuthFehler: Immer mit dem Code "invalid_grant". Die Spec verlangt in
            Abschnitt 5 ausdruecklich, dass abgelaufene oder zurueckgezogene
            Grants mit invalid_grant beantwortet werden und nicht mit einem
            eigenen Fehlercode. Auch die Beschreibungen bleiben absichtlich
            unspezifisch: Ein Angreifer soll aus der Antwort nicht ablesen
            koennen, welcher der Pruefschritte gescheitert ist.
    """
    abgelehnt = OAuthFehler(
        "invalid_grant",
        "Der Autorisierungscode ist ungueltig, abgelaufen oder bereits "
        "eingeloest. Bitte verbinde den Connector noch einmal.",
    )

    gespeichert = await sitzung.scalar(
        select(OAuthCode).where(OAuthCode.code_hash == pfeffern(code))
    )
    if gespeichert is None:
        raise abgelehnt
    if gespeichert.eingeloest_am is not None:
        # Ein zweites Mal vorgelegter Code heisst: Er wurde abgefangen. Alles,
        # was aus ihm hervorgegangen ist, ist damit wertlos.
        await familie_zurueckziehen(sitzung, gespeichert.familie_id)
        raise abgelehnt
    if gespeichert.ablauf_am <= _jetzt():
        raise abgelehnt
    if not gleich(gespeichert.client_id, client_id):
        raise abgelehnt
    if not gleich(gespeichert.redirect_uri, redirect_uri):
        raise abgelehnt

    try:
        abgeleitet = pkce_ableiten(code_verifier)
    except ValueError as fehler:
        raise abgelehnt from fehler
    if not gleich(gespeichert.code_challenge, abgeleitet):
        raise abgelehnt

    gespeichert.eingeloest_am = _jetzt()
    await sitzung.flush()
    return gespeichert


async def familie_zurueckziehen(sitzung: AsyncSession, familie_id: uuid.UUID) -> None:
    """Zieht alle Tokens einer Familie zurueck.

    Hier ist ein Massen-update() richtig und nicht verboten: OAuthToken
    traegt kein onupdate=func.now() (die Zeile "zurueckgezogen_am" wird
    ausdruecklich gesetzt), und es koennen beliebig viele Zeilen betroffen
    sein. Der Constraint aus den Global Constraints betrifft "bundles" und
    "karten" mit ihrem geaendert_am.
    """
    await sitzung.execute(
        update(OAuthToken)
        .where(OAuthToken.familie_id == familie_id, OAuthToken.zurueckgezogen_am.is_(None))
        .values(zurueckgezogen_am=_jetzt())
    )
    await sitzung.flush()


async def tokenpaar_ausgeben(
    sitzung: AsyncSession,
    client_id: str,
    familie_id: uuid.UUID,
    scope: str,
    resource: str | None,
) -> tuple[str, str, int]:
    """Gibt einen Zugriffs- und einen Erneuerungstoken aus.

    Returns:
        (Zugriffstoken, Erneuerungstoken, Gueltigkeit des Zugriffstokens in
        Sekunden) - alle drei so, wie sie in die Token-Antwort gehoeren.
    """
    zugriff = neues_geheimnis()
    erneuerung = neues_geheimnis()
    jetzt = _jetzt()
    for wert, art, dauer in (
        (zugriff, ART_ZUGRIFF, ZUGRIFF_GUELTIGKEIT),
        (erneuerung, ART_ERNEUERUNG, ERNEUERUNG_GUELTIGKEIT),
    ):
        sitzung.add(
            OAuthToken(
                token_hash=pfeffern(wert),
                art=art,
                client_id=client_id,
                familie_id=familie_id,
                scope=scope,
                resource=resource,
                ablauf_am=jetzt + dauer,
            )
        )
    await sitzung.flush()
    return zugriff, erneuerung, int(ZUGRIFF_GUELTIGKEIT.total_seconds())


async def erneuern(
    sitzung: AsyncSession, erneuerungstoken: str, client_id: str
) -> tuple[str, str, int]:
    """Rotiert ein Tokenpaar. Der alte Erneuerungstoken wird dabei ungueltig.

    Raises:
        OAuthFehler: Immer mit "invalid_grant", siehe code_einloesen().
    """
    abgelehnt = OAuthFehler(
        "invalid_grant",
        "Der Erneuerungstoken ist ungueltig, abgelaufen oder wurde bereits "
        "benutzt. Bitte verbinde den Connector noch einmal.",
    )

    gespeichert = await sitzung.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == pfeffern(erneuerungstoken),
            OAuthToken.art == ART_ERNEUERUNG,
        )
    )
    if gespeichert is None:
        raise abgelehnt
    if gespeichert.zurueckgezogen_am is not None:
        # Wiederverwendung eines bereits rotierten Tokens: Der Token war in
        # fremden Haenden. Auch das frisch ausgegebene Paar wird wertlos,
        # sonst arbeitete der Dieb mit dem neueren weiter.
        await familie_zurueckziehen(sitzung, gespeichert.familie_id)
        raise abgelehnt
    if gespeichert.ablauf_am <= _jetzt():
        raise abgelehnt
    if not gleich(gespeichert.client_id, client_id):
        raise abgelehnt

    gespeichert.zurueckgezogen_am = _jetzt()
    await sitzung.flush()
    return await tokenpaar_ausgeben(
        sitzung,
        client_id=gespeichert.client_id,
        familie_id=gespeichert.familie_id,
        scope=gespeichert.scope,
        resource=gespeichert.resource,
    )


async def zugriffstoken_pruefen(sitzung: AsyncSession, token: str) -> OAuthToken | None:
    """Der Zugriffstoken, wenn er gilt - sonst None.

    Ein Erneuerungstoken kommt hier nie durch: die Art wird mitgeprueft.
    """
    gespeichert = await sitzung.scalar(
        select(OAuthToken).where(
            OAuthToken.token_hash == pfeffern(token),
            OAuthToken.art == ART_ZUGRIFF,
        )
    )
    if gespeichert is None:
        return None
    if gespeichert.zurueckgezogen_am is not None:
        return None
    if gespeichert.ablauf_am <= _jetzt():
        return None
    return gespeichert
```

- [ ] **Step 8: Den hässlichen Import im Test glattziehen**

In `tests/test_oauth_speicher.py` die Zeile mit `__import__("app.oauth.modelle", ...)` durch einen echten Import ersetzen: oben `from app.oauth.modelle import OAuthCode` ergänzen und im Test schreiben:

```python
    gespeichert = await session.scalar(select(OAuthCode))
```

- [ ] **Step 9: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_speicher.py -q
```
Erwartet: PASS (13 Tests).

- [ ] **Step 10: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/oauth/geheimnisse.py app/oauth/speicher.py tests/test_oauth_geheimnisse.py tests/test_oauth_speicher.py
git commit -m "OAuth-Geheimnisse und Speicher: Codes, rotierende Tokens, Familienwiderruf"
```
Erwartet vor dem Commit: `148 passed`, 0 übersprungen, 0 Warnungen.

---

### Task 4: Die beiden Discovery-Dokumente

Der Einstieg in den ganzen Ablauf. Claude liest zuerst die Protected-Resource-Metadaten, dann die des Autorisierungsservers. Beide Dokumente entstehen **ausschließlich aus `BASE_URL`** – kein Header wird gelesen. Und das Feld `resource` muss laut Spec **exakt** der URL entsprechen, die die Lehrerin eingetragen hat.

**Files:**
- Create: `app/oauth/metadaten.py`, `app/routen/oauth.py`, `tests/test_oauth_metadaten.py`
- Modify: `app/main.py`, `tests/conftest.py` (Fixture `konfiguration`)
- Test: `tests/test_oauth_metadaten.py`

**Interfaces:**
- Consumes: `app.config.get_settings`, `app.config.Settings.base_url`
- Produces:
  - `app.oauth.metadaten.SCOPE = "lernseiten"`
  - `app.oauth.metadaten.MCP_PFAD = "/mcp"`
  - `app.oauth.metadaten.resource_url(basis_url: str) -> str`
  - `app.oauth.metadaten.geschuetzte_resource(basis_url: str) -> dict`
  - `app.oauth.metadaten.autorisierungsserver(basis_url: str) -> dict`
  - `app.routen.oauth.router` (APIRouter), eingehängt in `app/main.py` **vor** `lernseite.router`
  - Fixture `konfiguration` in `tests/conftest.py`: setzt `BASE_URL`, `APP_SECRET`, `TEACHER_PASSWORD` auf feste Testwerte und leert den `lru_cache` von `get_settings` davor und danach

- [ ] **Step 1: Die Fixture `konfiguration` in `tests/conftest.py` ergänzen**

```python
# Feste Testwerte fuer alles, was aus der Konfiguration kommt. Sie stehen hier
# und nicht in einzelnen Tests, damit dieselben Werte ueberall gelten - eine
# OAuth-Antwort haengt an mehreren davon gleichzeitig.
TEST_BASIS_URL = "https://karten.example.de"
TEST_APP_SECRET = "test-schluessel-nur-fuer-die-suite"
TEST_LEHRERINNEN_PASSWORT = "test-passwort-nur-fuer-die-suite"


@pytest.fixture
def konfiguration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Setzt feste Werte fuer BASE_URL, APP_SECRET und TEACHER_PASSWORD.

    Ohne diese Fixture haengt jeder OAuth-Test an dem, was gerade in der
    lokalen .env oder in der CI steht - lokal https://karten.example.de, in
    der CI http://localhost:8000. Ein Test, der die erzeugten URLs prueft,
    waere dann an einem der beiden Orte rot.

    get_settings ist lru_cache-dekoriert und muss deshalb VOR und NACH dem
    Setzen geleert werden: davor, damit die neuen Werte greifen, danach,
    damit der naechste Test nicht die Testwerte erbt.
    """
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("BASE_URL", TEST_BASIS_URL)
    monkeypatch.setenv("APP_SECRET", TEST_APP_SECRET)
    monkeypatch.setenv("TEACHER_PASSWORD", TEST_LEHRERINNEN_PASSWORT)
    yield
    get_settings.cache_clear()
```

- [ ] **Step 2: Die Tests schreiben**

`tests/test_oauth_metadaten.py`:

```python
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
```

- [ ] **Step 3: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_metadaten.py -q
```
Erwartet: 6-mal FAIL mit 404 – die Routen gibt es noch nicht.

- [ ] **Step 4: `app/oauth/metadaten.py` schreiben**

```python
"""Die beiden Discovery-Dokumente, gebaut aus BASE_URL.

An dieser Stelle wird bewusst KEIN Request angefasst. Der Container startet
uvicorn mit --forwarded-allow-ips='*' (siehe docker/app-start.sh), weil
hinter Coolify ein Reverse Proxy sitzt; X-Forwarded-Host und
X-Forwarded-Proto sind damit von aussen setzbar. Wuerde "resource" aus einem
Header entstehen, koennte jeder Aufrufer bestimmen, welche Adresse Claude
fuer die geschuetzte Resource haelt. Die Spec verlangt in Abschnitt 5, dass
"resource" exakt der URL entspricht, die die Lehrerin eingetragen hat - und
das ist BASE_URL.
"""

SCOPE = "lernseiten"
MCP_PFAD = "/mcp"


def resource_url(basis_url: str) -> str:
    """Die Adresse, die die Lehrerin in Cowork eintraegt."""
    return f"{basis_url}{MCP_PFAD}"


def geschuetzte_resource(basis_url: str) -> dict:
    """Das Dokument nach RFC 9728."""
    return {
        "resource": resource_url(basis_url),
        "authorization_servers": [basis_url],
        "scopes_supported": [SCOPE],
        "bearer_methods_supported": ["header"],
    }


def autorisierungsserver(basis_url: str) -> dict:
    """Das Dokument nach RFC 8414.

    token_endpoint_auth_methods_supported ist "none": Claude registriert sich
    als oeffentlicher Client und weist sich ueber PKCE aus, nicht ueber ein
    Client-Geheimnis. Ein Geheimnis, das in einer Cloud-Anwendung liegt, waere
    ohnehin keines.
    """
    return {
        "issuer": basis_url,
        "authorization_endpoint": f"{basis_url}/oauth/authorize",
        "token_endpoint": f"{basis_url}/oauth/token",
        "registration_endpoint": f"{basis_url}/oauth/register",
        "scopes_supported": [SCOPE],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["none"],
        "code_challenge_methods_supported": ["S256"],
    }
```

- [ ] **Step 5: `app/routen/oauth.py` mit den beiden Routen anlegen**

```python
"""Die HTTP-Seite des OAuth-Servers.

Bewusst gewoehnliche FastAPI-Routen und nicht @mcp.custom_route(): So laufen
sie unter denselben Schutzkoepfen und demselben deutschen 404-Handler wie der
Rest der Anwendung.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.oauth.metadaten import autorisierungsserver, geschuetzte_resource

router = APIRouter()

# Die Verbindungsmaske von claude.ai laeuft im Browser und holt die
# Discovery-Dokumente per fetch. Ohne diesen Kopf bricht sie mit einer
# Meldung ab, die nichts ueber die Ursache sagt. Die Dokumente sind
# oeffentlich und enthalten nichts Schuetzenswertes - "*" ist hier richtig
# und nicht bequem.
OEFFENTLICH = {"Access-Control-Allow-Origin": "*"}


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadaten() -> JSONResponse:
    """Zwei Pfade, ein Dokument.

    RFC 9728 Abschnitt 3.1 verlangt fuer die Resource BASE_URL/mcp den Pfad
    mit angehaengtem /mcp - und genau den nennt auch der
    WWW-Authenticate-Kopf, den das MCP-SDK schickt. Die Spec fuehrt in
    Abschnitt 3 den kurzen Pfad. Es gibt beide, damit keiner ins Leere
    laeuft.
    """
    return JSONResponse(
        geschuetzte_resource(get_settings().base_url), headers=OEFFENTLICH
    )


@router.get("/.well-known/oauth-authorization-server")
async def autorisierungsserver_metadaten() -> JSONResponse:
    return JSONResponse(
        autorisierungsserver(get_settings().base_url), headers=OEFFENTLICH
    )
```

- [ ] **Step 6: Den Router in `app/main.py` einhängen**

In `app/main.py` den Import ergänzen und den Router **vor** `lernseite.router` einhängen:

```python
from app.routen import lernseite, oauth, system
```

```python
app.include_router(system.router)
app.include_router(oauth.router)
# Muss als letzter kommen: /{slug} ist zwar durch ein Muster begrenzt, aber
# eine spaetere Route mit gleicher Form wuerde sonst verdeckt.
app.include_router(lernseite.router)
```

- [ ] **Step 7: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_metadaten.py -q
```
Erwartet: PASS (6 Tests).

- [ ] **Step 8: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/oauth/metadaten.py app/routen/oauth.py app/main.py tests/conftest.py tests/test_oauth_metadaten.py
git commit -m "Discovery-Dokumente aus BASE_URL, unter beiden Well-Known-Pfaden"
```
Erwartet vor dem Commit: `154 passed`, 0 übersprungen, 0 Warnungen.

---

### Task 5: Dynamische Registrierung

Claude meldet sich selbst an (RFC 7591). Der Endpunkt ist **unauthentifiziert** – das ist so vorgesehen. Der Schutz liegt darin, dass eine Registrierung für sich genommen nichts wert ist: Ohne das Passwort der Lehrerin auf der Zustimmungsseite bekommt ein registrierter Client nie einen Token.

**Files:**
- Create: `app/oauth/redirect.py`, `tests/test_oauth_redirect.py`, `tests/test_oauth_registrierung.py`
- Modify: `app/routen/oauth.py`
- Test: `tests/test_oauth_redirect.py`, `tests/test_oauth_registrierung.py`

**Interfaces:**
- Consumes: `app.oauth.speicher.client_anlegen`, `app.db.get_session`
- Produces:
  - `app.oauth.redirect.CLAUDE_RUECKSPRUNG = "https://claude.ai/api/mcp/auth_callback"`
  - `app.oauth.redirect.registrierbar(uri: str) -> bool`
  - `app.oauth.redirect.passt(angefragt: str, registrierte: list[str]) -> bool`
  - `POST /oauth/register` → 201 mit `client_id`, `client_id_issued_at`, `redirect_uris`, `token_endpoint_auth_method`, `grant_types`, `response_types`, `scope`, `client_name`

- [ ] **Step 1: Die Tests für `redirect.py` schreiben**

`tests/test_oauth_redirect.py`:

```python
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
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_redirect.py -q
```
Erwartet: FAIL, `No module named 'app.oauth.redirect'`.

- [ ] **Step 3: `app/oauth/redirect.py` schreiben**

```python
"""Welche Rueckadressen erlaubt sind - und warum genau diese drei.

Die Spec nennt in Abschnitt 5:
  - https://claude.ai/api/mcp/auth_callback  (Cowork und claude.ai)
  - http://localhost/callback  mit ignoriertem Port  (Claude Code)
  - http://127.0.0.1/callback  mit ignoriertem Port  (Claude Code)

Der ignorierte Port ist keine Nachlaessigkeit: Claude Code oeffnet beim
Verbinden einen lokalen Server auf einem freien Port und kann deshalb nicht
vorher registrieren, welcher es sein wird. RFC 8252 Abschnitt 7.3 sieht
genau diese Ausnahme fuer Loopback-Adressen vor. Sie ist harmlos, weil eine
Loopback-Adresse nur auf dem Rechner der Nutzerin selbst erreichbar ist.

Fuer alles andere gilt exakter Zeichenvergleich. Insbesondere gibt es keine
Praefix-Pruefung wie startswith("https://claude.ai"): Damit waere
https://claude.ai.boese.example erlaubt.
"""

from urllib.parse import urlsplit

CLAUDE_RUECKSPRUNG = "https://claude.ai/api/mcp/auth_callback"

# Nur diese beiden Hostnamen, nur ueber http, nur mit diesem Pfad. "[::1]"
# steht nicht in der Spec und wird deshalb nicht ergaenzt - was hier steht,
# steht auch in der Werkzeug- und Betriebsdokumentation.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
LOOPBACK_PFAD = "/callback"


def _loopback_kennung(uri: str) -> tuple[str, str] | None:
    """(Host, Pfad) einer erlaubten Loopback-Adresse, sonst None.

    Der Port faellt dabei absichtlich weg - er ist die eine Angabe, die
    ignoriert wird.
    """
    teile = urlsplit(uri)
    if teile.scheme != "http":
        return None
    if teile.hostname not in LOOPBACK_HOSTS:
        return None
    if teile.path != LOOPBACK_PFAD:
        return None
    if teile.query or teile.fragment or teile.username or teile.password:
        return None
    return teile.hostname, teile.path


def registrierbar(uri: str) -> bool:
    """Ob diese Adresse ueberhaupt registriert werden darf."""
    if uri == CLAUDE_RUECKSPRUNG:
        return True
    return _loopback_kennung(uri) is not None


def passt(angefragt: str, registrierte: list[str]) -> bool:
    """Ob die angefragte Adresse zu einer der registrierten passt.

    Exakter Vergleich - ausser bei Loopback, wo der Port ausgenommen ist.
    """
    if angefragt in registrierte:
        return True
    kennung = _loopback_kennung(angefragt)
    if kennung is None:
        return False
    return any(_loopback_kennung(eine) == kennung for eine in registrierte)
```

- [ ] **Step 4: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_redirect.py -q
```
Erwartet: PASS (16 Tests).

- [ ] **Step 5: Die Tests für die Registrierung schreiben**

`tests/test_oauth_registrierung.py`:

```python
"""Tests fuer POST /oauth/register (RFC 7591).

Der Endpunkt ist unauthentifiziert - so ist Dynamic Client Registration
gedacht. Eine Registrierung allein ist wertlos: Ohne das Passwort der
Lehrerin auf der Zustimmungsseite bekommt der Client nie einen Token.
"""

from app.oauth.redirect import CLAUDE_RUECKSPRUNG


def _registrieren(client, **abweichungen):
    koerper = {
        "client_name": "Claude",
        "redirect_uris": [CLAUDE_RUECKSPRUNG],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    koerper.update(abweichungen)
    return client.post("/oauth/register", json=koerper)


def test_registrierung_gibt_eine_client_id_zurueck(client, konfiguration):
    antwort = _registrieren(client)
    assert antwort.status_code == 201
    daten = antwort.json()
    assert len(daten["client_id"]) >= 20
    assert daten["redirect_uris"] == [CLAUDE_RUECKSPRUNG]
    assert daten["token_endpoint_auth_method"] == "none"
    assert daten["grant_types"] == ["authorization_code", "refresh_token"]
    assert daten["response_types"] == ["code"]
    assert daten["scope"] == "lernseiten"
    assert isinstance(daten["client_id_issued_at"], int)


def test_kein_client_secret_in_der_antwort(client, konfiguration):
    """Oeffentlicher Client mit PKCE. Ein Geheimnis in Anthropics Cloud waere
    keines - und die Metadaten sagen token_endpoint_auth_method: none."""
    assert "client_secret" not in _registrieren(client).json()


def test_zwei_registrierungen_ergeben_zwei_ids(client, konfiguration):
    erste = _registrieren(client).json()["client_id"]
    zweite = _registrieren(client).json()["client_id"]
    assert erste != zweite


def test_fremde_rueckadresse_wird_abgelehnt(client, konfiguration):
    antwort = _registrieren(client, redirect_uris=["https://boese.example/callback"])
    assert antwort.status_code == 400
    daten = antwort.json()
    assert daten["error"] == "invalid_redirect_uri"
    assert "boese.example" in daten["error_description"]
    assert "claude.ai" in daten["error_description"]


def test_eine_gute_und_eine_schlechte_adresse_wird_abgelehnt(client, konfiguration):
    """Alles oder nichts - sonst haette der Client eine Adresse registriert,
    von der er annimmt, sie sei erlaubt."""
    antwort = _registrieren(
        client, redirect_uris=[CLAUDE_RUECKSPRUNG, "https://boese.example/callback"]
    )
    assert antwort.status_code == 400


def test_leere_liste_wird_abgelehnt(client, konfiguration):
    antwort = _registrieren(client, redirect_uris=[])
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_redirect_uri"


def test_fehlendes_feld_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/register", json={"client_name": "Claude"})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_client_metadata"


def test_registrierung_ist_von_ueberall_aufrufbar(client, konfiguration):
    assert _registrieren(client).headers["access-control-allow-origin"] == "*"


def test_die_antwort_wird_nicht_zwischengespeichert(client, konfiguration):
    assert _registrieren(client).headers["cache-control"] == "no-store"
```

- [ ] **Step 6: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_registrierung.py -q
```
Erwartet: 9-mal FAIL mit 404.

- [ ] **Step 7: Den Registrierungsendpunkt in `app/routen/oauth.py` ergänzen**

Oben ergänzen:

```python
import time

from fastapi import Depends, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.oauth.metadaten import SCOPE
from app.oauth.redirect import CLAUDE_RUECKSPRUNG, registrierbar
from app.oauth.speicher import client_anlegen

# Alle Antworten mit Geheimnissen darin duerfen nirgends liegenbleiben.
NICHT_SPEICHERN = {"Cache-Control": "no-store", "Pragma": "no-cache"}
```

Und unten anhängen:

```python
class Registrierungswunsch(BaseModel):
    """Die Felder aus RFC 7591, die dieser Server auswertet.

    Alles Weitere (client_uri, logo_uri, contacts, ...) darf mitgeschickt
    werden und wird stillschweigend ignoriert - RFC 7591 Abschnitt 3.1
    erlaubt das ausdruecklich, und ein Server, der an einem unbekannten Feld
    scheitert, ist mit dem naechsten Claude-Update kaputt.
    """

    model_config = {"extra": "ignore"}

    redirect_uris: list[str]
    client_name: str | None = None


def _fehler(code: str, beschreibung: str, status: int = 400) -> JSONResponse:
    """Eine Ablehnung im Format aus RFC 6749 Abschnitt 5.2.

    error ist der maschinenlesbare Code, error_description der deutsche
    Klartext - Claude zeigt ihn der Lehrerin an.
    """
    return JSONResponse(
        {"error": code, "error_description": beschreibung},
        status_code=status,
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )


@router.post("/oauth/register")
async def registrieren(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> JSONResponse:
    """Dynamic Client Registration (RFC 7591).

    Der Koerper wird von Hand gelesen statt ueber ein Pydantic-Modell im
    Funktionskopf: FastAPI beantwortet ein ungueltiges Modell mit 422 und
    einer englischen Pydantic-Fehlerliste. RFC 7591 verlangt hier 400 mit
    einem "error"-Feld, und Claude wertet genau das aus.
    """
    try:
        rohdaten = await anfrage.json()
    except ValueError:
        return _fehler(
            "invalid_client_metadata",
            "Der Anfragekoerper ist kein gueltiges JSON.",
        )
    try:
        wunsch = Registrierungswunsch.model_validate(rohdaten)
    except ValidationError:
        return _fehler(
            "invalid_client_metadata",
            "Die Anfrage braucht das Feld 'redirect_uris' mit mindestens "
            "einer Rueckadresse.",
        )

    if not wunsch.redirect_uris:
        return _fehler(
            "invalid_redirect_uri",
            "Es wurde keine Rueckadresse angegeben. Erlaubt sind "
            f"{CLAUDE_RUECKSPRUNG} sowie http://localhost/callback und "
            "http://127.0.0.1/callback.",
        )
    for uri in wunsch.redirect_uris:
        if not registrierbar(uri):
            return _fehler(
                "invalid_redirect_uri",
                f"Die Rueckadresse {uri!r} ist auf diesem Server nicht "
                f"erlaubt. Erlaubt sind {CLAUDE_RUECKSPRUNG} sowie "
                "http://localhost/callback und http://127.0.0.1/callback "
                "(der Port darf dort abweichen).",
            )

    kunde = await client_anlegen(
        sitzung, client_name=wunsch.client_name, redirect_uris=wunsch.redirect_uris
    )
    await sitzung.commit()

    return JSONResponse(
        {
            "client_id": kunde.client_id,
            "client_id_issued_at": int(time.time()),
            "client_name": kunde.client_name,
            "redirect_uris": list(kunde.redirect_uris),
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
        status_code=201,
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )
```

- [ ] **Step 8: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_registrierung.py tests/test_oauth_redirect.py -q
```
Erwartet: PASS (25 Tests).

- [ ] **Step 9: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/oauth/redirect.py app/routen/oauth.py tests/test_oauth_redirect.py tests/test_oauth_registrierung.py
git commit -m "Dynamische Clientregistrierung mit strenger Pruefung der Rueckadressen"
```
Erwartet vor dem Commit: `179 passed`, 0 übersprungen, 0 Warnungen.

---

### Task 6: Die Zustimmungsseite

Die einzige Seite dieses Projekts, die die Lehrerin selbst zu sehen bekommt – und die einzige mit einem Formular. Deshalb muss hier auch die Content-Security-Policy angefasst werden: Die bestehende Richtlinie enthält `form-action 'none'` und würde das Absenden des Passworts **und** die anschließende Weiterleitung zu `claude.ai` blockieren.

**Files:**
- Create: `app/templates/zustimmung.html`, `app/static/zustimmung.css`, `tests/test_oauth_autorisierung.py`
- Modify: `app/routen/oauth.py`, `app/sicherheit.py`, `tests/test_sicherheit.py`
- Test: `tests/test_oauth_autorisierung.py`, `tests/test_sicherheit.py`

**Interfaces:**
- Consumes: `app.oauth.speicher.client_holen`, `app.oauth.speicher.code_ausgeben`, `app.oauth.redirect.passt`, `app.templates.rendern`
- Produces:
  - `GET /oauth/authorize` → HTML-Formular (200) oder Weiterleitung mit `error=` (302) oder deutsche Fehlerseite (400)
  - `POST /oauth/authorize` → Weiterleitung mit `code=` und `state=` (302) oder Formular erneut (401)
  - `app.sicherheit.ZUSTIMMUNG_RICHTLINIE`
  - `app.sicherheit.OHNE_RICHTLINIE` – die Pfade, die keine Richtlinie bekommen (`{"/mcp"}`)

- [ ] **Step 1: Die Tests schreiben**

`tests/test_oauth_autorisierung.py`:

```python
"""Tests fuer GET/POST /oauth/authorize.

Die Reihenfolge der Pruefungen ist hier sicherheitsrelevant und wird
mitgetestet: Solange nicht feststeht, dass die Rueckadresse zu einem
registrierten Client gehoert, darf NICHTS dorthin weitergeleitet werden -
auch kein Fehler. Sonst waere der Server ein offener Weiterleiter.
"""

from urllib.parse import parse_qs, urlsplit

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.redirect import CLAUDE_RUECKSPRUNG
from tests.conftest import TEST_LEHRERINNEN_PASSWORT


def _client_id(client) -> str:
    antwort = client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_RUECKSPRUNG]},
    )
    return antwort.json()["client_id"]


def _parameter(client_id: str, verifier: str, **abweichungen) -> dict:
    werte = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CLAUDE_RUECKSPRUNG,
        "scope": "lernseiten",
        "state": "zustand-123",
        "code_challenge": pkce_ableiten(verifier),
        "code_challenge_method": "S256",
        "resource": "https://karten.example.de/mcp",
    }
    werte.update(abweichungen)
    return {name: wert for name, wert in werte.items() if wert is not None}


def test_die_seite_fragt_nach_dem_passwort(client, konfiguration):
    kennung = _client_id(client)
    antwort = client.get("/oauth/authorize", params=_parameter(kennung, neues_geheimnis()))
    assert antwort.status_code == 200
    assert 'type="password"' in antwort.text
    assert "Lernseiten" in antwort.text


def test_die_seite_traegt_die_parameter_verborgen_weiter(client, konfiguration):
    """Sonst waeren sie nach dem Absenden weg und der Ablauf braeche ab."""
    kennung = _client_id(client)
    verifier = neues_geheimnis()
    werte = _parameter(kennung, verifier)
    text = client.get("/oauth/authorize", params=werte).text
    for name in ("client_id", "redirect_uri", "state", "code_challenge", "resource"):
        assert f'name="{name}"' in text
    assert werte["code_challenge"] in text


def test_unbekannter_client_bekommt_eine_deutsche_seite_ohne_weiterleitung(
    client, konfiguration
):
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter("gibt-es-nicht", neues_geheimnis()),
        follow_redirects=False,
    )
    assert antwort.status_code == 400
    assert "location" not in antwort.headers
    assert "nicht bekannt" in antwort.text


def test_fremde_rueckadresse_wird_nicht_angesteuert(client, konfiguration):
    """Der Test gegen den offenen Weiterleiter."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(
            kennung, neues_geheimnis(), redirect_uri="https://boese.example/callback"
        ),
        follow_redirects=False,
    )
    assert antwort.status_code == 400
    assert "location" not in antwort.headers


def test_fehlende_pkce_angabe_wird_zur_rueckadresse_gemeldet(client, konfiguration):
    """Ab hier ist die Rueckadresse geprueft, also darf der Fehler dorthin."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), code_challenge=None),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    ziel = urlsplit(antwort.headers["location"])
    assert f"{ziel.scheme}://{ziel.netloc}{ziel.path}" == CLAUDE_RUECKSPRUNG
    parameter = parse_qs(ziel.query)
    assert parameter["error"] == ["invalid_request"]
    assert parameter["state"] == ["zustand-123"]


def test_pkce_ohne_s256_wird_abgelehnt(client, konfiguration):
    """Die Metadaten nennen ausschliesslich S256. "plain" waere kein Schutz."""
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), code_challenge_method="plain"),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    assert parse_qs(urlsplit(antwort.headers["location"]).query)["error"] == [
        "invalid_request"
    ]


def test_falscher_response_type_wird_abgelehnt(client, konfiguration):
    kennung = _client_id(client)
    antwort = client.get(
        "/oauth/authorize",
        params=_parameter(kennung, neues_geheimnis(), response_type="token"),
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    assert parse_qs(urlsplit(antwort.headers["location"]).query)["error"] == [
        "unsupported_response_type"
    ]


def test_richtiges_passwort_liefert_einen_code(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": TEST_LEHRERINNEN_PASSWORT},
        follow_redirects=False,
    )
    assert antwort.status_code == 302
    parameter = parse_qs(urlsplit(antwort.headers["location"]).query)
    assert len(parameter["code"][0]) == 43
    assert parameter["state"] == ["zustand-123"]


def test_falsches_passwort_zeigt_die_seite_erneut(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": "falsch"},
        follow_redirects=False,
    )
    assert antwort.status_code == 401
    assert "Das Passwort stimmt nicht" in antwort.text
    assert 'type="password"' in antwort.text
    assert "location" not in antwort.headers


def test_das_passwort_steht_nie_in_der_antwort(client, konfiguration):
    kennung = _client_id(client)
    werte = _parameter(kennung, neues_geheimnis())
    antwort = client.post(
        "/oauth/authorize",
        data={**werte, "passwort": TEST_LEHRERINNEN_PASSWORT},
        follow_redirects=False,
    )
    assert TEST_LEHRERINNEN_PASSWORT not in antwort.text
    assert TEST_LEHRERINNEN_PASSWORT not in antwort.headers.get("location", "")


def test_die_zustimmungsseite_erlaubt_ihr_eigenes_formular(client, konfiguration):
    """Ohne diese Ausnahme blockiert die Richtlinie das Absenden.

    Die bestehende Richtlinie enthaelt form-action 'none'. Sie gilt fuer das
    Ziel des Formulars UND fuer die Weiterleitung danach - beide muessen
    erlaubt sein, sonst bricht der Ablauf im Browser ab, ohne dass am Server
    etwas auffiele.
    """
    kennung = _client_id(client)
    richtlinie = client.get(
        "/oauth/authorize", params=_parameter(kennung, neues_geheimnis())
    ).headers["content-security-policy"]
    assert "form-action 'self' https://claude.ai" in richtlinie
    assert "http://localhost:*" in richtlinie
    assert "http://127.0.0.1:*" in richtlinie
    assert "form-action 'none'" not in richtlinie
```

- [ ] **Step 2: Den Gegentest in `tests/test_sicherheit.py` ergänzen**

An `tests/test_sicherheit.py` anhängen:

```python
def test_die_lockere_richtlinie_gilt_nur_fuer_die_zustimmungsseite():
    """Die Ausnahme darf nicht auf die Lernseite abfaerben.

    Auf der Lernseite steht der JSON-Datenblock mit Inhalten, die ueber MCP
    hereingekommen sind. Ein Formular hat sie nicht - form-action 'none'
    bleibt dort die richtige Angabe.
    """
    from app.sicherheit import RICHTLINIE, ZUSTIMMUNG_RICHTLINIE

    assert "form-action 'none'" in RICHTLINIE
    assert "claude.ai" not in RICHTLINIE
    assert "form-action 'none'" not in ZUSTIMMUNG_RICHTLINIE
```

- [ ] **Step 3: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_autorisierung.py tests/test_sicherheit.py -q
```
Erwartet: die neuen Tests scheitern (404 bzw. `ImportError`), die vier bestehenden aus `test_sicherheit.py` bleiben grün.

- [ ] **Step 4: `app/sicherheit.py` umbauen**

Unter `RICHTLINIE` ergänzen und `dispatch` ersetzen:

```python
# Die Zustimmungsseite ist die einzige Seite dieses Projekts mit einem
# Formular. form-action gilt fuer das Ziel des Formulars UND fuer jede
# Weiterleitung, die daraus folgt - deshalb steht hier neben 'self' auch
# claude.ai (die Rueckadresse von Cowork) und die beiden Loopback-Adressen
# (Claude Code, dessen Port beim Start zufaellig ist; CSP erlaubt dafuer
# den Platzhalter :*). Ohne diese Ausnahme braeche der Ablauf im Browser ab,
# ohne dass am Server irgendetwas auffiele.
ZUSTIMMUNG_RICHTLINIE = RICHTLINIE.replace(
    "form-action 'none'",
    "form-action 'self' https://claude.ai http://localhost:* http://127.0.0.1:*",
)

# Der MCP-Endpunkt liefert kein Dokument, sondern JSON-RPC ueber
# Server-Sent-Events. Eine Inhaltsrichtlinie hat dort nichts zu regeln, und
# ein Kopf, den niemand auswertet, ist nur eine weitere Stelle, an der etwas
# schiefgehen kann.
OHNE_RICHTLINIE = frozenset({"/mcp"})

# Der Pfad der Zustimmungsseite. Steht als Konstante da, damit er nicht an
# zwei Stellen (hier und in app/routen/oauth.py) auseinanderlaufen kann.
ZUSTIMMUNG_PFAD = "/oauth/authorize"


class Schutzkoepfe(BaseHTTPMiddleware):
    """Haengt die Richtlinie und zwei weitere Schutzkoepfe an jede Antwort."""

    async def dispatch(self, request, call_next):
        """Laesst die Anfrage durch und ergaenzt die Antwort um die Schutzkoepfe."""
        antwort = await call_next(request)
        antwort.headers["X-Content-Type-Options"] = "nosniff"
        antwort.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path in OHNE_RICHTLINIE:
            return antwort
        antwort.headers["Content-Security-Policy"] = (
            ZUSTIMMUNG_RICHTLINIE
            if request.url.path == ZUSTIMMUNG_PFAD
            else RICHTLINIE
        )
        return antwort
```

- [ ] **Step 5: `app/templates/zustimmung.html` schreiben**

```html
{% extends "basis.html" %}
{% block titel %}Zugriff auf deine Lernseiten{% endblock %}
{% block kopf %}<link rel="stylesheet" href="/static/zustimmung.css">{% endblock %}
{% block inhalt %}
<main class="zustimmung">
  <h1>Möchtest du Claude Zugriff auf deine Lernseiten geben?</h1>
  <p class="erklaerung">
    Claude kann dann Lernpakete anlegen, ändern und deaktivieren. Lernende
    sehen davon nichts – sie bekommen nur die Links, die du weitergibst.
  </p>
  {% if fehler %}<p class="fehler" role="alert">{{ fehler }}</p>{% endif %}
  <form method="post" action="/oauth/authorize">
    {% for name, wert in verborgen.items() %}
    <input type="hidden" name="{{ name }}" value="{{ wert }}">
    {% endfor %}
    <label for="passwort">Dein Passwort</label>
    <input type="password" id="passwort" name="passwort" autocomplete="current-password"
           autofocus required>
    <button type="submit">Zugriff geben</button>
  </form>
</main>
{% endblock %}
```

Die Schleife über `verborgen` setzt die Werte über Jinjas Autoescape ein; ein `| safe` steht hier bewusst nirgends.

- [ ] **Step 6: `app/static/zustimmung.css` schreiben**

```css
/* Dieselbe Bildsprache wie die Lernseite: dunkle Tafel, gelber Zettel.
   Bewusst eine eigene Datei und kein Anbau an lernseite.css - die
   Zustimmungsseite hat mit dem Runner nichts zu tun und soll sich nicht
   mitaendern, wenn dort etwas umgebaut wird. Die Farbwerte sind aus
   docs/design/prototyp.html uebernommen, nicht neu gewaehlt. */
body {
  margin: 0;
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: radial-gradient(120% 90% at 50% 0%, #2a3138 0%, #16191d 70%);
  color: #e8eaed;
  font-family: system-ui, sans-serif;
  padding: 24px;
}

.zustimmung {
  width: min(100%, 30rem);
  background: linear-gradient(158deg, #ffe57a 0%, #ffd23f 100%);
  color: #2b2410;
  border-radius: 10px;
  padding: 28px 26px 32px;
  box-shadow: 0 18px 32px rgba(0, 0, 0, .55);
}

.zustimmung h1 { font-size: 1.3rem; line-height: 1.3; margin: 0 0 12px; }
.erklaerung { margin: 0 0 20px; line-height: 1.5; }
.fehler {
  margin: 0 0 16px;
  padding: 10px 12px;
  border-radius: 6px;
  background: #d1392f;
  border: 1px solid #a72d25;
  color: #fff;
}

label { display: block; font-weight: 600; margin-bottom: 6px; }
input[type="password"] {
  width: 100%;
  box-sizing: border-box;
  font: inherit;
  padding: 12px;
  border: 1px solid #a98c1c;
  border-radius: 6px;
  background: #fff8dc;
  color: #2b2410;
}

button {
  margin-top: 18px;
  width: 100%;
  min-height: 44px;
  font: inherit;
  font-weight: 700;
  color: #fff;
  background: #2f9e52;
  border: 1px solid #257e41;
  border-radius: 6px;
  cursor: pointer;
}
button:focus-visible, input:focus-visible { outline: 3px solid #16191d; outline-offset: 2px; }
```

- [ ] **Step 7: Die beiden Routen in `app/routen/oauth.py` ergänzen**

Imports oben ergänzen:

```python
import secrets

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

from app.oauth.redirect import passt
from app.oauth.speicher import client_holen, code_ausgeben
from app.templates import rendern
```

Und anhängen:

```python
# Die Parameter, die die Zustimmungsseite unveraendert weiterreichen muss.
# passwort steht bewusst NICHT darin: Es wird geprueft und danach vergessen.
DURCHGEREICHT = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
    "resource",
)


def _weiterleitung_mit_fehler(
    redirect_uri: str, code: str, beschreibung: str, state: str | None
) -> RedirectResponse:
    """Ein Fehler, der zur Rueckadresse gehoert (RFC 6749 Abschnitt 4.1.2.1).

    Nur aufrufen, NACHDEM redirect_uri gegen die registrierten Adressen
    geprueft wurde - sonst waere dieser Server ein offener Weiterleiter.
    """
    trenner = "&" if "?" in redirect_uri else "?"
    teile = [f"error={quote(code)}", f"error_description={quote(beschreibung)}"]
    if state is not None:
        teile.append(f"state={quote(state)}")
    return RedirectResponse(redirect_uri + trenner + "&".join(teile), status_code=302)


def _seite_mit_fehler(anfrage: Request, text: str) -> HTMLResponse:
    """Eine deutsche Fehlerseite, wenn NICHT weitergeleitet werden darf."""
    return rendern(
        anfrage,
        "fehler.html",
        status_code=400,
        ueberschrift="Der Verbindungsversuch hat nicht geklappt",
        text=text,
    )


async def _vorpruefen(
    anfrage: Request, werte: dict[str, str | None], sitzung: AsyncSession
) -> HTMLResponse | RedirectResponse | None:
    """Prueft die Anfrage. Gibt eine Antwort zurueck, wenn sie abzulehnen ist.

    Die Reihenfolge ist sicherheitsrelevant: Solange nicht feststeht, dass
    die Rueckadresse zu einem registrierten Client gehoert, geht KEINE
    Antwort dorthin - auch kein Fehler.
    """
    kunde = await client_holen(sitzung, werte["client_id"] or "")
    if kunde is None:
        return _seite_mit_fehler(
            anfrage,
            "Der Client, der sich verbinden will, ist diesem Server nicht "
            "bekannt. Bitte entferne den Connector in Claude und fuege ihn "
            "noch einmal hinzu.",
        )

    redirect_uri = werte["redirect_uri"]
    if not redirect_uri or not passt(redirect_uri, list(kunde.redirect_uris)):
        return _seite_mit_fehler(
            anfrage,
            "Die Rueckadresse der Anfrage gehoert nicht zu diesem Client. "
            "Bitte entferne den Connector in Claude und fuege ihn noch "
            "einmal hinzu.",
        )

    state = werte["state"]
    if werte["response_type"] != "code":
        return _weiterleitung_mit_fehler(
            redirect_uri,
            "unsupported_response_type",
            "Dieser Server kennt nur den Ablauf mit Autorisierungscode "
            "(response_type=code).",
            state,
        )
    if not werte["code_challenge"] or werte["code_challenge_method"] != "S256":
        return _weiterleitung_mit_fehler(
            redirect_uri,
            "invalid_request",
            "Dieser Server verlangt PKCE mit der Methode S256.",
            state,
        )
    return None


@router.get("/oauth/authorize", response_class=HTMLResponse)
async def zustimmung_zeigen(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> HTMLResponse | RedirectResponse:
    werte = {name: anfrage.query_params.get(name) for name in DURCHGEREICHT}
    abgelehnt = await _vorpruefen(anfrage, werte, sitzung)
    if abgelehnt is not None:
        return abgelehnt
    return rendern(
        anfrage,
        "zustimmung.html",
        verborgen={name: wert for name, wert in werte.items() if wert is not None},
        fehler=None,
    )


@router.post("/oauth/authorize")
async def zustimmung_erteilen(
    anfrage: Request,
    passwort: str = Form(default=""),
    sitzung: AsyncSession = Depends(get_session),
) -> HTMLResponse | RedirectResponse:
    formular = await anfrage.form()
    werte = {name: formular.get(name) for name in DURCHGEREICHT}
    abgelehnt = await _vorpruefen(anfrage, werte, sitzung)
    if abgelehnt is not None:
        return abgelehnt

    # secrets.compare_digest statt "==": Ein gewoehnlicher Vergleich bricht
    # beim ersten falschen Zeichen ab und verraet ueber die Laufzeit, wie
    # viele Zeichen stimmten.
    if not secrets.compare_digest(passwort, get_settings().teacher_password):
        return rendern(
            anfrage,
            "zustimmung.html",
            status_code=401,
            verborgen={name: wert for name, wert in werte.items() if wert is not None},
            fehler="Das Passwort stimmt nicht. Bitte versuche es noch einmal.",
        )

    kunde = await client_holen(sitzung, werte["client_id"])
    code = await code_ausgeben(
        sitzung,
        client=kunde,
        redirect_uri=werte["redirect_uri"],
        code_challenge=werte["code_challenge"],
        resource=werte["resource"],
    )
    await sitzung.commit()

    ziel = werte["redirect_uri"]
    trenner = "&" if "?" in ziel else "?"
    teile = [f"code={quote(code)}"]
    if werte["state"] is not None:
        teile.append(f"state={quote(werte['state'])}")
    return RedirectResponse(ziel + trenner + "&".join(teile), status_code=302)
```

Und ganz oben bei den Imports:

```python
from urllib.parse import quote
```

- [ ] **Step 8: Tests laufen lassen**

```bash
uv run pytest tests/test_oauth_autorisierung.py tests/test_sicherheit.py -q
```
Erwartet: PASS (11 + 5 Tests).

- [ ] **Step 9: Die Seite einmal mit eigenen Augen ansehen**

```bash
uv run uvicorn app.main:app --port 8001
```
Dann im Browser öffnen (Adresse in einer Zeile, `<ID>` durch eine echte Client-ID aus einer Registrierung ersetzen):

```
http://localhost:8001/oauth/authorize?response_type=code&client_id=<ID>&redirect_uri=https%3A%2F%2Fclaude.ai%2Fapi%2Fmcp%2Fauth_callback&scope=lernseiten&state=abc&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
```

Prüfen: Die Seite ist auf einem schmalen Fenster (390 px) ohne waagerechtes Scrollen lesbar, das Passwortfeld hat den Fokus, der Knopf ist mindestens 44 px hoch, und die Entwicklerkonsole meldet keinen CSP-Verstoß. Danach den Server beenden.

- [ ] **Step 10: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/templates/zustimmung.html app/static/zustimmung.css app/routen/oauth.py app/sicherheit.py tests/test_oauth_autorisierung.py tests/test_sicherheit.py
git commit -m "Zustimmungsseite mit Passwortpruefung, PKCE-Vorpruefung und eigener Inhaltsrichtlinie"
```
Erwartet vor dem Commit: `191 passed`, 0 übersprungen, 0 Warnungen.

---

### Task 7: Der Token-Endpunkt

Der letzte Baustein des Autorisierungsservers. Danach ist der komplette OAuth-Ablauf ohne MCP durchspielbar.

**Files:**
- Create: `tests/test_oauth_token.py`
- Modify: `app/routen/oauth.py`
- Test: `tests/test_oauth_token.py`

**Interfaces:**
- Consumes: `app.oauth.speicher.code_einloesen`, `app.oauth.speicher.tokenpaar_ausgeben`, `app.oauth.speicher.erneuern`, `app.oauth.speicher.OAuthFehler`
- Produces: `POST /oauth/token` mit `application/x-www-form-urlencoded` → `{"access_token", "token_type": "Bearer", "expires_in", "refresh_token", "scope"}`

- [ ] **Step 1: Die Tests schreiben**

`tests/test_oauth_token.py`:

```python
"""Tests fuer POST /oauth/token - inklusive des vollstaendigen Ablaufs.

Der Ablauf laeuft hier ohne Cowork durch: registrieren, zustimmen, Code
einloesen, erneuern. Genau das verlangt die Spec in Abschnitt 8 ("OAuth
vollstaendig") und Abschnitt 9 ("Der OAuth-Ablauf wird lokal ueber Tests
geprueft").
"""

import time
from urllib.parse import parse_qs, urlsplit

from app.oauth.geheimnisse import neues_geheimnis, pkce_ableiten
from app.oauth.redirect import CLAUDE_RUECKSPRUNG
from tests.conftest import TEST_LEHRERINNEN_PASSWORT


def _code_besorgen(client) -> tuple[str, str, str]:
    """Fuehrt Registrierung und Zustimmung durch.

    Returns:
        (Autorisierungscode, code_verifier, client_id)
    """
    kennung = client.post(
        "/oauth/register",
        json={"client_name": "Claude", "redirect_uris": [CLAUDE_RUECKSPRUNG]},
    ).json()["client_id"]
    verifier = neues_geheimnis()
    antwort = client.post(
        "/oauth/authorize",
        data={
            "response_type": "code",
            "client_id": kennung,
            "redirect_uri": CLAUDE_RUECKSPRUNG,
            "scope": "lernseiten",
            "state": "zustand-123",
            "code_challenge": pkce_ableiten(verifier),
            "code_challenge_method": "S256",
            "resource": "https://karten.example.de/mcp",
            "passwort": TEST_LEHRERINNEN_PASSWORT,
        },
        follow_redirects=False,
    )
    code = parse_qs(urlsplit(antwort.headers["location"]).query)["code"][0]
    return code, verifier, kennung


def _einloesen(client, code, verifier, kennung):
    return client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CLAUDE_RUECKSPRUNG,
            "client_id": kennung,
            "code_verifier": verifier,
        },
    )


def test_der_vollstaendige_ablauf_liefert_ein_tokenpaar(client, konfiguration):
    antwort = _einloesen(client, *_code_besorgen(client))
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["token_type"] == "Bearer"
    assert daten["expires_in"] == 3600
    assert daten["scope"] == "lernseiten"
    assert len(daten["access_token"]) == 43
    assert len(daten["refresh_token"]) == 43
    assert daten["access_token"] != daten["refresh_token"]


def test_die_tokenantwort_wird_nicht_zwischengespeichert(client, konfiguration):
    antwort = _einloesen(client, *_code_besorgen(client))
    assert antwort.headers["cache-control"] == "no-store"


def test_ein_code_gilt_nur_einmal(client, konfiguration):
    code, verifier, kennung = _code_besorgen(client)
    assert _einloesen(client, code, verifier, kennung).status_code == 200
    zweite = _einloesen(client, code, verifier, kennung)
    assert zweite.status_code == 400
    assert zweite.json()["error"] == "invalid_grant"


def test_falscher_verifier_wird_mit_invalid_grant_beantwortet(client, konfiguration):
    code, _, kennung = _code_besorgen(client)
    antwort = _einloesen(client, code, neues_geheimnis(), kennung)
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_grant"
    assert "verbinde den Connector" in antwort.json()["error_description"]


def test_unbekannter_code_wird_mit_invalid_grant_beantwortet(client, konfiguration):
    _, verifier, kennung = _code_besorgen(client)
    antwort = _einloesen(client, neues_geheimnis(), verifier, kennung)
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "invalid_grant"


def test_unbekannter_grant_type_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/token", data={"grant_type": "password"})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "unsupported_grant_type"


def test_fehlender_grant_type_wird_abgelehnt(client, konfiguration):
    antwort = client.post("/oauth/token", data={})
    assert antwort.status_code == 400
    assert antwort.json()["error"] == "unsupported_grant_type"


def test_erneuern_rotiert_den_refresh_token(client, konfiguration):
    erste = _einloesen(client, *_code_besorgen(client)).json()
    zweite = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": erste["client_id_zum_test"],
        },
    ).json()
    assert zweite["refresh_token"] != erste["refresh_token"]
    assert zweite["access_token"] != erste["access_token"]


def test_ein_verbrauchter_refresh_token_wird_mit_invalid_grant_beantwortet(
    client, konfiguration
):
    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    nochmal = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    assert nochmal.status_code == 400
    assert nochmal.json()["error"] == "invalid_grant"


def test_der_ablauf_bleibt_deutlich_unter_zehn_sekunden(client, konfiguration):
    """Die Spec verlangt in Abschnitt 5: "Alle OAuth-Endpunkte antworten
    deutlich unter zehn Sekunden." Der Grenzwert ist absichtlich grosszuegig -
    er soll eine eingebaute Verzoegerung finden, nicht die Rechnerlast messen."""
    begonnen = time.monotonic()
    code, verifier, kennung = _code_besorgen(client)
    _einloesen(client, code, verifier, kennung)
    assert time.monotonic() - begonnen < 5.0
```

`test_erneuern_rotiert_den_refresh_token` benutzt einen Schlüssel, den es nicht gibt. In Step 5 wird er durch die echte `client_id` ersetzt – der Test steht bewusst zuerst falsch da, damit man ihn nicht abschreibt, ohne ihn zu lesen. Vor dem Ausführen so umbauen:

```python
def test_erneuern_rotiert_den_refresh_token(client, konfiguration):
    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    zweite = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    ).json()
    assert zweite["refresh_token"] != erste["refresh_token"]
    assert zweite["access_token"] != erste["access_token"]
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_token.py -q
```
Erwartet: 10-mal FAIL mit 404 – `/oauth/token` gibt es noch nicht.

- [ ] **Step 3: Den Token-Endpunkt in `app/routen/oauth.py` ergänzen**

Imports oben ergänzen:

```python
from app.oauth.speicher import OAuthFehler, code_einloesen, erneuern, tokenpaar_ausgeben
```

Und anhängen:

```python
def _tokenantwort(zugriff: str, erneuerung: str, gueltigkeit: int, scope: str) -> JSONResponse:
    """Die Antwort nach RFC 6749 Abschnitt 5.1."""
    return JSONResponse(
        {
            "access_token": zugriff,
            "token_type": "Bearer",
            "expires_in": gueltigkeit,
            "refresh_token": erneuerung,
            "scope": scope,
        },
        headers={**OEFFENTLICH, **NICHT_SPEICHERN},
    )


@router.post("/oauth/token")
async def token_ausgeben(
    anfrage: Request, sitzung: AsyncSession = Depends(get_session)
) -> JSONResponse:
    """Code einloesen oder Tokenpaar erneuern.

    Der Koerper ist application/x-www-form-urlencoded, so verlangt es die
    Spec in Abschnitt 5 (und RFC 6749). Gelesen wird er von Hand statt ueber
    Form(...)-Parameter im Funktionskopf: Ein fehlendes Pflichtfeld
    beantwortet FastAPI sonst mit 422 und einer englischen Pydantic-Liste,
    waehrend OAuth hier 400 mit einem "error"-Feld verlangt - und genau das
    wertet Claude aus.
    """
    formular = await anfrage.form()
    grant_type = formular.get("grant_type")

    try:
        if grant_type == "authorization_code":
            eingeloest = await code_einloesen(
                sitzung,
                code=str(formular.get("code") or ""),
                client_id=str(formular.get("client_id") or ""),
                redirect_uri=str(formular.get("redirect_uri") or ""),
                code_verifier=str(formular.get("code_verifier") or ""),
            )
            zugriff, erneuerung, gueltigkeit = await tokenpaar_ausgeben(
                sitzung,
                client_id=eingeloest.client_id,
                familie_id=eingeloest.familie_id,
                scope=eingeloest.scope,
                resource=eingeloest.resource,
            )
            scope = eingeloest.scope
        elif grant_type == "refresh_token":
            zugriff, erneuerung, gueltigkeit = await erneuern(
                sitzung,
                erneuerungstoken=str(formular.get("refresh_token") or ""),
                client_id=str(formular.get("client_id") or ""),
            )
            scope = SCOPE
        else:
            return _fehler(
                "unsupported_grant_type",
                "Dieser Server kennt nur die Ablaeufe 'authorization_code' "
                "und 'refresh_token'.",
            )
    except OAuthFehler as fehler:
        # commit statt rollback: code_einloesen() und erneuern() ziehen bei
        # einer Wiederverwendung die ganze Tokenfamilie zurueck - dieser
        # Widerruf muss auch dann bestehen bleiben, wenn die Anfrage
        # abgelehnt wird. Genau dafuer wurde er geschrieben.
        await sitzung.commit()
        return _fehler(fehler.code, fehler.beschreibung)

    await sitzung.commit()
    return _tokenantwort(zugriff, erneuerung, gueltigkeit, scope)
```

- [ ] **Step 4: Test laufen lassen**

```bash
uv run pytest tests/test_oauth_token.py -q
```
Erwartet: PASS (10 Tests).

- [ ] **Step 5: Gegenprobe von Hand – der Widerruf überlebt die Ablehnung**

Der `commit()` im `except`-Zweig ist die Stelle, an der ein Fehler stumm bliebe. Kurz gegenprüfen: In `app/routen/oauth.py` das `await sitzung.commit()` im `except`-Block versuchsweise durch `await sitzung.rollback()` ersetzen und

```bash
uv run pytest tests/test_oauth_speicher.py::test_wiederverwendung_zieht_die_ganze_familie_zurueck tests/test_oauth_token.py -q
```

laufen lassen. Der Speichertest bleibt grün (er geht nicht durch die Route) – **das ist der Befund**: Auf HTTP-Ebene gibt es dafür noch keinen Test. Deshalb `rollback` wieder zu `commit` zurückändern und diesen Test in `tests/test_oauth_token.py` ergänzen:

```python
async def test_der_familienwiderruf_ueberlebt_die_ablehnung(client, konfiguration, session):
    """Wird ein verbrauchter Refresh-Token noch einmal vorgelegt, gilt die
    ganze Familie als kompromittiert - und dieser Widerruf muss bestehen
    bleiben, obwohl die Anfrage selbst abgelehnt wird."""
    from app.oauth.speicher import zugriffstoken_pruefen

    code, verifier, kennung = _code_besorgen(client)
    erste = _einloesen(client, code, verifier, kennung).json()
    zweite = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    ).json()
    assert await zugriffstoken_pruefen(session, zweite["access_token"]) is not None

    client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": erste["refresh_token"],
            "client_id": kennung,
        },
    )
    assert await zugriffstoken_pruefen(session, zweite["access_token"]) is None
```

```bash
uv run pytest tests/test_oauth_token.py -q
```
Erwartet: PASS (11 Tests). Zur Gegenprobe noch einmal `commit` durch `rollback` ersetzen – jetzt muss dieser Test rot werden – und danach zurückändern.

- [ ] **Step 6: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/routen/oauth.py tests/test_oauth_token.py
git commit -m "Token-Endpunkt mit Codeeinloesung, rotierenden Refresh-Tokens und invalid_grant"
```
Erwartet vor dem Commit: `202 passed`, 0 übersprungen, 0 Warnungen. **Damit ist der OAuth-Teil vollständig und geprüft, bevor die erste Zeile MCP entsteht** – so verlangt es die Spec in Abschnitt 10.

---

### Task 8: Den MCP-Endpunkt einhängen

Ab hier kommt das SDK ins Spiel. Diese Aufgabe bringt noch **kein einziges Werkzeug**: Ihr Ergebnis ist, dass `POST /mcp` ohne Token mit `401` und dem richtigen `WWW-Authenticate`-Kopf antwortet und mit gültigem Token einen MCP-Handschlag zulässt. Das ist der Auslöser des ganzen Ablaufs und die Stelle, an der laut Spec am ehesten etwas stumm schiefgeht.

**Files:**
- Create: `app/oauth/pruefer.py`, `app/mcp/__init__.py`, `tests/test_mcp_transport.py`
- Modify: `app/main.py`, `tests/conftest.py` (Fixture `mcp_laeuft`)
- Test: `tests/test_mcp_transport.py`

**Interfaces:**
- Consumes: `app.sitzung.sitzung`, `app.oauth.speicher.zugriffstoken_pruefen`, `app.oauth.metadaten.*`
- Produces:
  - `app.oauth.pruefer.TokenPruefer` – die `TokenVerifier`-Umsetzung
  - `app.mcp.mcp_bauen() -> tuple[MCPServer, Starlette]` – `lru_cache`-gecacht, faul
  - `app.mcp.MCPWeiche` – ASGI-Anwendung, die `mcp_bauen()` beim ersten Aufruf auswertet
  - Fixture `mcp_laeuft` in `tests/conftest.py` – baut pro Test einen frischen Server und betritt dessen `session_manager.run()`

- [ ] **Step 1: Die Tests schreiben**

`tests/test_mcp_transport.py`:

```python
"""Tests fuer den MCP-Endpunkt als Transport - noch ohne Werkzeuge.

Der 401 mit WWW-Authenticate ist laut Spec, Abschnitt 5, der Ausloeser des
gesamten OAuth-Ablaufs. Geht er verloren, meldet Claude nur "Couldn't reach
the MCP server" und niemand sieht, woran es lag.
"""

import pytest

from app.oauth.geheimnisse import neues_geheimnis
from app.oauth.speicher import client_anlegen, tokenpaar_ausgeben
from tests.conftest import TEST_BASIS_URL

import uuid

KOEPFE = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def _zugriffstoken(session) -> str:
    kunde = await client_anlegen(
        session, client_name="Claude",
        redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
    )
    zugriff, _, _ = await tokenpaar_ausgeben(
        session, client_id=kunde.client_id, familie_id=uuid.uuid4(),
        scope="lernseiten", resource=f"{TEST_BASIS_URL}/mcp",
    )
    return zugriff


async def test_ohne_token_kommt_401_mit_wegweiser(klient, konfiguration, mcp_sitzung):
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    assert antwort.status_code == 401
    wegweiser = antwort.headers["www-authenticate"]
    assert wegweiser.startswith("Bearer")
    assert (
        f'resource_metadata="{TEST_BASIS_URL}/.well-known/oauth-protected-resource/mcp"'
        in wegweiser
    )


async def test_der_genannte_wegweiser_ist_auch_erreichbar(klient, konfiguration, mcp_sitzung):
    """Ein Kopf, der auf eine 404 zeigt, waere schlimmer als keiner."""
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    wegweiser = antwort.headers["www-authenticate"]
    pfad = wegweiser.split('resource_metadata="')[1].split('"')[0]
    pfad = pfad[len(TEST_BASIS_URL):]
    dokument = await klient.get(pfad)
    assert dokument.status_code == 200
    assert dokument.json()["resource"] == f"{TEST_BASIS_URL}/mcp"


async def test_erfundener_token_wird_abgelehnt(klient, konfiguration, mcp_sitzung):
    antwort = await klient.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        headers={**KOEPFE, "Authorization": f"Bearer {neues_geheimnis()}"},
    )
    assert antwort.status_code == 401


async def test_handschlag_mit_gueltigem_token(klient, konfiguration, mcp_sitzung, mcp_laeuft):
    token = await _zugriffstoken(mcp_sitzung)
    antwort = await klient.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        headers={**KOEPFE, "Authorization": f"Bearer {token}"},
    )
    assert antwort.status_code == 200
    assert antwort.headers["mcp-session-id"]


async def test_fremder_host_wird_nicht_abgewiesen(klient, konfiguration, mcp_sitzung, mcp_laeuft):
    """Der DNS-Rebinding-Schutz des SDK ist ausdruecklich abgeschaltet (E-2).

    Faellt jemand versehentlich auf die Voreinstellung zurueck, akzeptiert
    das SDK nur localhost-Hostnamen und antwortet allem anderen mit 421 -
    also jeder Anfrage aus Anthropics Cloud. Dieser Test ist die Sperre
    dagegen.
    """
    token = await _zugriffstoken(mcp_sitzung)
    antwort = await klient.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        headers={
            **KOEPFE,
            "Authorization": f"Bearer {token}",
            "Host": "karten.example.de",
            "Origin": "https://claude.ai",
        },
    )
    assert antwort.status_code == 200


async def test_der_mcp_endpunkt_traegt_keine_inhaltsrichtlinie(klient, konfiguration, mcp_sitzung):
    """Dort wird kein Dokument ausgeliefert - siehe app/sicherheit.py."""
    antwort = await klient.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=KOEPFE
    )
    assert "content-security-policy" not in antwort.headers


async def test_die_lernseite_bleibt_erreichbar(klient, konfiguration, mcp_sitzung):
    """Die MCP-Route darf /{slug} nicht verdecken. Ein Mount an "" wuerde
    genau das tun (nachgemessen) - deshalb ist es eine Route, kein Mount."""
    antwort = await klient.get("/gibt-es-nicht-wirklich")
    assert antwort.status_code == 404
    assert "Diese Lernseite gibt es nicht" in antwort.text


async def test_ein_mehrsegmentiger_pfad_bleibt_die_deutsche_404_seite(
    klient, konfiguration, mcp_sitzung
):
    antwort = await klient.get("/ein-zwei-drei/vier")
    assert antwort.status_code == 404
    assert "Diese Lernseite gibt es nicht" in antwort.text


def test_der_rebinding_schutz_ist_ausdruecklich_abgeschaltet(konfiguration):
    """Gegenprobe auf der Ebene der Einstellung, nicht nur der Wirkung.

    Wird transport_security gar nicht uebergeben, schaltet das SDK bei
    host="127.0.0.1" selbsttaetig den localhost-Schutz ein. Dieser Test
    scheitert dann, weil das Feld None waere.
    """
    from app.mcp import TRANSPORTSICHERHEIT

    assert TRANSPORTSICHERHEIT is not None
    assert TRANSPORTSICHERHEIT.enable_dns_rebinding_protection is False
```

- [ ] **Step 2: Die Fixture `mcp_laeuft` in `tests/conftest.py` ergänzen**

```python
@pytest_asyncio.fixture
async def mcp_laeuft():
    """Baut pro Test einen frischen MCP-Server und betritt seinen Sitzungsverwalter.

    Zwei Gruende fuer "pro Test frisch":

    1. StreamableHTTPSessionManager.run() laesst sich GENAU EINMAL pro
       Instanz betreten - das Flag _has_started wird nie zurueckgesetzt.
       Eine geteilte Instanz waere nach dem ersten Test verbraucht.
    2. app/main.py fuehrt run() in seinem Lifespan aus. Die Fixture "klient"
       benutzt httpx2.ASGITransport, und die fuehrt keinen Lifespan aus
       (siehe den Hinweis im Docstring von "klient"). Ohne diese Fixture
       antwortete jede MCP-Anfrage mit "Task group is not initialized".

    Nur anfordern, wenn ein Test tatsaechlich einen MCP-Handschlag fuehrt.
    Fuer den 401 ohne Token wird sie nicht gebraucht: Die Ablehnung
    geschieht in der Middleware davor.
    """
    from app.mcp import mcp_bauen

    mcp_bauen.cache_clear()
    server, _ = mcp_bauen()
    async with server.session_manager.run():
        yield server
    mcp_bauen.cache_clear()
```

- [ ] **Step 3: Tests laufen lassen**

```bash
uv run pytest tests/test_mcp_transport.py -q
```
Erwartet: FAIL, `No module named 'app.mcp'`.

- [ ] **Step 4: `app/oauth/pruefer.py` schreiben**

```python
"""Der Anschlusspunkt zwischen unserem OAuth-Server und dem MCP-SDK.

Das SDK ist in diesem Projekt ausschliesslich Resource Server: Es prueft
Bearer-Tokens und gibt selbst keine aus. Der Anschlusspunkt dafuer ist das
Protokoll TokenVerifier mit seiner einen Methode verify_token.
"""

from mcp.server.auth.provider import AccessToken, TokenVerifier

from app.oauth.metadaten import SCOPE
from app.oauth.speicher import zugriffstoken_pruefen
from app.sitzung import sitzung


class TokenPruefer(TokenVerifier):
    """Schlaegt den Token in der Datenbank nach.

    Die Sitzung kommt aus app/sitzung.py und NICHT aus
    get_session_factory(): Diese Methode laeuft in einer Middleware des SDK,
    also ausserhalb von FastAPIs Abhaengigkeitsaufloesung, und wuerde sonst
    in Tests die Entwicklungsdatenbank treffen. Die ausfuehrliche Begruendung
    steht im Docstring von app/sitzung.py.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        async with sitzung() as offene:
            gespeichert = await zugriffstoken_pruefen(offene, token)
            if gespeichert is None:
                return None
            return AccessToken(
                token=token,
                client_id=gespeichert.client_id,
                scopes=[SCOPE],
                expires_at=int(gespeichert.ablauf_am.timestamp()),
                resource=gespeichert.resource,
            )
```

- [ ] **Step 5: `app/mcp/__init__.py` schreiben**

```python
"""Der MCP-Server: Aufbau, Absicherung und Einhaengung.

Warum der Aufbau faul ist (lru_cache statt Modulebene): Wuerde der Server
beim Import gebaut, laese er dabei get_settings().base_url - und damit
braeuchte schon der blosse Import von app.main eine vollstaendige Umgebung.
Genau das wurde in Plan 1 abgeschafft (siehe den Docstring von
app.db.get_engine). Ein frischer Checkout ohne .env und die CI muessen
app.main importieren koennen.

Warum eine Route und kein Mount: Nachgemessen gegen mcp 2.1.1 und Starlette
1.6.0 -
  - app.mount("", mcp_app) verschluckt JEDE Anfrage, auch /{slug}: Ein Mount
    mit leerem Praefix passt auf alles, und die Lernseiten waeren tot.
  - app.mount("/mcp", ...) macht den Endpunkt nur unter /mcp/ erreichbar;
    POST /mcp (die Adresse, die die Lehrerin eintraegt) endet in 405.
Eine gewoehnliche starlette.routing.Route mit der Starlette-App als
endpoint trifft dagegen genau /mcp - Starlette behandelt einen
endpoint, der keine Funktion und keine Methode ist, als ASGI-Anwendung und
reicht den unveraenderten Pfad hinein.
"""

from functools import lru_cache

from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.types import Receive, Scope, Send

from app.config import get_settings
from app.oauth.metadaten import MCP_PFAD, SCOPE, resource_url
from app.oauth.pruefer import TokenPruefer

# Der DNS-Rebinding-Schutz des SDK ist AUSDRUECKLICH abgeschaltet - siehe
# Entscheidung E-2 im Plan. Kurz: Er ist fuer Server gedacht, die auf
# localhost lauschen und von einer Webseite aus angreifbar waeren. Unserer
# ist ein oeffentlicher HTTPS-Endpunkt, dessen einziger Schutz das
# Bearer-Token ist; der Host-Kopf ist hinter Coolifys Proxy ohnehin nicht
# vertrauenswuerdig (uvicorn laeuft mit --forwarded-allow-ips='*'). Eine
# Positivliste fuer Origin waere dagegen die wahrscheinlichste Ursache fuer
# ein stummes "Couldn't reach the MCP server", das sich lokal nicht
# nachstellen laesst.
#
# Das Feld MUSS uebergeben werden: Ohne Angabe und mit dem Standardwert
# host="127.0.0.1" schaltet das SDK selbsttaetig einen Schutz ein, der
# ausschliesslich localhost-Hostnamen akzeptiert und allem anderen mit 421
# antwortet - also jeder Anfrage aus Anthropics Cloud.
TRANSPORTSICHERHEIT = TransportSecuritySettings(enable_dns_rebinding_protection=False)


@lru_cache
def mcp_bauen() -> tuple[MCPServer, Starlette]:
    """Baut den MCP-Server und seine ASGI-Anwendung, einmalig und gecacht.

    Returns:
        (Server, ASGI-Anwendung). Den Server braucht der Lifespan in
        app/main.py fuer session_manager.run(), die Anwendung braucht die
        Route.

    Tests leeren den Cache mit mcp_bauen.cache_clear() und bauen pro Test
    neu - session_manager.run() laesst sich nur einmal pro Instanz betreten.
    """
    basis_url = get_settings().base_url
    server = MCPServer(
        "flashcards",
        title="Lernseiten fuer die Berufsschule",
        instructions=(
            "Mit diesen Werkzeugen legst du Lernpakete fuer eine Berufsschule "
            "an und pflegst sie. Jedes Lernpaket bekommt eine eigene Adresse "
            "aus drei deutschen Woertern. Gib der Lehrerin nach jeder "
            "Aenderung den vollstaendigen Link."
        ),
        token_verifier=TokenPruefer(),
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(basis_url),
            resource_server_url=AnyHttpUrl(resource_url(basis_url)),
            required_scopes=[SCOPE],
        ),
    )
    # Ab Task 10 registriert diese Zeile die acht Werkzeuge. Bis dahin gibt
    # es keine - der Transport wird trotzdem vollstaendig geprueft.
    asgi = server.streamable_http_app(
        streamable_http_path=MCP_PFAD,
        transport_security=TRANSPORTSICHERHEIT,
    )
    return server, asgi


class MCPWeiche:
    """Reicht eine Anfrage an die MCP-Anwendung durch.

    Eine Klasse und keine Funktion: Starlette behandelt einen endpoint, der
    eine Funktion oder Methode ist, als Request/Response-Endpunkt und
    uebergibt ihm ein Request-Objekt. Eine Instanz mit __call__ ist fuer
    Starlette dagegen eine ASGI-Anwendung und bekommt (scope, receive, send)
    - und genau das braucht die MCP-Anwendung.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        _, asgi = mcp_bauen()
        await asgi(scope, receive, send)
```

- [ ] **Step 6: `app/main.py` um Lifespan und Route ergänzen**

Imports ergänzen:

```python
from contextlib import asynccontextmanager

from starlette.routing import Route

from app.mcp import MCPWeiche, mcp_bauen
```

Vor der App-Erzeugung:

```python
@asynccontextmanager
async def lebenslauf(app: FastAPI):
    """Betritt den Sitzungsverwalter des MCP-Servers.

    Ohne das antwortet jede MCP-Anfrage mit "Task group is not initialized.
    Make sure to use run()." - die eingehaengte Starlette-App bringt zwar
    einen eigenen Lifespan mit, aber Starlette fuehrt den Lifespan einer
    Unteranwendung nicht aus. Das ist die Stelle, an der so etwas gern
    uebersehen wird.
    """
    server, _ = mcp_bauen()
    async with server.session_manager.run():
        yield
```

Die App-Erzeugung um den Lifespan ergänzen:

```python
app = FastAPI(
    title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None,
    lifespan=lebenslauf,
)
```

Und die Route **vor** `app.include_router(lernseite.router)` eintragen:

```python
# Eine Route und kein Mount - die Begruendung steht im Docstring von
# app/mcp/__init__.py. Ohne methods=... passt sie auf jede Methode; das
# ist gewollt, weil Streamable HTTP POST, GET und DELETE benutzt.
app.router.routes.append(Route(MCP_PFAD, endpoint=MCPWeiche()))
```

mit `from app.oauth.metadaten import MCP_PFAD` bei den Imports.

- [ ] **Step 7: Tests laufen lassen**

```bash
uv run pytest tests/test_mcp_transport.py -q
```
Erwartet: PASS (9 Tests).

- [ ] **Step 8: Die gesamte Suite laufen lassen und auf den Lifespan achten**

```bash
uv run pytest -q
```
Erwartet: `211 passed`, 0 übersprungen, 0 Warnungen. Falls Tests mit `RuntimeError: Task group is not initialized` scheitern, fehlt ihnen die Fixture `mcp_laeuft`. Falls ein Test mit „can only be called once" scheitert, benutzt er einen `TestClient` als Kontextmanager (`with TestClient(app) as ...`) und führt damit den Lifespan ein zweites Mal aus – dann `mcp_bauen.cache_clear()` davor setzen oder den Kontextmanager weglassen.

- [ ] **Step 9: Commit**

```bash
git add app/oauth/pruefer.py app/mcp/__init__.py app/main.py tests/conftest.py tests/test_mcp_transport.py
git commit -m "MCP-Endpunkt eingehaengt: 401-Handschlag, Token-Pruefer und Sitzungsverwalter im Lifespan"
```

---

### Task 9: Kartenprüfung und Eingabemodelle

Der Kern der Werkzeuge, ohne Datenbank und ohne MCP. Hier entstehen die Meldungen, die der Agent der Lehrerin vorliest – und hier wird `richtige_antwort` als **Text** auf `richtige_index` abgebildet, was laut Spec die häufigste Fehlerquelle entschärft.

**Files:**
- Create: `app/mcp/fehler.py`, `app/mcp/eingaben.py`, `app/mcp/karten.py`, `tests/test_mcp_karten.py`
- Test: `tests/test_mcp_karten.py`

**Interfaces:**
- Consumes: `app.markdown.rendern`, `app.markdown.MAX_LAENGE`, `app.markdown.MarkdownZuLang`, `app.models.MAX_TITEL_LAENGE`, `app.models.MAX_KLASSE_LAENGE`
- Produces:
  - `app.mcp.fehler.MCPFehler(Exception)` – die eine Ausnahme, die alle Werkzeuge werfen
  - `app.mcp.eingaben.KarteEingabe` – `art`, `vorderseite`, `rueckseite`, `antworten`, `richtige_antwort`, `erklaerung`
  - `app.mcp.eingaben.KarteAenderung` – dieselben Felder, alle optional
  - `app.mcp.karten.karte_pruefen(eingabe: KarteEingabe, nummer: int) -> dict` – gibt die Spaltenwerte zurück (`art`, `vorderseite`, `rueckseite`, `antworten`, `richtige_index`, `erklaerung`)
  - `app.mcp.karten.titel_pruefen(titel: str) -> str`
  - `app.mcp.karten.klasse_pruefen(klasse: str | None) -> str | None`
  - `app.mcp.karten.beschreibung_pruefen(beschreibung: str | None) -> str | None`
  - `app.mcp.karten.MIN_ANTWORTEN = 2`, `app.mcp.karten.MAX_ANTWORTEN = 4`

- [ ] **Step 1: Die Tests schreiben**

`tests/test_mcp_karten.py`:

```python
"""Tests fuer die Kartenpruefung.

Ohne Datenbank, ohne MCP. Der Schwerpunkt liegt auf den MELDUNGEN: Der Agent
liest sie der Lehrerin vor, also muessen sie sagen, was falsch ist UND was
zu tun ist. Ein Test, der nur den Ausnahmetyp prueft, prueft hier zu wenig.
"""

import pytest

from app.markdown import MAX_LAENGE
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import (
    beschreibung_pruefen,
    karte_pruefen,
    klasse_pruefen,
    titel_pruefen,
)


def _frage(**abweichungen) -> KarteEingabe:
    felder = {
        "art": "frage",
        "vorderseite": "Was ist die Hauptstadt von Kroatien?",
        "antworten": ["Split", "Zagreb", "Dubrovnik", "Rijeka"],
        "richtige_antwort": "Zagreb",
        "erklaerung": "Zagreb liegt im Landesinneren.",
    }
    felder.update(abweichungen)
    return KarteEingabe(**felder)


def _flashcard(**abweichungen) -> KarteEingabe:
    felder = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlungsschicht"}
    felder.update(abweichungen)
    return KarteEingabe(**felder)


def test_eine_frage_wird_zu_spaltenwerten():
    werte = karte_pruefen(_frage(), nummer=1)
    assert werte["art"] == "frage"
    assert werte["antworten"] == ["Split", "Zagreb", "Dubrovnik", "Rijeka"]
    assert werte["richtige_index"] == 1
    assert werte["rueckseite"] is None
    assert werte["erklaerung"] == "Zagreb liegt im Landesinneren."


def test_eine_flashcard_wird_zu_spaltenwerten():
    werte = karte_pruefen(_flashcard(), nummer=1)
    assert werte["art"] == "flashcard"
    assert werte["rueckseite"] == "Vermittlungsschicht"
    assert werte["antworten"] is None
    assert werte["richtige_index"] is None
    assert werte["erklaerung"] is None


def test_gross_und_kleinschreibung_stoert_die_zuordnung_nicht():
    """Ein Agent, der "zagreb" tippt, soll nicht scheitern (Entscheidung E-4)."""
    assert karte_pruefen(_frage(richtige_antwort="  zagreb "), nummer=1)["richtige_index"] == 1


def test_fehlende_richtige_antwort_nennt_position_und_handlung():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(richtige_antwort=None), nummer=3)
    text = str(fehler.value)
    assert "Position 3" in text
    assert "keine richtige Antwort" in text
    assert "Text einer der Antwortmöglichkeiten" in text


def test_unbekannte_richtige_antwort_zeigt_die_moeglichkeiten():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(richtige_antwort="Ljubljana"), nummer=2)
    text = str(fehler.value)
    assert "Position 2" in text
    assert "Ljubljana" in text
    assert "Zagreb" in text
    assert "genau so" in text


def test_mehrfach_vorkommende_antwort_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(
            _frage(antworten=["Zagreb", "Zagreb", "Split"], richtige_antwort="Zagreb"),
            nummer=5,
        )
    text = str(fehler.value)
    assert "Position 5" in text
    assert "mehrfach" in text


@pytest.mark.parametrize(
    "antworten,anzahl",
    [
        (["Nur eine"], "eine"),
        (["A", "B", "C", "D", "E"], "fünf"),
        (["A", "B", "C", "D", "E", "F"], "sechs"),
    ],
)
def test_falsche_anzahl_antworten_wird_benannt(antworten, anzahl):
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(antworten=antworten, richtige_antwort=antworten[0]), nummer=4)
    text = str(fehler.value)
    assert "zwei bis vier Antwortmöglichkeiten" in text
    assert anzahl in text
    assert "Position 4" in text


def test_flashcard_ohne_rueckseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(rueckseite=None), nummer=1)
    assert "Rückseite" in str(fehler.value)


def test_flashcard_mit_antworten_wird_abgelehnt():
    """Die Datenbank verboete es ohnehin - aber mit einer Meldung, die
    niemandem weiterhilft."""
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(antworten=["A", "B"]), nummer=1)
    text = str(fehler.value)
    assert "Position 1" in text
    assert "Antwortmöglichkeiten" in text


def test_frage_mit_rueckseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_frage(rueckseite="steht hier falsch"), nummer=1)
    assert "Rückseite" in str(fehler.value)


def test_leere_vorderseite_wird_abgelehnt():
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(vorderseite="   "), nummer=7)
    text = str(fehler.value)
    assert "Position 7" in text
    assert "Vorderseite" in text


def test_zu_langer_text_wird_vor_dem_speichern_abgefangen():
    """Die Meldung muss BEIDE Zahlen nennen - so kommt sie aus
    app/markdown.py, und so ist sie brauchbar."""
    with pytest.raises(MCPFehler) as fehler:
        karte_pruefen(_flashcard(rueckseite="x" * (MAX_LAENGE + 1)), nummer=2)
    text = str(fehler.value)
    assert str(MAX_LAENGE + 1) in text
    assert str(MAX_LAENGE) in text
    assert "Position 2" in text


def test_genau_die_grenze_ist_erlaubt():
    karte_pruefen(_flashcard(rueckseite="x" * MAX_LAENGE), nummer=1)


def test_titel_wird_beschnitten_und_geprueft():
    assert titel_pruefen("  Netzwerktechnik  ") == "Netzwerktechnik"
    with pytest.raises(MCPFehler) as fehler:
        titel_pruefen("   ")
    assert "Titel" in str(fehler.value)
    with pytest.raises(MCPFehler) as fehler:
        titel_pruefen("t" * 201)
    assert "200" in str(fehler.value)


def test_klasse_ist_optional_und_begrenzt():
    assert klasse_pruefen(None) is None
    assert klasse_pruefen("   ") is None
    assert klasse_pruefen("  FS 23b ") == "FS 23b"
    with pytest.raises(MCPFehler) as fehler:
        klasse_pruefen("k" * 61)
    assert "60" in str(fehler.value)


def test_beschreibung_ist_optional_und_geht_durch_die_laengenpruefung():
    assert beschreibung_pruefen(None) is None
    assert beschreibung_pruefen("  ") is None
    assert beschreibung_pruefen(" Kurz ") == "Kurz"
    with pytest.raises(MCPFehler):
        beschreibung_pruefen("b" * (MAX_LAENGE + 1))
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_mcp_karten.py -q
```
Erwartet: FAIL, `No module named 'app.mcp.fehler'`.

- [ ] **Step 3: `app/mcp/fehler.py` schreiben**

```python
"""Die eine Ausnahme, die alle Werkzeuge werfen.

Sie traegt ausschliesslich deutschen Klartext, weil der Agent ihn der
Lehrerin vorliest. Die Umwandlung in die MCP-Antwort geschieht an genau
einer Stelle: in app/mcp/werkzeuge.py.
"""


class MCPFehler(Exception):
    """Ein Fehler, dessen Text fuer die Lehrerin bestimmt ist.

    Regel fuer jede Meldung: Sie nennt, WAS falsch ist und WAS ZU TUN ist.
    "Ungueltige Eingabe" ist keine Meldung, sondern eine Ausrede. Die Spec
    gibt in Abschnitt 5 drei Muster vor:

        "Die Karte auf Position 3 hat keine richtige Antwort. Bitte gib den
         Text einer der Antwortmoeglichkeiten an."
        "Ein Bundle mit dem Slug `rote-katze-springt` gibt es nicht. Mit
         `bundle_liste` siehst du alle vorhandenen."
        "Eine Frage braucht zwei bis vier Antwortmoeglichkeiten, diese hat
         sechs."
    """


def bei_karte(nummer: int, satz: str) -> str:
    """Stellt jeder Kartenmeldung dieselbe Ortsangabe voran.

    Ohne sie muesste die Lehrerin raten, welche der zwanzig Karten gemeint
    ist. Die Nummer ist die Position in der uebergebenen Liste, beginnend
    bei 1 - nicht die Spalte "position" in der Datenbank, die bei 0 beginnt
    und Luecken haben darf.
    """
    return f"Die Karte auf Position {nummer} {satz}"
```

- [ ] **Step 4: `app/mcp/eingaben.py` schreiben**

```python
"""Die Eingabemodelle der Werkzeuge.

Aus ihnen erzeugt das MCP-SDK das JSON-Schema, das der Agent zu sehen
bekommt. Die Beschreibungen sind deshalb kein Beiwerk: Sie sind die einzige
Anleitung, die der Agent hat.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class KarteEingabe(BaseModel):
    """Eine Karte, wie der Agent sie uebergibt."""

    art: Annotated[
        Literal["flashcard", "frage"],
        Field(description="'flashcard' zum Lernen, 'frage' fuer Multiple Choice."),
    ]
    vorderseite: Annotated[
        str,
        Field(
            description=(
                "Bei einer Flashcard der Begriff, bei einer Frage die Frage "
                "selbst. Einfaches Markdown ist erlaubt."
            )
        ),
    ]
    rueckseite: Annotated[
        str | None,
        Field(
            default=None,
            description="Nur bei art='flashcard': die Loesung. Einfaches Markdown.",
        ),
    ] = None
    antworten: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': zwei bis vier Antwortmoeglichkeiten als "
                "Klartext, ohne Buchstaben davor. Benutze KEINE Moeglichkeiten "
                "wie 'keine der genannten' oder 'A und B sind richtig' - die "
                "Reihenfolge wird bei jedem Durchlauf neu gemischt, solche "
                "Antworten ergeben danach keinen Sinn mehr."
            ),
        ),
    ] = None
    richtige_antwort: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': der TEXT der richtigen Antwort, genau so, "
                "wie er in 'antworten' steht - kein Buchstabe, keine Zahl."
            ),
        ),
    ] = None
    erklaerung: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': optionale Erklaerung, die nach dem "
                "Antworten auf der Rueckseite erscheint."
            ),
        ),
    ] = None


class KarteAenderung(BaseModel):
    """Die aenderbaren Felder einer bestehenden Karte.

    Alle Felder sind optional. Was nicht angegeben ist, bleibt, wie es war -
    'art' laesst sich nicht aendern, weil eine Flashcard und eine Frage
    unterschiedliche Pflichtfelder haben; dafuer loescht man die Karte und
    legt eine neue an.
    """

    vorderseite: str | None = None
    rueckseite: str | None = None
    antworten: list[str] | None = None
    richtige_antwort: str | None = None
    erklaerung: str | None = None
```

- [ ] **Step 5: `app/mcp/karten.py` schreiben**

```python
"""Aus einer Eingabe des Agenten werden geprueft Spaltenwerte.

Zwei Dinge geschehen hier, und beide sind in der Spec begruendet:

1. Die richtige Antwort kommt als TEXT und wird zu einer POSITION. Die
   Antwortreihenfolge wird bei jedem Durchlauf neu gemischt; ein
   gespeicherter Buchstabe waere danach falsch. Und der Agent, der einen
   Text angibt statt eines Buchstabens, kann nicht verrutschen.
2. Die Laengen werden HIER geprueft, nicht erst beim Ausliefern. Die
   Datenbank hat eigene Constraints, aber die melden sich mit einem
   Constraint-Namen - und den soll die Lehrerin nicht vorgelesen bekommen.
"""

from app.markdown import MarkdownZuLang, rendern
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler, bei_karte
from app.models import MAX_KLASSE_LAENGE, MAX_TITEL_LAENGE

MIN_ANTWORTEN = 2
MAX_ANTWORTEN = 4

# Fuer die Meldung "diese hat sechs" aus der Spec. Zahlwoerter statt Ziffern,
# weil die Meldung vorgelesen wird.
_ZAHLWOERTER = {
    0: "keine",
    1: "eine",
    2: "zwei",
    3: "drei",
    4: "vier",
    5: "fünf",
    6: "sechs",
    7: "sieben",
    8: "acht",
    9: "neun",
    10: "zehn",
}


def _zahlwort(anzahl: int) -> str:
    return _ZAHLWOERTER.get(anzahl, str(anzahl))


def _normalisiert(text: str) -> str:
    """Die Form, in der Antworttexte verglichen werden (Entscheidung E-4)."""
    return text.strip().casefold()


def _laenge_pruefen(text: str | None, feld: str, ort: str) -> None:
    """Wirft MCPFehler, wenn der Text nicht ausgeliefert werden koennte.

    rendern() macht die Arbeit: Es wirft MarkdownZuLang mit einer Meldung,
    die beide Zahlen nennt ("ist mit 5210 Zeichen zu lang. Erlaubt sind 5000
    Zeichen pro Karte."). Die uebernehmen wir woertlich und stellen nur den
    Ort davor.
    """
    if text is None:
        return
    try:
        rendern(text)
    except MarkdownZuLang as fehler:
        raise MCPFehler(f"{ort}: Das Feld '{feld}' ist zu lang. {fehler}") from fehler


def karte_pruefen(eingabe: KarteEingabe, nummer: int) -> dict:
    """Prueft eine Karte und gibt ihre Spaltenwerte zurueck.

    Args:
        eingabe: Die Karte, wie der Agent sie uebergeben hat.
        nummer: Die Position in der uebergebenen Liste, beginnend bei 1.
            Erscheint in jeder Meldung, damit die Lehrerin weiss, welche
            Karte gemeint ist.

    Returns:
        Ein Dict mit den Schluesseln art, vorderseite, rueckseite,
        antworten, richtige_index, erklaerung - genau die Spalten von
        app.models.Karte ausser id, bundle_id und position.

    Raises:
        MCPFehler: Mit einer deutschen Meldung, die sagt, was zu tun ist.
    """
    ort = f"Die Karte auf Position {nummer}"
    vorderseite = (eingabe.vorderseite or "").strip()
    if not vorderseite:
        raise MCPFehler(
            bei_karte(nummer, "hat keine Vorderseite. Bitte gib den Begriff "
                              "oder die Frage an.")
        )
    _laenge_pruefen(vorderseite, "vorderseite", ort)

    if eingabe.art == "flashcard":
        return _flashcard_pruefen(eingabe, nummer, ort, vorderseite)
    return _frage_pruefen(eingabe, nummer, ort, vorderseite)


def _flashcard_pruefen(eingabe: KarteEingabe, nummer: int, ort: str, vorderseite: str) -> dict:
    rueckseite = (eingabe.rueckseite or "").strip()
    if not rueckseite:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard, hat aber keine Rückseite. "
                              "Bitte gib an, was auf der Rückseite stehen soll.")
        )
    if eingabe.antworten or eingabe.richtige_antwort:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard und darf keine "
                              "Antwortmöglichkeiten haben. Setze art auf 'frage', "
                              "wenn es eine Multiple-Choice-Frage werden soll.")
        )
    if eingabe.erklaerung:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Flashcard und darf keine Erklärung "
                              "haben. Schreib die Erklärung mit auf die Rückseite.")
        )
    _laenge_pruefen(rueckseite, "rueckseite", ort)
    return {
        "art": "flashcard",
        "vorderseite": vorderseite,
        "rueckseite": rueckseite,
        "antworten": None,
        "richtige_index": None,
        "erklaerung": None,
    }


def _frage_pruefen(eingabe: KarteEingabe, nummer: int, ort: str, vorderseite: str) -> dict:
    if eingabe.rueckseite:
        raise MCPFehler(
            bei_karte(nummer, "ist eine Frage und darf keine Rückseite haben. "
                              "Was dort stehen sollte, gehört in 'erklaerung'.")
        )

    antworten = [text.strip() for text in (eingabe.antworten or [])]
    if not MIN_ANTWORTEN <= len(antworten) <= MAX_ANTWORTEN:
        raise MCPFehler(
            "Eine Frage braucht zwei bis vier Antwortmöglichkeiten, "
            f"die Karte auf Position {nummer} hat {_zahlwort(len(antworten))}."
        )
    if any(not text for text in antworten):
        raise MCPFehler(
            bei_karte(nummer, "hat eine leere Antwortmöglichkeit. Bitte gib "
                              "für jede Möglichkeit einen Text an.")
        )

    richtige = (eingabe.richtige_antwort or "").strip()
    if not richtige:
        raise MCPFehler(
            bei_karte(nummer, "hat keine richtige Antwort. Bitte gib den Text "
                              "einer der Antwortmöglichkeiten an.")
        )

    gesucht = _normalisiert(richtige)
    treffer = [stelle for stelle, text in enumerate(antworten)
               if _normalisiert(text) == gesucht]
    aufzaehlung = ", ".join(f"„{text}“" for text in antworten)
    if not treffer:
        raise MCPFehler(
            bei_karte(nummer, f"nennt als richtige Antwort „{richtige}“. Dieser "
                              f"Text steht nicht unter den Antwortmöglichkeiten "
                              f"({aufzaehlung}). Bitte gib ihn genau so an, wie "
                              f"er in der Liste steht.")
        )
    if len(treffer) > 1:
        raise MCPFehler(
            bei_karte(nummer, f"nennt als richtige Antwort „{richtige}“. Dieser "
                              f"Text kommt unter den Antwortmöglichkeiten mehrfach "
                              f"vor ({aufzaehlung}). Bitte formuliere die "
                              f"Möglichkeiten so, dass jede nur einmal vorkommt.")
        )

    erklaerung = (eingabe.erklaerung or "").strip() or None
    _laenge_pruefen(erklaerung, "erklaerung", ort)
    for text in antworten:
        _laenge_pruefen(text, "antworten", ort)

    return {
        "art": "frage",
        "vorderseite": vorderseite,
        "rueckseite": None,
        "antworten": antworten,
        "richtige_index": treffer[0],
        "erklaerung": erklaerung,
    }


def titel_pruefen(titel: str) -> str:
    beschnitten = (titel or "").strip()
    if not beschnitten:
        raise MCPFehler(
            "Das Lernpaket braucht einen Titel. Bitte gib eine kurze "
            "Überschrift an, zum Beispiel „Netzwerkgrundlagen“."
        )
    if len(beschnitten) > MAX_TITEL_LAENGE:
        raise MCPFehler(
            f"Der Titel ist mit {len(beschnitten)} Zeichen zu lang. Erlaubt "
            f"sind {MAX_TITEL_LAENGE} Zeichen – er steht als einzeilige "
            "Überschrift auf der Lernseite."
        )
    return beschnitten


def klasse_pruefen(klasse: str | None) -> str | None:
    beschnitten = (klasse or "").strip()
    if not beschnitten:
        return None
    if len(beschnitten) > MAX_KLASSE_LAENGE:
        raise MCPFehler(
            f"Die Klassenbezeichnung ist mit {len(beschnitten)} Zeichen zu "
            f"lang. Erlaubt sind {MAX_KLASSE_LAENGE} Zeichen, zum Beispiel "
            "„FS 23b“."
        )
    return beschnitten


def beschreibung_pruefen(beschreibung: str | None) -> str | None:
    beschnitten = (beschreibung or "").strip()
    if not beschnitten:
        return None
    _laenge_pruefen(beschnitten, "beschreibung", "Die Beschreibung des Lernpakets")
    return beschnitten
```

- [ ] **Step 6: Tests laufen lassen**

```bash
uv run pytest tests/test_mcp_karten.py -q
```
Erwartet: PASS (20 Tests).

- [ ] **Step 7: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/mcp/fehler.py app/mcp/eingaben.py app/mcp/karten.py tests/test_mcp_karten.py
git commit -m "Kartenpruefung: richtige Antwort als Text, Laengen vor dem Speichern, deutsche Meldungen"
```
Erwartet vor dem Commit: `231 passed`, 0 übersprungen, 0 Warnungen.

---

### Task 10: `bundle_anlegen`, `bundle_liste`, `bundle_anzeigen`

Der erste Aufruf, der etwas bewirkt – und der wichtigste: Aus einem Arbeitsblatt soll **ein** Werkzeugaufruf ein fertiges Lernpaket machen. Hier steckt auch der Wettlauf um den Slug.

**Files:**
- Create: `app/mcp/dienste.py`, `app/mcp/werkzeuge.py`, `tests/test_mcp_werkzeuge_bundles.py`
- Modify: `app/mcp/__init__.py` (Werkzeuge registrieren)
- Test: `tests/test_mcp_werkzeuge_bundles.py`

**Interfaces:**
- Consumes: `app.slug.freien_slug_finden`, `app.slug.SlugKollision`, `app.mcp.karten.*`, `app.sitzung.sitzung`, `app.config.get_settings`
- Produces:
  - `app.mcp.dienste.bundle_anlegen(sitzung, titel, beschreibung, klasse, selbsteinschaetzung, karten) -> Bundle`
  - `app.mcp.dienste.bundle_holen(sitzung, slug) -> Bundle` (wirft `MCPFehler`)
  - `app.mcp.dienste.bundles_auflisten(sitzung, klasse, nur_aktive) -> list[tuple[Bundle, int]]`
  - `app.mcp.dienste.SLUG_VERSUCHE = 3`
  - `app.mcp.werkzeuge.registrieren(server: MCPServer) -> None`
  - `app.mcp.werkzeuge.uebersicht(bundle, anzahl_karten) -> dict` mit den Schlüsseln `slug`, `url`, `titel`, `beschreibung`, `klasse`, `selbsteinschaetzung`, `reihenfolge`, `aktiv`, `anzahl_karten`
  - Werkzeuge `bundle_anlegen`, `bundle_liste`, `bundle_anzeigen`

- [ ] **Step 1: Die Tests schreiben**

`tests/test_mcp_werkzeuge_bundles.py`:

```python
"""Tests fuer die Werkzeuge rund um Bundles.

Aufgerufen wird ueber MCPServer.call_tool() und nicht ueber HTTP: So wird
genau das geprueft, was der Agent zu sehen bekommt (Schema, Ergebnis,
Fehlertext), ohne dass fuer jeden Fall ein Handschlag noetig waere. Der Weg
ueber HTTP wird in tests/test_mcp_ende_zu_ende.py einmal vollstaendig
gegangen.
"""

import json

import pytest
from sqlalchemy import select

from app.mcp import mcp_bauen
from app.models import Bundle
from tests.conftest import TEST_BASIS_URL

FLASHCARD = {"art": "flashcard", "vorderseite": "OSI-Schicht 3", "rueckseite": "Vermittlungsschicht"}
FRAGE = {
    "art": "frage",
    "vorderseite": "Was ist die Hauptstadt von Kroatien?",
    "antworten": ["Split", "Zagreb", "Dubrovnik", "Rijeka"],
    "richtige_antwort": "Zagreb",
    "erklaerung": "Zagreb liegt im Landesinneren.",
}


async def _aufrufen(name: str, **argumente) -> dict:
    """Ruft ein Werkzeug auf und gibt sein Ergebnis als Dict zurueck."""
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is False, ergebnis.content[0].text
    return json.loads(ergebnis.content[0].text)


async def _fehlertext(name: str, **argumente) -> str:
    """Ruft ein Werkzeug auf, das scheitern soll, und gibt den Text zurueck."""
    server, _ = mcp_bauen()
    ergebnis = await server.call_tool(name, argumente)
    assert ergebnis.is_error is True
    return ergebnis.content[0].text


@pytest.fixture(autouse=True)
def frischer_server():
    """Baut den Server pro Test neu, damit kein Zustand mitwandert."""
    mcp_bauen.cache_clear()
    yield
    mcp_bauen.cache_clear()


async def test_anlegen_liefert_slug_url_und_anzahl(konfiguration, mcp_sitzung):
    daten = await _aufrufen(
        "bundle_anlegen",
        titel="Netzwerkgrundlagen",
        klasse="FS 23b",
        karten=[FLASHCARD, FRAGE],
    )
    assert daten["slug"].count("-") == 2
    assert daten["url"] == f"{TEST_BASIS_URL}/{daten['slug']}"
    assert daten["anzahl_karten"] == 2
    assert daten["titel"] == "Netzwerkgrundlagen"


async def test_die_karten_landen_richtig_in_der_datenbank(konfiguration, mcp_sitzung):
    daten = await _aufrufen("bundle_anlegen", titel="T", karten=[FRAGE, FLASHCARD])
    bundle = await mcp_sitzung.scalar(select(Bundle).where(Bundle.slug == daten["slug"]))
    karten = sorted(bundle.karten, key=lambda k: k.position)
    assert [k.position for k in karten] == [0, 1]
    assert karten[0].art == "frage"
    assert karten[0].richtige_index == 1
    assert karten[0].rueckseite is None
    assert karten[1].art == "flashcard"
    assert karten[1].antworten is None


async def test_anlegen_ohne_karten_wird_abgelehnt(konfiguration, mcp_sitzung):
    text = await _fehlertext("bundle_anlegen", titel="Leer", karten=[])
    assert "keine Karten" in text
    assert "mindestens eine" in text


async def test_eine_kaputte_karte_verhindert_das_ganze_bundle(konfiguration, mcp_sitzung):
    """Alles oder nichts: Ein halb angelegtes Lernpaket waere schlimmer als
    keines, weil niemand sieht, was fehlt."""
    kaputt = {**FRAGE, "richtige_antwort": "Ljubljana"}
    text = await _fehlertext("bundle_anlegen", titel="T", karten=[FLASHCARD, kaputt])
    assert "Position 2" in text
    anzahl = len((await mcp_sitzung.scalars(select(Bundle))).all())
    assert anzahl == 0


async def test_ein_belegter_slug_wird_neu_gewuerfelt(konfiguration, mcp_sitzung, monkeypatch):
    """Der Wettlauf aus Spec, Abschnitt 4.

    freien_slug_finden() prueft und schreibt nicht atomar: Zwischen "ist
    frei" und "ist eingetragen" kann ein zweiter Aufruf denselben Kandidaten
    ziehen. Aufgefangen wird das vom Unique-Constraint - und das Anlegen muss
    daraufhin NEU WUERFELN statt der Lehrerin einen IntegrityError
    vorzulegen.

    Nachgestellt wird der Wettlauf, indem freien_slug_finden zuerst einen
    Slug liefert, der schon vergeben ist.
    """
    from app.mcp import dienste

    mcp_sitzung.add(Bundle(slug="schon-vergeben-adresse", titel="Da"))
    await mcp_sitzung.flush()

    kandidaten = iter(["schon-vergeben-adresse", "frisch-gewuerfelte-adresse"])

    async def gefaelscht(sitzung, versuche=10):
        return next(kandidaten)

    monkeypatch.setattr(dienste, "freien_slug_finden", gefaelscht)

    daten = await _aufrufen("bundle_anlegen", titel="Zweites", karten=[FLASHCARD])
    assert daten["slug"] == "frisch-gewuerfelte-adresse"


async def test_wenn_gar_nichts_frei_ist_kommt_eine_klartextmeldung(
    konfiguration, mcp_sitzung, monkeypatch
):
    from app.mcp import dienste

    mcp_sitzung.add(Bundle(slug="immer-dieselbe-adresse", titel="Da"))
    await mcp_sitzung.flush()

    async def immer_dieselbe(sitzung, versuche=10):
        return "immer-dieselbe-adresse"

    monkeypatch.setattr(dienste, "freien_slug_finden", immer_dieselbe)

    text = await _fehlertext("bundle_anlegen", titel="Dritte", karten=[FLASHCARD])
    assert "keine freie" in text.lower()
    assert "noch einmal" in text


async def test_liste_zeigt_slug_url_und_kartenzahl(konfiguration, mcp_sitzung):
    await _aufrufen("bundle_anlegen", titel="Eins", klasse="FS 23b", karten=[FLASHCARD])
    await _aufrufen("bundle_anlegen", titel="Zwei", klasse="EL 24a", karten=[FRAGE, FLASHCARD])

    daten = await _aufrufen("bundle_liste")
    assert daten["anzahl"] == 2
    nach_titel = {eintrag["titel"]: eintrag for eintrag in daten["bundles"]}
    assert nach_titel["Zwei"]["anzahl_karten"] == 2
    assert nach_titel["Eins"]["klasse"] == "FS 23b"
    assert nach_titel["Eins"]["url"].startswith(TEST_BASIS_URL)
    assert nach_titel["Eins"]["aktiv"] is True


async def test_liste_laesst_sich_nach_klasse_filtern(konfiguration, mcp_sitzung):
    await _aufrufen("bundle_anlegen", titel="Eins", klasse="FS 23b", karten=[FLASHCARD])
    await _aufrufen("bundle_anlegen", titel="Zwei", klasse="EL 24a", karten=[FLASHCARD])

    daten = await _aufrufen("bundle_liste", klasse="FS 23b")
    assert [eintrag["titel"] for eintrag in daten["bundles"]] == ["Eins"]


async def test_leere_liste_ist_kein_fehler(konfiguration, mcp_sitzung):
    daten = await _aufrufen("bundle_liste")
    assert daten["anzahl"] == 0
    assert daten["bundles"] == []


async def test_anzeigen_liefert_karten_mit_ids_und_positionen(konfiguration, mcp_sitzung):
    angelegt = await _aufrufen("bundle_anlegen", titel="T", karten=[FRAGE, FLASHCARD])
    daten = await _aufrufen("bundle_anzeigen", slug=angelegt["slug"])

    assert daten["titel"] == "T"
    assert len(daten["karten"]) == 2
    erste = daten["karten"][0]
    assert erste["position"] == 0
    assert len(erste["karte_id"]) == 36
    assert erste["art"] == "frage"
    # Zurueck als TEXT, nicht als Index: So kann der Agent die Karte
    # unveraendert wieder an karte_aendern uebergeben.
    assert erste["richtige_antwort"] == "Zagreb"
    assert erste["antworten"] == ["Split", "Zagreb", "Dubrovnik", "Rijeka"]


async def test_unbekannter_slug_nennt_das_werkzeug_zum_nachsehen(konfiguration, mcp_sitzung):
    """Die Meldung steht so in der Spec, Abschnitt 5."""
    text = await _fehlertext("bundle_anzeigen", slug="rote-katze-springt")
    assert "rote-katze-springt" in text
    assert "bundle_liste" in text


async def test_die_beschreibung_der_werkzeuge_warnt_vor_keine_der_genannten(konfiguration):
    """Die Spec verlangt diesen Hinweis ausdruecklich in der
    Werkzeugbeschreibung, weil die Reihenfolge gemischt wird."""
    server, _ = mcp_bauen()
    werkzeuge = {eines.name: eines for eines in await server.list_tools()}
    schema = json.dumps(werkzeuge["bundle_anlegen"].input_schema, ensure_ascii=False)
    assert "keine der genannten" in schema
    assert "A und B sind richtig" in schema


async def test_alle_acht_werkzeuge_sind_da(konfiguration):
    """Wird spaeter durch Task 11 und 12 vervollstaendigt - hier stehen erst drei."""
    server, _ = mcp_bauen()
    namen = {eines.name for eines in await server.list_tools()}
    assert {"bundle_anlegen", "bundle_liste", "bundle_anzeigen"} <= namen
```

- [ ] **Step 2: Test laufen lassen**

```bash
uv run pytest tests/test_mcp_werkzeuge_bundles.py -q
```
Erwartet: FAIL, `No module named 'app.mcp.dienste'`.

- [ ] **Step 3: `app/mcp/dienste.py` schreiben**

```python
"""Die Datenbankarbeit hinter den Werkzeugen.

Kennt kein MCP. Jede Ablehnung verlaesst dieses Modul als MCPFehler mit
deutschem Klartext.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.mcp.karten import beschreibung_pruefen, karte_pruefen, klasse_pruefen, titel_pruefen
from app.models import Bundle, Karte
from app.slug import SlugKollision, freien_slug_finden

# Drei Anlaeufe. freien_slug_finden() wuerfelt selbst schon bis zu zehnmal
# und prueft dabei jedes Mal die Datenbank; diese Schleife hier faengt
# ausschliesslich den Wettlauf ab - zwei gleichzeitige Aufrufe, die denselben
# freien Kandidaten ziehen. Dass das dreimal hintereinander passiert, ist bei
# einer Nutzerin ausgeschlossen.
SLUG_VERSUCHE = 3


async def bundle_holen(sitzung: AsyncSession, slug: str) -> Bundle:
    """Das Bundle zu einem Slug.

    Raises:
        MCPFehler: Wenn es keines gibt. Die Meldung nennt das Werkzeug zum
            Nachsehen - so steht sie in der Spec, Abschnitt 5.
    """
    bundle = await sitzung.scalar(select(Bundle).where(Bundle.slug == slug))
    if bundle is None:
        raise MCPFehler(
            f"Ein Lernpaket mit der Adresse „{slug}“ gibt es nicht. Mit "
            "bundle_liste siehst du alle vorhandenen."
        )
    return bundle


async def karte_holen(sitzung: AsyncSession, karte_id: str) -> Karte:
    """Die Karte zu einer ID.

    Raises:
        MCPFehler: Wenn die ID keine ist oder es die Karte nicht gibt.
    """
    try:
        kennung = uuid.UUID(karte_id)
    except (ValueError, AttributeError, TypeError) as fehler:
        raise MCPFehler(
            f"„{karte_id}“ ist keine Karten-ID. Die IDs stehen bei jeder "
            "Karte, die bundle_anzeigen ausgibt."
        ) from fehler
    karte = await sitzung.scalar(select(Karte).where(Karte.id == kennung))
    if karte is None:
        raise MCPFehler(
            f"Eine Karte mit der ID {karte_id} gibt es nicht. Mit "
            "bundle_anzeigen siehst du die IDs aller Karten eines Lernpakets."
        )
    return karte


async def bundle_anlegen(
    sitzung: AsyncSession,
    titel: str,
    beschreibung: str | None,
    klasse: str | None,
    selbsteinschaetzung: bool,
    karten: list[KarteEingabe],
) -> Bundle:
    """Legt ein Lernpaket samt Karten an.

    Alles oder nichts: Die Karten werden vollstaendig geprueft, BEVOR
    irgendetwas geschrieben wird. Ein halb angelegtes Lernpaket waere
    schlimmer als keines, weil niemand sieht, was fehlt.

    Raises:
        MCPFehler: Bei jeder abgelehnten Eingabe und wenn keine freie Adresse
            gefunden wird.
    """
    if not karten:
        raise MCPFehler(
            "Das Lernpaket enthält keine Karten. Bitte gib mindestens eine "
            "Karte an – ein Lernpaket ohne Karten kann niemand üben."
        )
    geprueft = [karte_pruefen(eine, nummer) for nummer, eine in enumerate(karten, start=1)]

    felder = {
        "titel": titel_pruefen(titel),
        "beschreibung": beschreibung_pruefen(beschreibung),
        "klasse": klasse_pruefen(klasse),
        "selbsteinschaetzung": selbsteinschaetzung,
    }

    for _ in range(SLUG_VERSUCHE):
        slug = await freien_slug_finden(sitzung)
        bundle = Bundle(slug=slug, **felder)
        bundle.karten = [
            Karte(position=stelle, **werte) for stelle, werte in enumerate(geprueft)
        ]
        try:
            # begin_nested() setzt einen SAVEPOINT. Schlaegt der Einfuegevorgang
            # am Unique-Constraint fehl, wird nur bis dorthin zurueckgerollt und
            # die Sitzung bleibt benutzbar - ein Rollback der ganzen Transaktion
            # wuerde alles verwerfen, was vorher geschah.
            async with sitzung.begin_nested():
                sitzung.add(bundle)
                await sitzung.flush()
        except IntegrityError as fehler:
            if "uq_bundles_slug" not in str(fehler.orig):
                raise
            # Der Wettlauf aus Spec, Abschnitt 4: Zwischen "ist frei" und
            # "ist eingetragen" hat ein zweiter Aufruf denselben Kandidaten
            # gezogen. Das ist kein Fehler, den die Lehrerin lesen soll,
            # sondern ein Signal, noch einmal zu wuerfeln.
            continue
        return bundle

    raise MCPFehler(
        "Es konnte keine freie Drei-Wort-Adresse gefunden werden. Bitte "
        "versuche es noch einmal."
    )


async def bundles_auflisten(
    sitzung: AsyncSession, klasse: str | None, nur_aktive: bool
) -> list[tuple[Bundle, int]]:
    """Alle Lernpakete mit ihrer Kartenzahl, neueste zuerst."""
    abfrage = (
        select(Bundle, func.count(Karte.id))
        .outerjoin(Karte, Karte.bundle_id == Bundle.id)
        .group_by(Bundle.id)
        .order_by(Bundle.erstellt_am.desc())
    )
    if klasse:
        abfrage = abfrage.where(Bundle.klasse == klasse.strip())
    if nur_aktive:
        abfrage = abfrage.where(Bundle.aktiv.is_(True))
    return [(bundle, anzahl) for bundle, anzahl in (await sitzung.execute(abfrage)).all()]
```

- [ ] **Step 4: `app/mcp/werkzeuge.py` schreiben**

```python
"""Die acht Werkzeuge.

Duenne Huellen: Sie oeffnen eine Sitzung, rufen app/mcp/dienste.py, machen
die Aenderung fest und bauen die Antwort. Jede schreibende Antwort enthaelt
den fertigen Link - so verlangt es die Spec in Abschnitt 5.

Die Fehlerbehandlung steht an genau einer Stelle: im Dekorator
@als_werkzeug. Ein MCPFehler wird zum ToolError des SDK, und dessen Text
kommt beim Agenten als isError-Antwort an. Das SDK stellt dabei das
englische "Error executing tool <name>: " voran - das ist nicht abschaltbar
und in Entscheidung E-7 des Plans begruendet; der deutsche Satz steht
dahinter, und er ist es, den die Lehrerin hoert.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from app.config import get_settings
from app.mcp import dienste
from app.mcp.eingaben import KarteEingabe
from app.mcp.fehler import MCPFehler
from app.models import Bundle
from app.sitzung import sitzung


def als_werkzeug(funktion: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Uebersetzt MCPFehler in die Fehlerantwort des SDK."""

    @functools.wraps(funktion)
    async def huelle(*args: Any, **kwargs: Any) -> Any:
        try:
            return await funktion(*args, **kwargs)
        except MCPFehler as fehler:
            raise ToolError(str(fehler)) from fehler

    return huelle


def url(slug: str) -> str:
    return get_settings().bundle_url(slug)


def uebersicht(bundle: Bundle, anzahl_karten: int) -> dict:
    """Die Kurzform eines Lernpakets - in jeder Antwort dieselbe."""
    return {
        "slug": bundle.slug,
        "url": url(bundle.slug),
        "titel": bundle.titel,
        "beschreibung": bundle.beschreibung or "",
        "klasse": bundle.klasse or "",
        "selbsteinschaetzung": bundle.selbsteinschaetzung,
        "reihenfolge": bundle.reihenfolge,
        "aktiv": bundle.aktiv,
        "anzahl_karten": anzahl_karten,
    }


def karte_ausgeben(karte) -> dict:
    """Eine Karte so, wie der Agent sie zurueckbekommt.

    Die richtige Antwort kommt als TEXT zurueck, nicht als Index: So kann der
    Agent eine Karte unveraendert wieder an karte_aendern uebergeben, ohne
    zwischen zwei Darstellungen umzurechnen.
    """
    daten = {
        "karte_id": str(karte.id),
        "position": karte.position,
        "art": karte.art,
        "vorderseite": karte.vorderseite,
    }
    if karte.art == "flashcard":
        daten["rueckseite"] = karte.rueckseite
        return daten
    antworten = list(karte.antworten or [])
    daten["antworten"] = antworten
    daten["richtige_antwort"] = antworten[karte.richtige_index]
    daten["erklaerung"] = karte.erklaerung or ""
    return daten


def registrieren(server: MCPServer) -> None:
    """Haengt alle Werkzeuge an den Server."""

    @server.tool(
        description=(
            "Legt ein neues Lernpaket an und gibt den fertigen Link zurueck. "
            "Ein Aufruf genuegt fuer ein komplettes Arbeitsblatt: Titel und "
            "alle Karten auf einmal uebergeben.\n\n"
            "WICHTIG fuer Fragen: Benutze KEINE Antwortmoeglichkeiten wie "
            "'keine der genannten' oder 'A und B sind richtig'. Die "
            "Reihenfolge der Antworten wird bei jedem Durchlauf neu gemischt "
            "- solche Moeglichkeiten ergeben danach keinen Sinn mehr."
        )
    )
    @als_werkzeug
    async def bundle_anlegen(
        titel: Annotated[str, Field(description="Ueberschrift der Lernseite.")],
        karten: Annotated[list[KarteEingabe], Field(description="Die Karten des Lernpakets.")],
        beschreibung: Annotated[
            str | None, Field(default=None, description="Optionaler Einleitungstext, Markdown.")
        ] = None,
        klasse: Annotated[
            str | None, Field(default=None, description="Optionale Klassenbezeichnung, z.B. 'FS 23b'.")
        ] = None,
        selbsteinschaetzung: Annotated[
            bool,
            Field(
                default=True,
                description=(
                    "Ob Flashcards beim Ergebnis mitzaehlen ('Wusste ich' / "
                    "'Wusste ich nicht'). Standard: ja."
                ),
            ),
        ] = True,
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_anlegen(
                offene,
                titel=titel,
                beschreibung=beschreibung,
                klasse=klasse,
                selbsteinschaetzung=selbsteinschaetzung,
                karten=karten,
            )
            antwort = uebersicht(bundle, len(bundle.karten))
            await offene.commit()
            return antwort

    @server.tool(
        description=(
            "Listet alle Lernpakete mit Adresse, Link, Titel, Klasse, "
            "Kartenzahl und Zustand auf."
        )
    )
    @als_werkzeug
    async def bundle_liste(
        klasse: Annotated[
            str | None,
            Field(default=None, description="Nur Lernpakete dieser Klasse."),
        ] = None,
        nur_aktive: Annotated[
            bool,
            Field(default=False, description="Deaktivierte Lernpakete weglassen."),
        ] = False,
    ) -> dict:
        async with sitzung() as offene:
            zeilen = await dienste.bundles_auflisten(
                offene, klasse=klasse, nur_aktive=nur_aktive
            )
            return {
                "anzahl": len(zeilen),
                "bundles": [uebersicht(bundle, anzahl) for bundle, anzahl in zeilen],
            }

    @server.tool(
        description=(
            "Zeigt ein Lernpaket mit allen Karten, ihren IDs und ihren "
            "Positionen. Die IDs braucht man fuer karte_aendern und "
            "karte_loeschen."
        )
    )
    @als_werkzeug
    async def bundle_anzeigen(
        slug: Annotated[str, Field(description="Die Drei-Wort-Adresse des Lernpakets.")],
    ) -> dict:
        async with sitzung() as offene:
            bundle = await dienste.bundle_holen(offene, slug)
            karten = sorted(bundle.karten, key=lambda eine: eine.position)
            return {
                **uebersicht(bundle, len(karten)),
                "karten": [karte_ausgeben(eine) for eine in karten],
            }
```

- [ ] **Step 5: Die Werkzeuge in `app/mcp/__init__.py` registrieren**

Den Platzhalterkommentar in `mcp_bauen()` ersetzen durch:

```python
    # Der Import steht hier und nicht oben: app/mcp/werkzeuge.py importiert
    # app.mcp.dienste, und ein Import auf Modulebene ergaebe einen Ringschluss
    # ueber app.mcp.
    from app.mcp.werkzeuge import registrieren

    registrieren(server)
```

- [ ] **Step 6: Tests laufen lassen**

```bash
uv run pytest tests/test_mcp_werkzeuge_bundles.py -q
```
Erwartet: PASS (13 Tests).

- [ ] **Step 7: Gesamte Suite und Commit**

```bash
uv run pytest -q
git add app/mcp/dienste.py app/mcp/werkzeuge.py app/mcp/__init__.py tests/test_mcp_werkzeuge_bundles.py
git commit -m "Werkzeuge bundle_anlegen, bundle_liste und bundle_anzeigen samt Slug-Wettlauf"
```
Erwartet vor dem Commit: `244 passed`, 0 übersprungen, 0 Warnungen.

---
