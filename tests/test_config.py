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


def test_fehlende_pflichtangabe_faellt_auf():
    with pytest.raises(ValueError):
        Settings(_env_file=None, database_url="x", app_secret="y", base_url="z")


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
