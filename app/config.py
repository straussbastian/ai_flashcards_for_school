from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Zeichen, die in einer zusaetzlichen Rueckadresse nichts verloren haben. Der
# Ursprung der Adresse wird in die Content-Security-Policy der
# Zustimmungsseite geschrieben (app/sicherheit.py); dort trennen Leerraum,
# Semikolon und Komma Quellen und Anweisungen, und Anfuehrungszeichen leiten
# Schluesselwoerter wie 'unsafe-inline' ein.
_VERBOTEN_IN_RUECKADRESSEN = frozenset(" \t\r\n;,'\"")


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
    # Weitere OAuth-Rueckadressen neben claude.ai und Loopback, z.B. die
    # Callback-URL einer n8n-Instanz. Kommt als Klartext mit Kommas aus der
    # Umgebung; NoDecode haelt pydantic-settings davon ab, den Wert als JSON
    # zu lesen. Leer ist der Normalfall: Dann gilt genau, was die Spec nennt.
    extra_redirect_uris: Annotated[tuple[str, ...], NoDecode] = ()

    @field_validator("extra_redirect_uris", mode="before")
    @classmethod
    def _rueckadressen_pruefen(cls, wert: object) -> tuple[str, ...]:
        """Trennt an Kommas und laesst nur saubere https-Adressen durch.

        Ein Tippfehler soll beim Start auffallen und nicht erst, wenn
        jemand in n8n auf "Connect" klickt und eine Fehlermeldung bekommt,
        die nichts ueber die Ursache sagt.
        """
        if isinstance(wert, str):
            wert = wert.split(",")
        adressen = tuple(teil.strip() for teil in wert if teil.strip())
        for adresse in adressen:
            teile = urlsplit(adresse)
            if (
                teile.scheme != "https"
                or not teile.hostname
                or teile.fragment
                or teile.username is not None
                or _VERBOTEN_IN_RUECKADRESSEN.intersection(adresse)
            ):
                raise ValueError(
                    "EXTRA_REDIRECT_URIS darf nur vollstaendige https-Adressen "
                    "ohne Fragment, Zugangsdaten, Leerzeichen, Semikolon oder "
                    f"Anfuehrungszeichen enthalten, bekommen habe ich: {adresse!r}"
                )
        return adressen

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
