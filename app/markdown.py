import nh3
from markdown_it import MarkdownIt

_renderer = MarkdownIt("commonmark").enable("strikethrough")

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


def rendern(text: str | None) -> str:
    """Markdown zu HTML, anschliessend auf erlaubte Tags reduziert.

    Wird beim Ausliefern der Lernseite aufgerufen. Der Browser bekommt
    fertiges HTML und braucht keinen Markdown-Parser.
    """
    if not text or not text.strip():
        return ""
    roh = _renderer.render(text)
    return nh3.clean(roh, tags=ERLAUBTE_TAGS, attributes={}).strip()
