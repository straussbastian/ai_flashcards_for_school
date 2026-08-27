"""Die eine Ausnahme, die alle Werkzeuge werfen.

Sie traegt ausschliesslich deutschen Klartext, weil der Agent ihn der
Lehrerin vorliest. Die Umwandlung in die MCP-Antwort geschieht an genau
einer Stelle: in app/mcp/werkzeuge.py.
"""


class MCPFehler(Exception):
    """Ein Fehler, dessen Text fuer die Lehrerin bestimmt ist.

    Regel fuer jede Meldung: Sie nennt, WAS falsch ist und WAS ZU TUN ist.
    "Ungueltige Eingabe" ist keine Meldung, sondern eine Ausrede. Die Spec
    gibt in Abschnitt 5 drei Muster vor:

        "Die Karte auf Position 3 hat keine richtige Antwort. Bitte gib den
         Text einer der Antwortmoeglichkeiten an."
        "Ein Bundle mit dem Slug `rote-katze-springt` gibt es nicht. Mit
         `bundle_liste` siehst du alle vorhandenen."
        "Eine Frage braucht zwei bis vier Antwortmoeglichkeiten, diese hat
         sechs."
    """


def bei_karte(nummer: int, satz: str) -> str:
    """Stellt jeder Kartenmeldung dieselbe Ortsangabe voran.

    Ohne sie muesste die Lehrerin raten, welche der zwanzig Karten gemeint
    ist. Die Nummer ist die Position in der uebergebenen Liste, beginnend
    bei 1 - nicht die Spalte "position" in der Datenbank, die bei 0 beginnt
    und Luecken haben darf.
    """
    return f"Die Karte auf Position {nummer} {satz}"
