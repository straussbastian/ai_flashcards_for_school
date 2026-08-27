"""Die Eingabemodelle der Werkzeuge.

Aus ihnen erzeugt das MCP-SDK das JSON-Schema, das der Agent zu sehen
bekommt. Die Beschreibungen sind deshalb kein Beiwerk: Sie sind die einzige
Anleitung, die der Agent hat.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class KarteEingabe(BaseModel):
    """Eine Karte, wie der Agent sie uebergibt."""

    art: Annotated[
        Literal["flashcard", "frage"],
        Field(description="'flashcard' zum Lernen, 'frage' für Multiple Choice."),
    ]
    vorderseite: Annotated[
        str,
        Field(
            description=(
                "Bei einer Flashcard der Begriff, bei einer Frage die Frage "
                "selbst. Einfaches Markdown ist erlaubt."
            )
        ),
    ]
    rueckseite: Annotated[
        str | None,
        Field(
            default=None,
            description="Nur bei art='flashcard': die Lösung. Einfaches Markdown.",
        ),
    ] = None
    antworten: Annotated[
        list[str] | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': zwei bis vier Antwortmöglichkeiten als "
                "Klartext, ohne Buchstaben davor. Benutze KEINE Möglichkeiten "
                "wie 'keine der genannten' oder 'A und B sind richtig' - die "
                "Reihenfolge wird bei jedem Durchlauf neu gemischt, solche "
                "Antworten ergeben danach keinen Sinn mehr."
            ),
        ),
    ] = None
    richtige_antwort: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': der TEXT der richtigen Antwort, genau so, "
                "wie er in 'antworten' steht - kein Buchstabe, keine Zahl."
            ),
        ),
    ] = None
    erklaerung: Annotated[
        str | None,
        Field(
            default=None,
            description=(
                "Nur bei art='frage': optionale Erklärung, die nach dem "
                "Antworten auf der Rückseite erscheint."
            ),
        ),
    ] = None


class KarteAenderung(BaseModel):
    """Die aenderbaren Felder einer bestehenden Karte.

    Alle Felder sind optional. Was nicht angegeben ist, bleibt, wie es war -
    'art' laesst sich nicht aendern, weil eine Flashcard und eine Frage
    unterschiedliche Pflichtfelder haben; dafuer loescht man die Karte und
    legt eine neue an.
    """

    vorderseite: str | None = None
    rueckseite: str | None = None
    antworten: list[str] | None = None
    richtige_antwort: str | None = None
    erklaerung: str | None = None
