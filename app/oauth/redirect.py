"""Welche Rueckadressen erlaubt sind - und warum genau diese drei.

Die Spec nennt in Abschnitt 5:
  - https://claude.ai/api/mcp/auth_callback  (Cowork und claude.ai)
  - http://localhost/callback  mit ignoriertem Port  (Claude Code)
  - http://127.0.0.1/callback  mit ignoriertem Port  (Claude Code)

Dazu kommen nur die Adressen, die der Betreiber ausdruecklich in
EXTRA_REDIRECT_URIS freigibt (etwa fuer n8n). Ohne diese Variable bleibt es
bei den dreien.

Der ignorierte Port ist keine Nachlaessigkeit: Claude Code oeffnet beim
Verbinden einen lokalen Server auf einem freien Port und kann deshalb nicht
vorher registrieren, welcher es sein wird. RFC 8252 Abschnitt 7.3 sieht
genau diese Ausnahme fuer Loopback-Adressen vor. Sie ist harmlos, weil eine
Loopback-Adresse nur auf dem Rechner der Nutzerin selbst erreichbar ist.

Fuer alles andere gilt exakter Zeichenvergleich. Insbesondere gibt es keine
Praefix-Pruefung wie startswith("https://claude.ai"): Damit waere
https://claude.ai.boese.example erlaubt.
"""

from collections.abc import Collection
from urllib.parse import urlsplit

CLAUDE_RUECKSPRUNG = "https://claude.ai/api/mcp/auth_callback"

# Nur diese beiden Hostnamen, nur ueber http, nur mit diesem Pfad. "[::1]"
# steht nicht in der Spec und wird deshalb nicht ergaenzt - was hier steht,
# steht auch in der Werkzeug- und Betriebsdokumentation.
LOOPBACK_HOSTS = ("localhost", "127.0.0.1")
LOOPBACK_PFAD = "/callback"


def _loopback_kennung(uri: str) -> tuple[str, str] | None:
    """(Host, Pfad) einer erlaubten Loopback-Adresse, sonst None.

    Der Port faellt dabei absichtlich weg - er ist die eine Angabe, die
    ignoriert wird.
    """
    teile = urlsplit(uri)
    if teile.scheme != "http":
        return None
    if teile.hostname not in LOOPBACK_HOSTS:
        return None
    if teile.path != LOOPBACK_PFAD:
        return None
    if teile.query or teile.fragment or teile.username or teile.password:
        return None
    return teile.hostname, teile.path


def registrierbar(uri: str, zusaetzliche: Collection[str] = ()) -> bool:
    """Ob diese Adresse ueberhaupt registriert werden darf.

    zusaetzliche sind die Adressen aus EXTRA_REDIRECT_URIS (app/config.py),
    etwa die Callback-URL einer n8n-Instanz. Auch fuer sie gilt exakter
    Zeichenvergleich - aus demselben Grund wie bei claude.ai.
    """
    if uri == CLAUDE_RUECKSPRUNG or uri in zusaetzliche:
        return True
    return _loopback_kennung(uri) is not None


def passt(angefragt: str, registrierte: list[str]) -> bool:
    """Ob die angefragte Adresse zu einer der registrierten passt.

    Exakter Vergleich - ausser bei Loopback, wo der Port ausgenommen ist.
    """
    if angefragt in registrierte:
        return True
    kennung = _loopback_kennung(angefragt)
    if kennung is None:
        return False
    return any(_loopback_kennung(eine) == kennung for eine in registrierte)
