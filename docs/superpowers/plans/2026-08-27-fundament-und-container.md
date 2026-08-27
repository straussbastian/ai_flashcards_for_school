# Fundament und erreichbarer Container – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein lauffähiges Projektgerüst mit vollständigem Datenmodell, das als einzelner Docker-Container mit eingebautem PostgreSQL **lokal auf dem Entwicklungsrechner** läuft, Daten über Neustarts hinweg behält und im Git so vorbereitet ist, dass Coolify es später selbst zieht.

**Architecture:** Ein FastAPI-Prozess und ein PostgreSQL-17-Server laufen im selben Container unter `supervisord`. Die Datenbank liegt auf `/data/pgdata`, einem gemounteten Volume; fehlt der Mount, verweigert der Container bewusst den Start. Das Datenmodell erzwingt Korrektheit über CHECK-Constraints in der Datenbank, nicht nur in der Anwendung. Dieser Plan baut noch keine MCP-Werkzeuge und keine Lernseite – er stellt das Fundament, auf dem beide aufsetzen.

**Deployment:** In diesem Plan läuft alles lokal – gebaut und gestartet auf dem eigenen Rechner. Coolify holt sich das Repository später eigenständig per CI/CD aus Git; im Repo entsteht deshalb nur alles, was dafür gebraucht wird (`Dockerfile`, dokumentierte Umgebungsvariablen, README), aber es wird in diesem Plan nichts auf einen Server ausgerollt.

**Hinweis für Plan 2:** Cowork erreicht MCP-Server aus Anthropics Cloud, nicht vom Rechner der Lehrkraft. Ein lokal laufender Container ist von dort nicht erreichbar. Der OAuth-Ablauf aus Plan 2 wird deshalb lokal über pytest vollständig geprüft; für den Praxistest mit echtem Cowork braucht es entweder einen Tunnel (`cloudflared tunnel`) oder das spätere Coolify-Deployment. Das ist in Plan 2 zu berücksichtigen, nicht hier.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 (async), psycopg 3, Alembic, pydantic-settings, markdown-it-py, nh3, pytest, uv, Docker, PostgreSQL 17, supervisord.

**Spec:** [docs/superpowers/specs/2026-08-27-flashcards-design.md](../specs/2026-08-27-flashcards-design.md)

## Global Constraints

- Python 3.13, PostgreSQL 17.
- Alle Bezeichner im Datenmodell und in den MCP-Werkzeugen sind **deutsch** (`bundles`, `karten`, `vorderseite`, `richtige_index`). Code, Kommentare und Fehlermeldungen ebenfalls deutsch.
- Keine Geheimnisse im Image und keine im Git. Konfiguration ausschließlich über Umgebungsvariablen, dokumentiert in `.env.example`.
- `PGDATA` ist `/data/pgdata`. `/data` muss ein Mountpoint sein, sonst bricht der Container mit Klartextmeldung ab.
- Kein stdio-MCP, keine Session-Cookies, kein LocalStorage – gilt für das ganze Projekt.
- Antwortmöglichkeiten einer Frage: zwei bis vier. Gespeichert wird `richtige_index` (nullbasierte Position), **nie** ein Buchstabe.
- Jede Aufgabe endet mit einem Commit. Commit-Nachrichten deutsch, im Imperativ.
- Tests laufen gegen eine echte PostgreSQL-Instanz, nicht gegen SQLite. Die Constraints sind der Kern des Modells und existieren in SQLite nicht.

---

## Dateistruktur

Diese Dateien entstehen in diesem Plan:

| Datei | Verantwortung |
|---|---|
| `pyproject.toml` | Abhängigkeiten, pytest-Konfiguration |
| `.env.example` | Dokumentierte Konfiguration, ohne echte Werte |
| `compose.dev.yml` | PostgreSQL nur für die lokale Entwicklung |
| `app/config.py` | Einstellungen aus der Umgebung, URL-Aufbau |
| `app/db.py` | Engine, Session-Fabrik, Session-Abhängigkeit für FastAPI |
| `app/models.py` | `Base`, `Bundle`, `Karte` samt Constraints |
| `app/slug.py` | Drei-Wort-Adressen erzeugen, Kollisionen auflösen |
| `app/woerter/{adjektive,nomen,verben}.txt` | Die Wortlisten |
| `app/markdown.py` | Markdown zu gesäubertem HTML |
| `app/main.py` | FastAPI-App, `/healthz`, Landeseite |
| `migrations/` | Alembic-Umgebung und Migrationen |
| `docker/entrypoint.sh` | Volume-Prüfung, Cluster anlegen, supervisord starten |
| `docker/app-start.sh` | Auf Postgres warten, migrieren, uvicorn starten |
| `docker/backup.sh` | Nächtlicher Dump nach `/data/backups` |
| `docker/supervisord.conf` | Prozessverwaltung |
| `Dockerfile`, `.dockerignore` | Image |
| `README.md` | Betrieb, besonders der Volume-Mount |
| `tests/` | Tests zu allem oben |

Die Trennung folgt der Verantwortung, nicht der technischen Schicht: `slug.py` und `markdown.py` sind eigenständig testbar und werden später von MCP-Werkzeugen *und* Lernseite benutzt.

---

### Task 1: Projektgerüst und Healthcheck

**Files:**
- Create: `pyproject.toml`, `.env.example`, `app/__init__.py`, `app/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: nichts
- Produces: `app.main.app` (FastAPI-Instanz), Route `GET /healthz` → `{"status": "ok"}`, Route `GET /` → HTML mit Status 200

- [ ] **Step 1: Projektdatei anlegen**

`pyproject.toml`:

```toml
[project]
name = "flashcards"
version = "0.1.0"
description = "Flashcards und Fragelisten fuer die Berufsschule"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy>=2.0.36",
    "psycopg[binary]>=3.2",
    "alembic>=1.14",
    "pydantic-settings>=2.7",
    "jinja2>=3.1",
    "markdown-it-py>=3.0",
    "nh3>=0.2.20",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

Dann `uv sync` ausführen. Es entsteht `uv.lock` – die gehört ins Git.

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

`tests/test_main.py`:

```python
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
```

- [ ] **Step 3: Test laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 4: Minimale Umsetzung**

`app/__init__.py`: leer.

`app/main.py`:

```python
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Flashcards", docs_url=None, redoc_url=None, openapi_url=None)

LANDESEITE = """<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Lernkarten</title></head>
<body><p>Diese Seite wird ueber einen Link aufgerufen, den du von deiner Lehrkraft bekommst.</p></body>
</html>"""


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def landeseite() -> str:
    return LANDESEITE
```

Die API-Dokumentation ist bewusst abgeschaltet: Der Server ist öffentlich erreichbar und soll seine Routen nicht auflisten.

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest tests/test_main.py -v`
Expected: 2 passed

- [ ] **Step 6: `.env.example` anlegen**

```bash
# Datenbank. Im Container zeigt die URL auf localhost im selben Container.
POSTGRES_PASSWORD=bitte-aendern
DATABASE_URL=postgresql+psycopg://flashcards:bitte-aendern@localhost:5432/flashcards

# Signaturschluessel fuer OAuth-Tokens. Lang und zufaellig, z.B. `openssl rand -hex 32`.
APP_SECRET=bitte-aendern

# Das eine Passwort, mit dem sich die Lehrkraft beim Verbinden des Connectors anmeldet.
TEACHER_PASSWORD=bitte-aendern

# Oeffentliche Basis-URL ohne abschliessenden Schraegstrich.
BASE_URL=https://karten.example.de

TZ=Europe/Berlin
```

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .env.example app tests
git commit -m "Projektgeruest mit FastAPI und Healthcheck"
```

---

### Task 2: Konfiguration aus der Umgebung

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nichts
- Produces: `app.config.Settings` (Felder `database_url: str`, `app_secret: str`, `teacher_password: str`, `base_url: str`), `app.config.get_settings() -> Settings` (gecacht), `Settings.bundle_url(slug: str) -> str`

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/test_config.py`:

```python
import pytest

from app.config import Settings


def _einstellungen(**abweichungen) -> Settings:
    werte = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/db",
        "app_secret": "geheim",
        "teacher_password": "passwort",
        "base_url": "https://karten.example.de",
    }
    werte.update(abweichungen)
    return Settings(**werte)


def test_bundle_url_wird_aus_basis_und_slug_gebaut():
    einstellungen = _einstellungen()
    assert einstellungen.bundle_url("rote-katze-springt") == "https://karten.example.de/rote-katze-springt"


def test_abschliessender_schraegstrich_wird_entfernt():
    einstellungen = _einstellungen(base_url="https://karten.example.de/")
    assert einstellungen.bundle_url("blaue-ampel-tanzt") == "https://karten.example.de/blaue-ampel-tanzt"


def test_fehlende_pflichtangabe_faellt_auf():
    with pytest.raises(ValueError):
        Settings(database_url="x", app_secret="y", base_url="z")
```

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Minimale Umsetzung**

`app/config.py`:

```python
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Konfiguration. Kommt im Betrieb aus Umgebungsvariablen, lokal aus .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str
    app_secret: str
    teacher_password: str
    base_url: str = "http://localhost:8000"

    @field_validator("base_url")
    @classmethod
    def _ohne_abschliessenden_schraegstrich(cls, wert: str) -> str:
        return wert.rstrip("/")

    def bundle_url(self, slug: str) -> str:
        """Die vollstaendige, teilbare Adresse einer Lernseite."""
        return f"{self.base_url}/{slug}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

`get_settings` ist gecacht, damit die `.env` einmal gelesen wird. Wichtig: **nicht** beim Import eine Instanz anlegen – sonst scheitern Tests ohne gesetzte Umgebung schon beim Einsammeln.

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "Konfiguration aus Umgebungsvariablen"
```

---

### Task 3: Datenbankanbindung und Testumgebung

**Files:**
- Create: `app/db.py`, `compose.dev.yml`, `tests/conftest.py`
- Modify: `app/main.py` (Healthcheck prüft jetzt die Datenbank), `.env.example`
- Test: `tests/test_db.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: `app.config.get_settings`
- Produces: `app.db.Base` (DeclarativeBase), `app.db.engine`, `app.db.SessionLocal` (async_sessionmaker), `app.db.get_session()` (async generator, FastAPI-Abhängigkeit), Fixture `session` in `tests/conftest.py`

- [ ] **Step 1: PostgreSQL für die Entwicklung bereitstellen**

`compose.dev.yml` – **nur für lokale Entwicklung**, im Betrieb läuft Postgres im App-Container:

```yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: flashcards
      POSTGRES_PASSWORD: entwicklung
      POSTGRES_DB: flashcards
    ports:
      - "55432:5432"
    volumes:
      - pgdata-dev:/var/lib/postgresql/data

volumes:
  pgdata-dev:
```

Starten: `docker compose -f compose.dev.yml up -d`

Lokale `.env` (nicht im Git):

```bash
DATABASE_URL=postgresql+psycopg://flashcards:entwicklung@localhost:55432/flashcards
TEST_DATABASE_URL=postgresql+psycopg://flashcards:entwicklung@localhost:55432/flashcards_test
APP_SECRET=entwicklung
TEACHER_PASSWORD=entwicklung
BASE_URL=http://localhost:8000
```

`TEST_DATABASE_URL` zusätzlich in `.env.example` aufnehmen, mit dem Hinweis, dass sie nur für Tests gebraucht wird.

- [ ] **Step 2: Den fehlschlagenden Test schreiben**

`tests/test_db.py`:

```python
from sqlalchemy import text


async def test_datenbank_antwortet(session):
    ergebnis = await session.scalar(text("SELECT 1"))
    assert ergebnis == 1
```

Und in `tests/test_main.py` ergänzen:

```python
def test_healthz_meldet_datenbank_ok():
    antwort = client.get("/healthz")
    assert antwort.json()["datenbank"] == "ok"
```

- [ ] **Step 3: Test laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL – die Fixture `session` gibt es noch nicht

- [ ] **Step 4: Datenbankmodul schreiben**

`app/db.py`:

```python
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Gemeinsame Basis aller Tabellen."""


engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-Abhaengigkeit: eine Session pro Anfrage."""
    async with SessionLocal() as session:
        yield session
```

`pool_pre_ping` fängt ab, dass Postgres im selben Container neu gestartet wurde und alte Verbindungen tot sind.

- [ ] **Step 5: Test-Fixtures schreiben**

`tests/conftest.py`:

```python
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import Base

TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as verbindung:
        await verbindung.run_sync(Base.metadata.drop_all)
        await verbindung.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Eine Session pro Test, die am Ende zurueckgerollt wird."""
    verbindung = await test_engine.connect()
    transaktion = await verbindung.begin()
    fabrik = async_sessionmaker(bind=verbindung, expire_on_commit=False)
    async with fabrik() as sitzung:
        yield sitzung
    await transaktion.rollback()
    await verbindung.close()
```

Jeder Test läuft in einer Transaktion, die zurückgerollt wird – die Tests beeinflussen sich damit nicht gegenseitig, und die Datenbank bleibt sauber.

Die Testdatenbank einmal anlegen:

```bash
docker compose -f compose.dev.yml exec db createdb -U flashcards flashcards_test
```

- [ ] **Step 6: Healthcheck erweitert**

In `app/main.py`:

```python
from fastapi import Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session


@app.get("/healthz")
async def healthz(session: AsyncSession = Depends(get_session)) -> JSONResponse:
    try:
        await session.scalar(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            {"status": "fehler", "datenbank": "nicht erreichbar"}, status_code=503
        )
    return JSONResponse({"status": "ok", "datenbank": "ok"})
```

Der Healthcheck ist die einzige Stelle, an der ein nacktes `except Exception` steht: Er soll jeden Datenbankfehler in ein 503 verwandeln, statt selbst abzustürzen.

- [ ] **Step 7: Tests laufen lassen**

Run: `uv run pytest -v`
Expected: alle Tests grün

- [ ] **Step 8: Commit**

```bash
git add app/db.py app/main.py compose.dev.yml tests/ .env.example
git commit -m "Datenbankanbindung, Testumgebung und Healthcheck mit Datenbankpruefung"
```

---

### Task 4: Datenmodell mit Constraints

**Files:**
- Create: `app/models.py`, `migrations/` (per `alembic init`), `migrations/versions/0001_grundmodell.py`, `alembic.ini`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `app.db.Base`
- Produces: `app.models.Bundle` (Felder `id, slug, titel, beschreibung, klasse, selbsteinschaetzung, reihenfolge, aktiv, erstellt_am, geaendert_am, karten`), `app.models.Karte` (Felder `id, bundle_id, position, art, vorderseite, rueckseite, antworten, richtige_index, erklaerung, erstellt_am, geaendert_am`)

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`tests/test_models.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Bundle, Karte


async def _bundle(session) -> Bundle:
    bundle = Bundle(slug="rote-katze-springt", titel="Hauptstaedte Europas")
    session.add(bundle)
    await session.flush()
    return bundle


async def test_gueltige_flashcard_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Hauptstadt von Kroatien?",
            rueckseite="Zagreb",
        )
    )
    await session.flush()


async def test_gueltige_frage_laesst_sich_speichern(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Hauptstadt von Kroatien?",
            antworten=["Split", "Zagreb", "Rijeka"],
            richtige_index=1,
            erklaerung="Zagreb liegt im Landesinneren.",
        )
    )
    await session.flush()


async def test_flashcard_ohne_rueckseite_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(bundle_id=bundle.id, position=1, art="flashcard", vorderseite="Frage")
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_frage_mit_index_ausserhalb_der_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["A", "B"],
            richtige_index=5,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_frage_mit_fuenf_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="frage",
            vorderseite="Frage",
            antworten=["a", "b", "c", "d", "e"],
            richtige_index=0,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_flashcard_mit_antworten_wird_abgelehnt(session):
    bundle = await _bundle(session)
    session.add(
        Karte(
            bundle_id=bundle.id,
            position=1,
            art="flashcard",
            vorderseite="Frage",
            rueckseite="Antwort",
            antworten=["a", "b"],
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_doppelte_position_im_selben_bundle_wird_abgelehnt(session):
    bundle = await _bundle(session)
    for _ in range(2):
        session.add(
            Karte(
                bundle_id=bundle.id,
                position=1,
                art="flashcard",
                vorderseite="Frage",
                rueckseite="Antwort",
            )
        )
    with pytest.raises(IntegrityError):
        await session.flush()


async def test_unbekannte_reihenfolge_wird_abgelehnt(session):
    session.add(Bundle(slug="blaue-ampel-tanzt", titel="Test", reihenfolge="rueckwaerts"))
    with pytest.raises(IntegrityError):
        await session.flush()
```

- [ ] **Step 2: Tests laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Modelle schreiben**

`app/models.py`:

```python
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Bundle(Base):
    """Eine Lernseite unter einer Drei-Wort-Adresse."""

    __tablename__ = "bundles"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    titel: Mapped[str] = mapped_column(Text, nullable=False)
    beschreibung: Mapped[str | None] = mapped_column(Text)
    klasse: Mapped[str | None] = mapped_column(String(60))
    selbsteinschaetzung: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    reihenfolge: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="zufall"
    )
    aktiv: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    karten: Mapped[list["Karte"]] = relationship(
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="Karte.position",
        lazy="selectin",
    )

    __table_args__ = (
        CheckConstraint(
            "reihenfolge IN ('zufall', 'fest')", name="ck_bundles_reihenfolge"
        ),
    )


class Karte(Base):
    """Eine Flashcard oder eine Multiple-Choice-Frage innerhalb eines Bundles."""

    __tablename__ = "karten"

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bundles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    art: Mapped[str] = mapped_column(String(12), nullable=False)
    vorderseite: Mapped[str] = mapped_column(Text, nullable=False)
    rueckseite: Mapped[str | None] = mapped_column(Text)
    antworten: Mapped[list[str] | None] = mapped_column(JSONB)
    richtige_index: Mapped[int | None] = mapped_column(Integer)
    erklaerung: Mapped[str | None] = mapped_column(Text)
    erstellt_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    bundle: Mapped[Bundle] = relationship(back_populates="karten")

    __table_args__ = (
        UniqueConstraint(
            "bundle_id",
            "position",
            name="uq_karten_bundle_position",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint("art IN ('flashcard', 'frage')", name="ck_karten_art"),
        CheckConstraint(
            """
            (art = 'flashcard'
                AND rueckseite IS NOT NULL
                AND antworten IS NULL
                AND richtige_index IS NULL
                AND erklaerung IS NULL)
            OR
            (art = 'frage'
                AND rueckseite IS NULL
                AND antworten IS NOT NULL
                AND richtige_index IS NOT NULL)
            """,
            name="ck_karten_felder_passen_zur_art",
        ),
        CheckConstraint(
            """
            art <> 'frage'
            OR (jsonb_typeof(antworten) = 'array'
                AND jsonb_array_length(antworten) BETWEEN 2 AND 4)
            """,
            name="ck_karten_antwortanzahl",
        ),
        CheckConstraint(
            """
            art <> 'frage'
            OR (richtige_index >= 0
                AND richtige_index < jsonb_array_length(antworten))
            """,
            name="ck_karten_richtige_index_im_bereich",
        ),
    )
```

Zwei Entscheidungen, die begründet gehören:

Der Unique-Constraint auf `(bundle_id, position)` ist **deferrable**. Beim späteren Umsortieren von Karten wandern mehrere Positionen gleichzeitig; ohne aufgeschobene Prüfung würde jede Zwischenstufe scheitern, obwohl der Endzustand gültig ist.

`richtige_index` statt Buchstabe: Die Antwortreihenfolge wird im Browser bei jedem Durchlauf gemischt, die Buchstaben A–D entstehen erst danach. Ein gespeicherter Buchstabe wäre nach dem ersten Mischen falsch.

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_models.py -v`
Expected: 8 passed

- [ ] **Step 5: Alembic einrichten**

```bash
uv run alembic init -t async migrations
```

In `alembic.ini` die Zeile `sqlalchemy.url = ...` **löschen** – die URL kommt aus der Konfiguration.

In `migrations/env.py` oben ergänzen:

```python
from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401  -- sorgt dafuer, dass die Tabellen registriert sind

datenbank_url = get_settings().database_url
target_metadata = Base.metadata
```

**Die URL darf nicht über `config.set_main_option()` laufen.** Alembic reicht den Wert an einen `ConfigParser` weiter, für den `%` das Interpolationszeichen ist. Ein Datenbankpasswort mit `%` – bei URL-kodierten Passwörtern der Normalfall, `%40` für `@` – lässt dann jedes `alembic upgrade` mit `InterpolationSyntaxError` scheitern. Weil die Migration im Container beim Start läuft, würde das den Start kippen, und zwar erst auf dem Server.

Reiche die URL stattdessen direkt weiter: im Offline-Pfad als `url=datenbank_url`, im Online-Pfad in das Dict, das `config.get_section()` liefert, bevor es an `async_engine_from_config` geht.

- [ ] **Step 6: Migration erzeugen und prüfen**

```bash
uv run alembic revision --autogenerate -m "Grundmodell: bundles und karten"
```

Die erzeugte Datei nach `migrations/versions/` **von Hand durchsehen**: Alle fünf CHECK-Constraints und der deferrable Unique-Constraint müssen enthalten sein. Autogenerate übernimmt Constraints aus `__table_args__`, aber verlassen wird sich darauf nicht – fehlt etwas, wird es ergänzt.

- [ ] **Step 7: Migration gegen eine leere Datenbank prüfen**

```bash
docker compose -f compose.dev.yml exec db dropdb -U flashcards --if-exists flashcards
docker compose -f compose.dev.yml exec db createdb -U flashcards flashcards
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

Expected: alle drei Befehle ohne Fehler. Der Weg zurück und wieder hoch beweist, dass die Migration auch rückwärts sauber ist.

- [ ] **Step 8: Commit**

```bash
git add app/models.py migrations alembic.ini tests/test_models.py
git commit -m "Datenmodell fuer Bundles und Karten mit Constraints in der Datenbank"
```

---

### Task 5: Drei-Wort-Adressen

**Files:**
- Create: `app/slug.py`, `app/woerter/adjektive.txt`, `app/woerter/nomen.txt`, `app/woerter/verben.txt`
- Test: `tests/test_slug.py`

**Interfaces:**
- Consumes: `app.models.Bundle`
- Produces: `app.slug.zufaelliger_slug() -> str`, `app.slug.freien_slug_finden(session: AsyncSession, versuche: int = 10) -> str`, `app.slug.SlugKollision` (Exception)

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`tests/test_slug.py`:

```python
import re

import pytest

from app import slug as slug_modul
from app.models import Bundle
from app.slug import SlugKollision, freien_slug_finden, zufaelliger_slug

FORM = re.compile(r"^[a-z]+-[a-z]+-[a-z]+$")


def test_slug_hat_drei_kleingeschriebene_woerter():
    assert FORM.match(zufaelliger_slug())


def test_alle_woerter_sind_url_tauglich():
    for liste in (slug_modul.ADJEKTIVE, slug_modul.NOMEN, slug_modul.VERBEN):
        assert len(liste) >= 30
        for wort in liste:
            assert re.match(r"^[a-z]+$", wort), f"{wort} ist nicht url-tauglich"


async def test_belegter_slug_wird_uebersprungen(session, monkeypatch):
    session.add(Bundle(slug="rote-katze-springt", titel="Belegt"))
    await session.flush()

    kandidaten = iter(["rote-katze-springt", "blaue-ampel-tanzt"])
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: next(kandidaten))

    assert await freien_slug_finden(session) == "blaue-ampel-tanzt"


async def test_dauerhafte_kollision_meldet_klartext(session, monkeypatch):
    session.add(Bundle(slug="rote-katze-springt", titel="Belegt"))
    await session.flush()
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: "rote-katze-springt")

    with pytest.raises(SlugKollision) as fehler:
        await freien_slug_finden(session, versuche=3)
    assert "Adresse" in str(fehler.value)
```

- [ ] **Step 2: Tests laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_slug.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.slug'`

- [ ] **Step 3: Wortlisten anlegen**

`app/woerter/adjektive.txt`:

```
rote
blaue
gelbe
kluge
leise
laute
schnelle
langsame
kleine
grosse
alte
neue
wilde
ruhige
starke
weiche
harte
runde
flache
spitze
helle
dunkle
warme
kalte
frische
tapfere
freche
brave
stille
weise
```

`app/woerter/nomen.txt`:

```
katze
ampel
birne
wolke
brille
feder
gabel
harfe
insel
kanne
lampe
muschel
nadel
orgel
pfanne
quelle
rakete
schaufel
tasse
vase
waage
zange
blume
kerze
leiter
murmel
palme
raupe
tafel
truhe
```

`app/woerter/verben.txt`:

```
springt
tanzt
singt
lacht
rennt
wartet
blinkt
schwimmt
klettert
winkt
staunt
malt
baut
sammelt
faltet
rollt
huepft
pfeift
brummt
flattert
wandert
leuchtet
klingelt
rutscht
schaukelt
zwitschert
funkelt
purzelt
wippt
klopft
```

Bewusst ohne Umlaute und ohne Sonderzeichen, damit die Adresse ohne Kodierung in jede Adresszeile passt und vorlesbar bleibt. 30 × 30 × 30 ergibt 27.000 Kombinationen – reichlich für eine Schule und nicht durchprobierbar. Wer die Listen erweitert, hält sich an dieselbe Regel; der Test `test_alle_woerter_sind_url_tauglich` erzwingt sie.

- [ ] **Step 4: Slug-Modul schreiben**

`app/slug.py`:

```python
import secrets
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bundle

WOERTER = Path(__file__).parent / "woerter"


def _lade(dateiname: str) -> list[str]:
    zeilen = (WOERTER / dateiname).read_text(encoding="utf-8").splitlines()
    return [zeile.strip() for zeile in zeilen if zeile.strip()]


ADJEKTIVE = _lade("adjektive.txt")
NOMEN = _lade("nomen.txt")
VERBEN = _lade("verben.txt")


class SlugKollision(RuntimeError):
    """Es wurde keine freie Adresse gefunden."""


def zufaelliger_slug() -> str:
    return "-".join(
        (secrets.choice(ADJEKTIVE), secrets.choice(NOMEN), secrets.choice(VERBEN))
    )


async def freien_slug_finden(session: AsyncSession, versuche: int = 10) -> str:
    """Wuerfelt Adressen, bis eine noch nicht vergeben ist."""
    for _ in range(versuche):
        kandidat = zufaelliger_slug()
        belegt = await session.scalar(select(Bundle.id).where(Bundle.slug == kandidat))
        if belegt is None:
            return kandidat
    raise SlugKollision(
        "Es konnte keine freie Drei-Wort-Adresse gefunden werden. "
        "Bitte versuche es noch einmal oder melde dich beim Betreiber der Seite."
    )
```

**Achtung beim Testen:** `freien_slug_finden` ruft `zufaelliger_slug` über das Modul auf, damit `monkeypatch` greift. Ein `from app.slug import zufaelliger_slug` innerhalb des Moduls würde die Ersetzung im Test wirkungslos machen.

- [ ] **Step 5: Tests laufen lassen**

Run: `uv run pytest tests/test_slug.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add app/slug.py app/woerter tests/test_slug.py
git commit -m "Drei-Wort-Adressen mit deutschen Wortlisten und Kollisionsbehandlung"
```

---

### Task 6: Markdown rendern und säubern

**Files:**
- Create: `app/markdown.py`
- Test: `tests/test_markdown.py`

**Interfaces:**
- Consumes: nichts
- Produces: `app.markdown.rendern(text: str | None) -> str` (liefert gesäubertes HTML, bei leerer Eingabe einen leeren String)

- [ ] **Step 1: Die fehlschlagenden Tests schreiben**

`tests/test_markdown.py`:

```python
from app.markdown import rendern


def test_fettschrift_wird_gerendert():
    assert "<strong>wichtig</strong>" in rendern("Das ist **wichtig**.")


def test_aufzaehlung_wird_gerendert():
    ergebnis = rendern("- eins\n- zwei")
    assert "<ul>" in ergebnis
    assert ergebnis.count("<li>") == 2


def test_skript_wird_entfernt():
    ergebnis = rendern("Hallo <script>alert('boese')</script>")
    assert "script" not in ergebnis.lower()
    assert "Hallo" in ergebnis


def test_bild_wird_entfernt():
    ergebnis = rendern("![alt](https://example.com/bild.png)")
    assert "<img" not in ergebnis


def test_link_wird_entfernt_text_bleibt():
    ergebnis = rendern("[Klick mich](javascript:alert(1))")
    assert "<a" not in ergebnis
    assert "Klick mich" in ergebnis


def test_leere_eingabe_ergibt_leeren_string():
    assert rendern(None) == ""
    assert rendern("") == ""
    assert rendern("   ") == ""
```

Bilder und Links sind bewusst nicht erlaubt: Die Spec legt für Karten reinen Text mit einfachem Markdown fest, und ein Link auf einer Lernkarte wäre ein Weg, Lernende von der Seite wegzuführen.

- [ ] **Step 2: Tests laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_markdown.py -v`
Expected: FAIL mit `ModuleNotFoundError: No module named 'app.markdown'`

- [ ] **Step 3: Minimale Umsetzung**

`app/markdown.py`:

```python
import nh3
from markdown_it import MarkdownIt

_renderer = MarkdownIt("commonmark").enable("strikethrough")

ERLAUBTE_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "s",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
    "h3",
    "h4",
}


def rendern(text: str | None) -> str:
    """Markdown zu HTML, anschliessend auf erlaubte Tags reduziert.

    Wird beim Ausliefern der Lernseite aufgerufen. Der Browser bekommt
    fertiges HTML und braucht keinen Markdown-Parser.
    """
    if not text or not text.strip():
        return ""
    roh = _renderer.render(text)
    return nh3.clean(roh, tags=ERLAUBTE_TAGS, attributes={}).strip()
```

`nh3.clean` mit leerem `attributes` entfernt jedes Attribut – damit gibt es keine `onclick`-, `style`- oder `href`-Vektoren, auch nicht an erlaubten Tags.

- [ ] **Step 4: Tests laufen lassen**

Run: `uv run pytest tests/test_markdown.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add app/markdown.py tests/test_markdown.py
git commit -m "Markdown-Rendering mit Saeuberung"
```

---

### Task 7: Der Container

**Files:**
- Create: `Dockerfile`, `.dockerignore`, `docker/entrypoint.sh`, `docker/app-start.sh`, `docker/backup.sh`, `docker/supervisord.conf`
- Test: `tests/test_container.py`

**Interfaces:**
- Consumes: alles Bisherige
- Produces: ein Image, das auf Port 8000 lauscht, `/data` als Datenverzeichnis erwartet und ohne diesen Mount bewusst nicht startet

- [ ] **Step 1: Den fehlschlagenden Test schreiben**

`tests/test_container.py` – ein echter Integrationstest, der das Image baut und startet. Er wird übersprungen, wenn Docker fehlt:

```python
import json
import shutil
import subprocess
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("docker") is None, reason="Docker ist nicht verfuegbar"
)

IMAGE = "flashcards-test"


def _laufen(*befehl: str, pruefen: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(befehl, capture_output=True, text=True, check=pruefen)


@pytest.fixture(scope="module")
def image():
    _laufen("docker", "build", "-t", IMAGE, ".")
    return IMAGE


def test_ohne_volume_bricht_der_container_mit_klartext_ab(image):
    ergebnis = _laufen("docker", "run", "--rm", image, pruefen=False)
    assert ergebnis.returncode != 0
    assert "/data" in (ergebnis.stdout + ergebnis.stderr)


def test_mit_volume_wird_die_seite_erreichbar_und_daten_ueberleben(image, tmp_path):
    name = f"flashcards-{uuid.uuid4().hex[:8]}"
    volume = tmp_path / "daten"
    volume.mkdir()

    def starten() -> None:
        _laufen(
            "docker", "run", "-d", "--name", name,
            "-v", f"{volume}:/data",
            "-e", "POSTGRES_PASSWORD=test",
            "-e", "DATABASE_URL=postgresql+psycopg://flashcards:test@localhost:5432/flashcards",
            "-e", "APP_SECRET=test",
            "-e", "TEACHER_PASSWORD=test",
            "-e", "BASE_URL=http://localhost:8000",
            "-p", "18000:8000",
            image,
        )

    def warten_bis_gesund() -> dict:
        for _ in range(60):
            ergebnis = _laufen(
                "docker", "exec", name,
                "python", "-c",
                "import urllib.request,sys;"
                "sys.stdout.write(urllib.request.urlopen('http://localhost:8000/healthz').read().decode())",
                pruefen=False,
            )
            if ergebnis.returncode == 0 and '"ok"' in ergebnis.stdout:
                return json.loads(ergebnis.stdout)
            time.sleep(2)
        logs = _laufen("docker", "logs", name, pruefen=False)
        pytest.fail(f"Container wurde nicht gesund. Logs:\n{logs.stdout}\n{logs.stderr}")

    try:
        starten()
        gesundheit = warten_bis_gesund()
        assert gesundheit["datenbank"] == "ok"

        # Eine Zeile schreiben, Container neu starten, Zeile muss noch da sein.
        _laufen(
            "docker", "exec", name, "psql", "-U", "flashcards", "-d", "flashcards",
            "-c", "INSERT INTO bundles (id, slug, titel) "
                  "VALUES (gen_random_uuid(), 'rote-katze-springt', 'Test')",
        )
        _laufen("docker", "restart", name)
        warten_bis_gesund()
        zaehlung = _laufen(
            "docker", "exec", name, "psql", "-U", "flashcards", "-d", "flashcards",
            "-tAc", "SELECT count(*) FROM bundles WHERE slug = 'rote-katze-springt'",
        )
        assert zaehlung.stdout.strip() == "1"
    finally:
        _laufen("docker", "rm", "-f", name, pruefen=False)
```

Dieser Test prüft genau das Risiko aus der Spec: Ohne Volume bricht der Start ab, mit Volume überleben die Daten einen Neustart.

- [ ] **Step 2: Test laufen lassen und Fehlschlag bestätigen**

Run: `uv run pytest tests/test_container.py -v`
Expected: FAIL beim Build – es gibt noch kein `Dockerfile`

- [ ] **Step 3: Dockerfile schreiben**

```dockerfile
FROM python:3.13-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PGDATA=/data/pgdata \
    PATH="/usr/lib/postgresql/17/bin:/app/.venv/bin:$PATH" \
    TZ=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-17 \
        postgresql-client-17 \
        supervisor \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY docker ./docker
RUN chmod +x docker/*.sh

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/docker/entrypoint.sh"]
```

- [ ] **Step 4: Einstiegspunkt schreiben**

`docker/entrypoint.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# --- Die kritische Pruefung -------------------------------------------------
# Ohne persistentes Volume waeren alle Lernseiten beim naechsten Deploy weg.
# Lieber gar nicht starten als still Daten verlieren.
if ! mountpoint -q /data; then
    if [ "${ALLOW_EPHEMERAL_DATA:-0}" != "1" ]; then
        echo "FEHLER: /data ist kein gemountetes Volume." >&2
        echo "" >&2
        echo "Die Datenbank liegt in /data. Ohne persistentes Volume waeren alle" >&2
        echo "Lernseiten nach dem naechsten Deployment verloren." >&2
        echo "" >&2
        echo "In Coolify unter 'Persistent Storage' ein Volume auf /data anlegen." >&2
        echo "Nur zum lokalen Ausprobieren: ALLOW_EPHEMERAL_DATA=1 setzen." >&2
        exit 1
    fi
    echo "WARNUNG: /data ist kein Volume. Daten gehen beim Stoppen verloren." >&2
fi

mkdir -p /data/pgdata /data/backups
chown -R postgres:postgres /data/pgdata
chmod 700 /data/pgdata

if [ ! -s "$PGDATA/PG_VERSION" ]; then
    echo "Erststart: Datenbank-Cluster wird angelegt."
    su postgres -c "initdb --encoding=UTF8 --locale=C.UTF-8 --auth-local=trust --auth-host=scram-sha-256"
    echo "listen_addresses = 'localhost'" >> "$PGDATA/postgresql.conf"
    touch /data/.cluster-neu
fi

exec supervisord -c /app/docker/supervisord.conf
```

- [ ] **Step 5: Startskript der Anwendung schreiben**

`docker/app-start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Warte auf PostgreSQL ..."
for _ in $(seq 1 60); do
    if pg_isready -h localhost -q; then break; fi
    sleep 1
done
pg_isready -h localhost -q || { echo "PostgreSQL ist nicht hochgekommen." >&2; exit 1; }

if [ -f /data/.cluster-neu ]; then
    echo "Lege Rolle und Datenbank an."
    psql -U postgres -h localhost -v ON_ERROR_STOP=1 <<SQL
CREATE ROLE flashcards LOGIN PASSWORD '${POSTGRES_PASSWORD}';
CREATE DATABASE flashcards OWNER flashcards;
SQL
    rm -f /data/.cluster-neu
fi

echo "Fuehre Migrationen aus."
alembic upgrade head

echo "Starte Webserver."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
```

`--proxy-headers` ist nötig, weil Coolify einen Reverse Proxy davorsetzt und die Anwendung sonst `http` statt `https` sieht.

- [ ] **Step 6: Backup-Skript schreiben**

`docker/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Coolifys Datenbank-Backups greifen nicht, weil Postgres im App-Container laeuft.
# Deshalb ein eigener Dump ins selbe Volume, das Deployments ueberlebt.
ZIEL="/data/backups/flashcards-$(date +%Y-%m-%d-%H%M).sql.gz"
pg_dump -U flashcards -h localhost flashcards | gzip > "$ZIEL"
echo "Backup geschrieben: $ZIEL"

# Nur die sieben juengsten behalten.
ls -1t /data/backups/flashcards-*.sql.gz | tail -n +8 | xargs -r rm --
```

- [ ] **Step 7: Prozessverwaltung schreiben**

`docker/supervisord.conf`:

```ini
[supervisord]
nodaemon=true
logfile=/dev/null
logfile_maxbytes=0
user=root

[program:postgres]
command=/usr/lib/postgresql/17/bin/postgres -D /data/pgdata
user=postgres
autorestart=true
priority=10
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

[program:app]
command=/app/docker/app-start.sh
directory=/app
autorestart=true
priority=20
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0

[program:backup]
command=/bin/bash -c "while true; do sleep 86400; /app/docker/backup.sh || true; done"
autorestart=true
priority=30
stdout_logfile=/dev/fd/1
stdout_logfile_maxbytes=0
stderr_logfile=/dev/fd/2
stderr_logfile_maxbytes=0
```

- [ ] **Step 8: `.dockerignore` schreiben**

```
.git
.venv
.env
.env.*
.superpowers
docs
tests
compose.dev.yml
__pycache__
*.pyc
.pytest_cache
.ruff_cache
```

- [ ] **Step 9: Container-Tests laufen lassen**

Run: `uv run pytest tests/test_container.py -v`
Expected: 2 passed. Der erste Lauf dauert wegen des Image-Builds mehrere Minuten.

Schlägt der zweite Test fehl, zuerst `docker logs` des Testcontainers ansehen – die Meldung steht im pytest-Fehlertext.

- [ ] **Step 10: Commit**

```bash
git add Dockerfile .dockerignore docker tests/test_container.py
git commit -m "Container mit PostgreSQL, supervisord, Volume-Pruefung und Backup"
```

---

### Task 8: README und lokaler Betrieb

**Files:**
- Create: `README.md`, `run-local.sh`
- Test: manuelle Abnahme gegen den lokal laufenden Container

**Interfaces:**
- Consumes: das Image aus Task 7
- Produces: ein lokal laufender Container unter `http://localhost:8000`, dessen `/healthz` mit `{"status": "ok", "datenbank": "ok"}` antwortet und dessen Daten einen Neustart überleben. Das Repository enthält danach alles, was Coolify später für ein eigenständiges CI/CD-Deployment braucht.

- [ ] **Step 1: README schreiben**

`README.md`:

````markdown
# Flashcards für die Berufsschule

Lernseiten mit Karteikarten und Multiple-Choice-Fragen. Jede Seite hat eine
Adresse aus drei Wörtern, zum Beispiel `/rote-katze-springt`. Keine Anmeldung
für Lernende, keine gespeicherten Ergebnisse.

Gepflegt werden die Inhalte über einen MCP-Server, also durch einen KI-Agenten.
Es gibt bewusst keine Administrationsoberfläche.

## Das Wichtigste zuerst: das Volume

Die Datenbank läuft **im selben Container** wie die Anwendung und liegt unter
`/data/pgdata`. In Coolify muss unter *Persistent Storage* ein Volume auf
`/data` angelegt sein.

Ohne dieses Volume startet der Container bewusst nicht – lieber ein klarer
Fehler als stillschweigend verlorene Lernseiten.

## Entwicklung

```bash
uv sync
docker compose -f compose.dev.yml up -d
cp .env.example .env          # Werte anpassen
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Tests:

```bash
docker compose -f compose.dev.yml exec db createdb -U flashcards flashcards_test
uv run pytest
```

Die Container-Tests bauen das Image und brauchen ein laufendes Docker. Ohne
Docker werden sie übersprungen.

## Den Container lokal betreiben

```bash
./run-local.sh
```

Das Skript baut das Image, legt `./daten` als Volume an und startet den
Container auf `http://localhost:8000`. Prüfen:

```bash
curl -s http://localhost:8000/healthz
```

Stoppen mit `docker rm -f flashcards-lokal`. Das Verzeichnis `./daten` bleibt
liegen – beim nächsten Start ist alles wieder da.

## Betrieb auf Coolify (später)

Coolify zieht sich das Repository selbst per CI/CD. Einzurichten ist dort:

1. Neue Anwendung aus diesem Git-Repository, Build über das `Dockerfile`
2. **Persistent Storage: Volume auf `/data`** – ohne das startet der Container nicht
3. Umgebungsvariablen aus `.env.example` setzen, `BASE_URL` auf die echte Domain
4. Domain zuweisen, HTTPS aktivieren
5. Healthcheck auf `/healthz`

## Backups

Ein Dump landet täglich unter `/data/backups`, sieben Generationen werden
behalten. Wiederherstellen:

```bash
gunzip -c /data/backups/flashcards-JJJJ-MM-TT-HHMM.sql.gz \
  | psql -U flashcards -d flashcards
```

## Aufbau

| Verzeichnis | Inhalt |
|---|---|
| `app/` | Anwendung |
| `migrations/` | Alembic |
| `docker/` | Startskripte und Prozessverwaltung |
| `docs/superpowers/specs/` | Design-Spec |
| `docs/design/mockups/` | Freigegebene Entwürfe – Referenz für die Optik |
````

- [ ] **Step 2: Startskript für den lokalen Betrieb schreiben**

`run-local.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

NAME=flashcards-lokal
DATEN="$(pwd)/daten"

mkdir -p "$DATEN"

docker build -t flashcards .
docker rm -f "$NAME" 2>/dev/null || true

docker run -d --name "$NAME" \
    -v "$DATEN:/data" \
    -e POSTGRES_PASSWORD=lokal \
    -e DATABASE_URL='postgresql+psycopg://flashcards:lokal@localhost:5432/flashcards' \
    -e APP_SECRET=lokal-nur-zum-entwickeln \
    -e TEACHER_PASSWORD=lokal \
    -e BASE_URL=http://localhost:8000 \
    -p 8000:8000 \
    flashcards

echo "Container laeuft. Logs: docker logs -f $NAME"
echo "Pruefen:              curl -s http://localhost:8000/healthz"
```

Ausführbar machen und `daten/` in die `.gitignore` aufnehmen:

```bash
chmod +x run-local.sh
echo "daten/" >> .gitignore
```

- [ ] **Step 3: Container lokal starten**

```bash
./run-local.sh
docker logs -f flashcards-lokal
```

Expected in den Logs, in dieser Reihenfolge: „Erststart: Datenbank-Cluster wird angelegt.", „Lege Rolle und Datenbank an.", die Alembic-Migration, „Starte Webserver."

Der erste Start dauert länger, weil das Cluster angelegt wird.

- [ ] **Step 4: Abnahme**

```bash
curl -s http://localhost:8000/healthz
```

Expected: `{"status":"ok","datenbank":"ok"}`

```bash
curl -s http://localhost:8000/ | head -5
```

Expected: die Landeseite, ohne jede Aufzählung von Bundles.

```bash
docker exec flashcards-lokal psql -U flashcards -d flashcards -c "\dt"
```

Expected: die Tabellen `bundles`, `karten` und `alembic_version`.

- [ ] **Step 5: Prüfen, dass die Daten einen Neustart überstehen**

```bash
docker exec flashcards-lokal psql -U flashcards -d flashcards \
  -c "INSERT INTO bundles (id, slug, titel) VALUES (gen_random_uuid(), 'rote-katze-springt', 'Erster Test')"
docker rm -f flashcards-lokal
./run-local.sh
sleep 20
docker exec flashcards-lokal psql -U flashcards -d flashcards \
  -tAc "SELECT titel FROM bundles WHERE slug = 'rote-katze-springt'"
```

Expected: `Erster Test`

Das ist die eigentliche Abnahme dieses Plans: Das Fundament steht, läuft lokal, und ein kompletter Neustart des Containers löscht nichts.

- [ ] **Step 6: Commit und pushen**

```bash
git add README.md run-local.sh .gitignore
git commit -m "README und Startskript fuer den lokalen Betrieb"
git push -u origin main
```

Damit liegt im Repository alles, was Coolify später braucht: `Dockerfile`, dokumentierte Umgebungsvariablen und die Anforderung an das `/data`-Volume. Eingerichtet wird dort nichts in diesem Plan.

---

## Selbstprüfung des Plans

**Abdeckung der Spec:** Abschnitt 3 der Spec (Architektur, Volume, Backups, Routen `/healthz` und `/`, Konfiguration) liegt in den Tasks 1, 2, 3, 7 und 8. Abschnitt 4 (Datenmodell, Constraints, Slug-Erzeugung) in den Tasks 4 und 5. Das Markdown-Rendering aus Abschnitt 6 in Task 6.

**Bewusst nicht in diesem Plan** und den Folgeplänen zugeordnet:

- Abschnitt 5 der Spec, MCP-Server und OAuth → **Plan 2**
- Abschnitt 6 der Spec, Lernseite und Runner, sowie die Routen `/{slug}`, 404 und 410 → **Plan 3**
- Die Playwright-Tests und der Screenshot-Abgleich gegen die Mockups → **Plan 3**
- Abschnitt 9 der Spec, das Einrichten in Coolify → **später**, wenn das Repository steht. Coolify zieht sich das Repo per CI/CD selbst; dieser Plan bereitet nur alles Nötige vor und betreibt den Container lokal.

**Namensgleichheit geprüft:** `richtige_index` heißt in Modell, Tests, Constraints und Spec gleich. `freien_slug_finden`, `zufaelliger_slug`, `rendern`, `get_settings`, `get_session`, `Base`, `Bundle`, `Karte` werden in allen Tasks identisch geschrieben.

**Keine Platzhalter:** Jeder Schritt enthält den vollständigen Inhalt – es gibt kein „analog zu Task N" und kein „Fehlerbehandlung ergänzen".
