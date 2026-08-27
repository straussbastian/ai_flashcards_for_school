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
