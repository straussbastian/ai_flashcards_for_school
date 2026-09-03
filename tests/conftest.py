import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx2
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import models  # noqa: F401 -- registriert die Tabellen bei Base.metadata
from app.oauth import modelle as oauth_modelle  # noqa: F401 -- registriert die OAuth-Tabellen
from app.db import Base, get_session
from app.main import app


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Erzeugt die Engine fuer die Testdatenbank.

    TEST_DATABASE_URL wird bewusst erst hier gelesen und nicht auf
    Modulebene: Faehlt die Variable, sollen nur die Tests uebersprungen
    werden, die tatsaechlich eine Datenbank brauchen. Ein Fehlschlag beim
    Einlesen des Moduls wuerde sonst das Einsammeln aller Tests verhindern,
    auch solcher ohne Datenbankbezug (z.B. tests/test_config.py).
    """
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip(
            "TEST_DATABASE_URL ist nicht gesetzt. Die Suite laeuft im Container, "
            "der Datenbank und Variablen selbst mitbringt: "
            "docker compose -f compose.test.yml up --build "
            "--abort-on-container-exit --exit-code-from test"
        )

    engine = create_async_engine(test_database_url)
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
    # join_transaction_mode="create_savepoint": Ohne dieses Flag benutzt die
    # Session den Modus "rollback_only" (SQLAlchemy-Default fuer eine bereits
    # begonnene, nicht verschachtelte Connection-Transaktion). Darin leitet
    # ein automatisches Session-Rollback - wie es SQLAlchemy nach einem
    # fehlgeschlagenen flush() ausloest, siehe Constraint-Tests in
    # tests/test_models.py - direkt an "transaktion" oben weiter und beendet
    # sie. Der spaetere, hier unten stehende await transaktion.rollback()
    # liefe dann ins Leere und SQLAlchemy warnt mit "transaction already
    # deassociated from connection". Mit "create_savepoint" arbeitet die
    # Session stattdessen in einem eigenen SAVEPOINT, sodass die aeussere
    # Transaktion bis zum expliziten Rollback unten unangetastet bleibt.
    fabrik = async_sessionmaker(
        bind=verbindung, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    async with fabrik() as sitzung:
        yield sitzung
    await transaktion.rollback()
    await verbindung.close()


@pytest_asyncio.fixture
async def datenbank_override(session: AsyncSession) -> AsyncGenerator[None, None]:
    """Ueberschreibt die App-Abhaengigkeit get_session mit der Testsession.

    Ohne diesen Override wuerden Anfragen ueber Depends(get_session) die
    echte Entwicklungsdatenbank (DATABASE_URL) treffen statt der
    Testdatenbank. Wird nicht direkt von Tests angefordert, sondern von der
    Fixture "client" unten - so ist die Absicherung an den TestClient
    gekoppelt statt an das Erinnerungsvermoegen einzelner Testdateien.
    Raeumt sich danach selbst wieder ab.
    """
    app.dependency_overrides[get_session] = lambda: session
    yield
    del app.dependency_overrides[get_session]


@pytest.fixture
def client(datenbank_override: None) -> TestClient:
    """Ein TestClient, dessen Datenbank-Abhaengigkeit zwangslaeufig die Testsession benutzt.

    Jeder Test, der einen Client braucht, fordert diese Fixture an und
    bekommt den Override automatisch mit - ohne dass die einzelne Testdatei
    selbst daran denken muss (Sicherheitsgarantie statt Opt-in).
    """
    return TestClient(app)


@pytest_asyncio.fixture
async def klient(datenbank_override: None) -> AsyncGenerator[httpx2.AsyncClient, None]:
    """Asynchrones Gegenstueck zu "client", fuer async-def-Tests.

    Der synchrone TestClient (siehe "client" oben) fuehrt die App in einem
    eigenen Thread mit eigenem Event-Loop aus; die Testsession haengt am
    Loop des Tests. Bei einem synchronen Test laeuft der aeussere Loop
    waehrenddessen nicht mit, deshalb funktioniert das dort. Ein
    async-def-Test laesst den aeusseren Loop aber mitlaufen - dann arbeiten
    zwei Event-Loops auf derselben Datenbankverbindung, was zu sporadischen
    Haengern fuehrt. httpx2.AsyncClient mit ASGITransport ruft die App direkt
    im Loop des Tests auf, ganz ohne eigenen Thread, und vermeidet das.

    Bekommt denselben Datenbank-Override wie "client", aus demselben Grund:
    Die Absicherung gegen die Entwicklungsdatenbank darf nicht davon
    abhaengen, dass eine Testdatei daran denkt.

    Achtung: ASGITransport fuehrt anders als TestClient keinen Lifespan
    (startup/shutdown) aus. Heute folgenlos, da app.main keine
    Lifespan-Handler registriert - kommt spaeter einer dazu, liefe er in
    allen Tests ueber "klient" still nicht mit, waehrend Tests ueber
    "client" ihn ausfuehren.
    """
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as instanz:
        yield instanz


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

    # run() gehalten wird in einer eigenen Task, nicht direkt hier: Der
    # Sitzungsverwalter oeffnet darin eine anyio-Taskgruppe, und anyio
    # verlangt, dass ihr Gueltigkeitsbereich in DERSELBEN Task verlassen
    # wird, in der er betreten wurde. pytest-asyncio fuehrt Aufbau und
    # Abbau einer async-Fixture aber in zwei verschiedenen Tasks aus - ohne
    # diesen Umweg scheitert der Abbau mit "Attempted to exit cancel scope
    # in a different task than it was entered in". Im Betrieb macht der
    # Lifespan in app/main.py genau dasselbe: eine Task haelt run() offen,
    # waehrend die Anfragen in anderen Tasks laufen.
    bereit = asyncio.Event()
    beenden = asyncio.Event()

    async def halten():
        async with server.session_manager.run():
            bereit.set()
            await beenden.wait()

    aufgabe = asyncio.create_task(halten())
    await bereit.wait()
    yield server
    beenden.set()
    await aufgabe
    mcp_bauen.cache_clear()


def mit_adresse(sitzung, eintrag, art: str = "paket"):
    """Traegt ein Lernpaket oder eine Sammlung samt seiner Adresse ein.

    Seit es die Tabelle "adressen" gibt, kann ein Lernpaket nicht mehr
    ohne sie bestehen - bundles.slug ist ein Fremdschluessel darauf. Im
    Betrieb erledigt das freien_slug_finden(), das die Adresse gleich
    reserviert. Tests, die ein Lernpaket mit einer selbst gewaehlten
    Adresse anlegen, gehen daran vorbei und muessen sie selbst eintragen.

    Bewusst ein Helfer und kein automatischer Haken am Modell: Ein
    Lernpaket ohne Adresse SOLL scheitern. Wuerde die Adresse still
    nachgetragen, faende ein Fehler, der genau das versaeumt, nie statt.
    """
    from app.models import Adresse

    sitzung.add(Adresse(slug=eintrag.slug, art=art))
    sitzung.add(eintrag)
    return eintrag
