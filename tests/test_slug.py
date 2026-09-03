import re

import pytest

from app import slug as slug_modul
from app.models import Adresse
from app.slug import SlugKollision, freien_slug_finden, zufaelliger_slug

FORM = re.compile(r"^[a-z]+-[a-z]+-[a-z]+$")


def test_slug_hat_drei_kleingeschriebene_woerter():
    assert FORM.match(zufaelliger_slug())


def test_alle_woerter_sind_url_tauglich():
    for liste in (slug_modul.ADJEKTIVE, slug_modul.NOMEN, slug_modul.VERBEN):
        assert len(liste) >= 200
        for wort in liste:
            assert re.match(r"^[a-z]+$", wort), f"{wort} ist nicht url-tauglich"


def test_keine_wortliste_enthaelt_dopplungen():
    """Ein doppeltes Wort verkleinert den Adressraum, ohne dass es auffaellt.

    Die Listen werden von Hand gepflegt, und ein Wort zweimal einzutragen
    ist der wahrscheinlichste Fehler dabei. Ohne diesen Test bliebe er
    stumm: Die Adressen sehen weiterhin richtig aus, es gibt nur weniger
    davon und Kollisionen werden haeufiger.
    """
    for name in ("ADJEKTIVE", "NOMEN", "VERBEN"):
        liste = getattr(slug_modul, name)
        doppelt = sorted({w for w in liste if liste.count(w) > 1})
        assert not doppelt, f"{name} enthaelt doppelte Woerter: {doppelt}"


def test_der_adressraum_ist_gross_genug():
    """200 x 200 x 200 = 8 Millionen statt der urspruenglichen 27.000.

    freien_slug_finden() wuerfelt zehnmal und gibt dann auf. Wie oft das
    passiert, haengt allein daran, wie voll der Adressraum ist - deshalb
    steht diese Zahl hier und nicht nur in einem Kommentar.
    """
    moeglich = len(slug_modul.ADJEKTIVE) * len(slug_modul.NOMEN) * len(slug_modul.VERBEN)
    assert moeglich >= 8_000_000, f"Nur {moeglich:,} moegliche Adressen."


async def test_belegter_slug_wird_uebersprungen(session, monkeypatch):
    session.add(Adresse(slug="rote-katze-springt", art="paket"))
    await session.flush()

    kandidaten = iter(["rote-katze-springt", "blaue-ampel-tanzt"])
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: next(kandidaten))

    assert await freien_slug_finden(session) == "blaue-ampel-tanzt"


async def test_dauerhafte_kollision_meldet_klartext(session, monkeypatch):
    session.add(Adresse(slug="rote-katze-springt", art="paket"))
    await session.flush()
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: "rote-katze-springt")

    with pytest.raises(SlugKollision) as fehler:
        await freien_slug_finden(session, versuche=3)
    assert "Adresse" in str(fehler.value)


async def test_die_adresse_wird_gleich_eingetragen(session, monkeypatch):
    """Pruefen und Belegen sind ein Schritt.

    Frueher wurde nur gefragt ("gibt es diesen Slug schon?") und danach
    geschrieben; zwischen Frage und Antwort lag ein Wettlauf, den jeder
    Aufrufer selbst abfangen musste. Jetzt IST der Eintrag der Anspruch.
    """
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: "gelbe-tafel-summt")
    slug = await freien_slug_finden(session, art="sammlung")

    eintrag = await session.get(Adresse, slug)
    assert eintrag is not None, "Die Adresse wurde nicht eingetragen."
    assert eintrag.art == "sammlung"


async def test_eine_sammlung_bekommt_keine_paketadresse(session, monkeypatch):
    """Der eigentliche Zweck der gemeinsamen Tabelle.

    Lernpakete und Sammlungen werden beide unter /{slug} ausgeliefert. Ohne
    gemeinsamen Adressraum koennte eine Sammlung die Adresse eines
    Lernpakets bekommen, und die Route lieferte still das Falsche aus.
    """
    session.add(Adresse(slug="rote-katze-springt", art="paket"))
    await session.flush()

    kandidaten = iter(["rote-katze-springt", "blaue-ampel-tanzt"])
    monkeypatch.setattr(slug_modul, "zufaelliger_slug", lambda: next(kandidaten))

    assert await freien_slug_finden(session, art="sammlung") == "blaue-ampel-tanzt"
