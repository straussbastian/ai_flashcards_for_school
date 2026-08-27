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
    """Gibt die gecachte Konfigurationsinstanz zurück. Liest die .env einmalig."""
    return Settings()  # type: ignore[call-arg]
