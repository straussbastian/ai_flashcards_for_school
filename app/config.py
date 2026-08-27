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
    # Pflichtfeld ohne Default. Ein Default wie "http://localhost:8000" liesse
    # die Anwendung im Betrieb anstandslos starten, wenn BASE_URL vergessen
    # wurde - und der MCP-Server aus Plan 2 gaebe der Lehrkraft bei jeder
    # schreibenden Antwort einen fertigen Link zurueck, den niemand aufrufen
    # kann. Ein fehlender Wert soll beim Start auffallen, nicht erst an einem
    # unbrauchbaren Link. Die Spec fuehrt BASE_URL in Abschnitt 3 als
    # Pflichtvariable.
    base_url: str

    @field_validator("base_url")
    @classmethod
    def _basis_url_pruefen(cls, wert: str) -> str:
        """Prueft das Schema und schneidet einen abschliessenden / ab.

        Ohne die Schema-Pruefung wuerde ein Wert wie "karten.example.de"
        (ohne Schema) klaglos angenommen und ergaebe Links der Form
        "karten.example.de/rote-katze-springt" - relativ statt absolut, also
        in einer Chat-Antwort nicht anklickbar. Das faellt erst der Lehrkraft
        auf, nicht beim Start.
        """
        if not wert.startswith(("http://", "https://")):
            raise ValueError(
                "BASE_URL muss mit http:// oder https:// beginnen, "
                f"bekommen habe ich: {wert!r}"
            )
        return wert.rstrip("/")

    def bundle_url(self, slug: str) -> str:
        """Die vollstaendige, teilbare Adresse einer Lernseite."""
        return f"{self.base_url}/{slug}"


@lru_cache
def get_settings() -> Settings:
    """Gibt die gecachte Konfigurationsinstanz zurück. Liest die .env einmalig."""
    return Settings()  # type: ignore[call-arg]
