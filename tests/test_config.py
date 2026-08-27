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
