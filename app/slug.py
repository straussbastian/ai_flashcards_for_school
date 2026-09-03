import secrets
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Adresse

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


async def freien_slug_finden(
    session: AsyncSession, art: str = "paket", versuche: int = 10
) -> str:
    """Wuerfelt Adressen, bis eine frei ist - und traegt sie gleich ein.

    Frueher wurde nur GEFRAGT ("gibt es diesen Slug schon?") und danach
    geschrieben. Zwischen Frage und Antwort lag ein Wettlauf, den der
    Aufrufer mit einer eigenen Wiederholschleife abfangen musste.

    Jetzt ist Pruefen und Belegen ein Schritt: Der Eintrag in adressen ist
    der Anspruch auf die Adresse. Gewinnt ihn ein anderer Aufruf, scheitert
    das INSERT am Primaerschluessel, und hier wird einfach weitergewuerfelt.
    Der Aufrufer braucht dafuer nichts mehr zu tun.

    Das ist ausserdem die Stelle, an der beide Arten zusammenkommen: Weil
    Lernpakete und Sammlungen ihre Adressen aus derselben Tabelle nehmen,
    kann eine Sammlung keine Adresse bekommen, die schon ein Lernpaket
    traegt - und umgekehrt.

    Args:
        art: "paket" oder "sammlung". Steht in der Adresstabelle und sagt
            der Route, was sie unter dieser Adresse ausliefern soll.

    Raises:
        SlugKollision: Wenn nach "versuche" Anlaeufen keine freie Adresse
            gefunden wurde.
    """
    for _ in range(versuche):
        kandidat = zufaelliger_slug()
        try:
            # begin_nested() setzt einen SAVEPOINT: Scheitert das INSERT am
            # Primaerschluessel, wird nur bis dorthin zurueckgerollt und die
            # Sitzung bleibt benutzbar. Ohne das waere die ganze Transaktion
            # hin - samt allem, was der Aufrufer vorher schon getan hat.
            async with session.begin_nested():
                session.add(Adresse(slug=kandidat, art=art))
                await session.flush()
        except IntegrityError:
            continue
        return kandidat
    raise SlugKollision(
        "Es konnte keine freie Drei-Wort-Adresse gefunden werden. "
        "Bitte versuche es noch einmal oder melde dich beim Betreiber der Seite."
    )
