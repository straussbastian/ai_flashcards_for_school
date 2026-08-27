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
