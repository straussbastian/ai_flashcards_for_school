import nh3
from markdown_it import MarkdownIt

_renderer = MarkdownIt("commonmark").enable("strikethrough")

# MUSS mit MAX_MARKDOWN_LAENGE in app/models.py und mit der Zahl in den
# Constraints ck_*_max_laenge in migrations/versions/0001_grundmodell.py
# uebereinstimmen. Bewusst kein gemeinsamer Import: Eine Migration
# beschreibt den Zustand der Datenbank von damals und darf nicht davon
# abhaengen, was gerade im Anwendungscode steht.
#
# Warum das zusammenpassen muss: rendern() wird erst beim Ausliefern der
# Lernseite aufgerufen. Laege in der Datenbank ein laengerer Text, waere die
# ganze Seite fuer alle Lernenden dieses Bundles kaputt, nicht nur die eine
# Karte. Die Datenbank laesst deshalb gar nicht erst hinein, was hier nicht
# ausgeliefert werden kann.
#
# Laufen die Zahlen auseinander, wird
# tests/test_models.py::test_markdown_grenze_und_datenbankgrenze_passen_zusammen
# rot.
MAX_LAENGE = 5000

ERLAUBTE_TAGS = {
    "p",
    "br",
    "strong",
    "em",
    "s",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
    "h3",
    "h4",
}


class MarkdownZuLang(Exception):
    """Ausnahme, wenn der Markdown-Text die maximale Länge überschreitet."""

    pass


def rendern(text: str | None) -> str:
    """Markdown zu HTML, anschliessend auf erlaubte Tags reduziert.

    Wird beim Ausliefern der Lernseite aufgerufen. Der Browser bekommt
    fertiges HTML und braucht keinen Markdown-Parser.

    Raises:
        MarkdownZuLang: Wenn der Text MAX_LAENGE überschreitet.
    """
    if not text or not text.strip():
        return ""

    if len(text) > MAX_LAENGE:
        raise MarkdownZuLang(
            f"Der Text ist mit {len(text)} Zeichen zu lang. "
            f"Erlaubt sind {MAX_LAENGE} Zeichen pro Karte."
        )

    roh = _renderer.render(text)
    return nh3.clean(roh, tags=ERLAUBTE_TAGS, attributes={}).strip()
