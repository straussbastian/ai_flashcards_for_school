import pytest

from app.config import Settings, get_settings


def _einstellungen(**abweichungen) -> Settings:
    werte = {
        "database_url": "postgresql+psycopg://u:p@localhost:5432/db",
        "app_secret": "geheim",
        "teacher_password": "passwort",
        "base_url": "https://karten.example.de",
    }
    werte.update(abweichungen)
    return Settings(_env_file=None, **werte)


def test_bundle_url_wird_aus_basis_und_slug_gebaut():
    einstellungen = _einstellungen()
    assert einstellungen.bundle_url("rote-katze-springt") == "https://karten.example.de/rote-katze-springt"


def test_abschliessender_schraegstrich_wird_entfernt():
    einstellungen = _einstellungen(base_url="https://karten.example.de/")
    assert einstellungen.bundle_url("blaue-ampel-tanzt") == "https://karten.example.de/blaue-ampel-tanzt"


def test_fehlende_pflichtangabe_faellt_auf(monkeypatch):
    """Stellt sicher, dass teacher_password wirklich erforderlich ist.

    Löscht Umgebungsvariablen, die den Test verfälschen würden, damit
    er unabhängig von der Umgebung des Ausführenden läuft.
    """
    # Umgebungsvariablen löschen, die den Test verfälschen könnten
    monkeypatch.delenv("TEACHER_PASSWORD", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_SECRET", raising=False)
    monkeypatch.delenv("BASE_URL", raising=False)

    # base_url ist hier bewusst gültig: Seit base_url ein Pflichtfeld mit
    # Schema-Prüfung ist, würde ein Wert wie "z" schon am Validator
    # scheitern - der Test wäre grün, ohne über teacher_password irgendetwas
    # auszusagen.
    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="x",
            app_secret="y",
            base_url="https://karten.example.de",
        )


def test_fehlende_basis_url_faellt_auf(monkeypatch):
    """BASE_URL ist Pflicht und hat keinen Default.

    Vorher stand in app/config.py `base_url: str = "http://localhost:8000"`.
    Fehlte die Variable im Betrieb, startete die Anwendung anstandslos und
    der MCP-Server aus Plan 2 händigte der Lehrkraft bei jeder schreibenden
    Antwort einen `http://localhost:8000/...`-Link aus, den niemand aufrufen
    kann. Die Spec führt BASE_URL in Abschnitt 3 als Pflichtvariable.
    """
    monkeypatch.delenv("BASE_URL", raising=False)

    with pytest.raises(ValueError):
        Settings(
            _env_file=None,
            database_url="x",
            app_secret="y",
            teacher_password="z",
        )


@pytest.mark.parametrize(
    "wert",
    [
        pytest.param("karten.example.de", id="ohne_schema"),
        pytest.param("ftp://karten.example.de", id="falsches_schema"),
        pytest.param("", id="leer"),
    ],
)
def test_basis_url_ohne_http_schema_faellt_auf(wert):
    """Ein Wert ohne http:// oder https:// ergibt keinen anklickbaren Link.

    "karten.example.de/rote-katze-springt" ist eine relative Adresse. In der
    Chat-Antwort an die Lehrkraft sähe sie beinahe richtig aus und führte
    doch ins Leere - ein Fehler, der erst beim Klicken auffällt statt beim
    Start.
    """
    with pytest.raises(ValueError):
        _einstellungen(base_url=wert)


def test_gueltige_schemata_werden_angenommen():
    assert _einstellungen(base_url="http://localhost:8000").base_url == (
        "http://localhost:8000"
    )
    assert _einstellungen(base_url="https://karten.example.de").base_url == (
        "https://karten.example.de"
    )


@pytest.fixture
def _geleerte_cache():
    """Leert den get_settings-Cache vor und nach dem Test."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_get_settings_liest_die_umgebung(monkeypatch, _geleerte_cache):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:pw@db:5432/testdb")
    monkeypatch.setenv("APP_SECRET", "test-geheim")
    monkeypatch.setenv("TEACHER_PASSWORD", "test-passwort")
    monkeypatch.setenv("BASE_URL", "https://test.example.com")

    einstellungen = get_settings()

    assert einstellungen.database_url == "postgresql://test:pw@db:5432/testdb"
    assert einstellungen.app_secret == "test-geheim"
    assert einstellungen.teacher_password == "test-passwort"
    assert einstellungen.base_url == "https://test.example.com"


def test_get_settings_ist_gecacht(monkeypatch, _geleerte_cache):
    monkeypatch.setenv("DATABASE_URL", "postgresql://cached:pw@db:5432/cachedb")
    monkeypatch.setenv("APP_SECRET", "cached-geheim")
    monkeypatch.setenv("TEACHER_PASSWORD", "cached-passwort")
    monkeypatch.setenv("BASE_URL", "https://cached.example.com")

    erste_instanz = get_settings()
    zweite_instanz = get_settings()

    assert erste_instanz is zweite_instanz


# ---- EXTRA_REDIRECT_URIS ---------------------------------------------------
#
# Weitere OAuth-Rueckadressen neben claude.ai und Loopback, z.B. die einer
# n8n-Instanz. Die Variable kommt als Klartext mit Kommas aus .env bzw.
# Coolify - nicht als JSON-Liste, die niemand von Hand richtig eintippt.

N8N = "https://n8n.example.de/rest/oauth2-credential/callback"
MAKE = "https://hook.example.com/oauth/cb/mcp"


def test_ohne_zusaetzliche_rueckadressen_ist_die_liste_leer():
    assert _einstellungen().extra_redirect_uris == ()


def test_zusaetzliche_rueckadressen_werden_an_kommas_getrennt():
    einstellungen = _einstellungen(extra_redirect_uris=f" {N8N} , {MAKE},")
    assert einstellungen.extra_redirect_uris == (N8N, MAKE)


def test_zusaetzliche_rueckadressen_kommen_als_klartext_aus_der_umgebung(
    monkeypatch, _geleerte_cache
):
    """pydantic-settings liest eine Sammlung sonst als JSON und scheitert
    schon beim Start an einer gewoehnlichen Adresse."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:pw@db:5432/testdb")
    monkeypatch.setenv("APP_SECRET", "test-geheim")
    monkeypatch.setenv("TEACHER_PASSWORD", "test-passwort")
    monkeypatch.setenv("BASE_URL", "https://test.example.com")
    monkeypatch.setenv("EXTRA_REDIRECT_URIS", f"{N8N},{MAKE}")

    assert get_settings().extra_redirect_uris == (N8N, MAKE)


@pytest.mark.parametrize(
    "wert",
    [
        pytest.param("http://n8n.example.de/callback", id="ohne_https"),
        pytest.param("n8n.example.de/callback", id="ohne_schema"),
        pytest.param("https:///callback", id="ohne_host"),
        pytest.param("https://n8n.example.de/callback#oben", id="mit_fragment"),
        pytest.param("https://nutzer:pw@n8n.example.de/callback", id="mit_zugangsdaten"),
        pytest.param("https://n8n.example.de/call back", id="mit_leerzeichen"),
        pytest.param("https://n8n.example.de/cb;script-src", id="mit_semikolon"),
        pytest.param("https://n8n.example.de/cb'x", id="mit_hochkomma"),
    ],
)
def test_untaugliche_zusaetzliche_rueckadresse_faellt_beim_start_auf(wert):
    """Ein Tippfehler soll beim Start auffallen, nicht erst beim Verbinden.

    Leerzeichen, Semikolon und Hochkomma sind zusaetzlich deshalb verboten,
    weil der Ursprung der Adresse in die Content-Security-Policy der
    Zustimmungsseite geschrieben wird - dort trennen genau diese Zeichen
    Anweisungen und Quellen.
    """
    with pytest.raises(ValueError):
        _einstellungen(extra_redirect_uris=wert)
