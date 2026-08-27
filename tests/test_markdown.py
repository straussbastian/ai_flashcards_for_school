import pytest
from app.markdown import rendern, MarkdownZuLang


def test_fettschrift_wird_gerendert():
    assert "<strong>wichtig</strong>" in rendern("Das ist **wichtig**.")


def test_aufzaehlung_wird_gerendert():
    ergebnis = rendern("- eins\n- zwei")
    assert "<ul>" in ergebnis
    assert ergebnis.count("<li>") == 2


def test_skript_wird_entfernt():
    ergebnis = rendern("Hallo <script>alert('boese')</script>")
    assert "script" not in ergebnis.lower()
    assert "Hallo" in ergebnis


def test_bild_wird_entfernt():
    ergebnis = rendern("![alt](https://example.com/bild.png)")
    assert "<img" not in ergebnis


def test_link_wird_entfernt_text_bleibt():
    ergebnis = rendern("[Klick mich](javascript:alert(1))")
    assert "<a" not in ergebnis
    assert "Klick mich" in ergebnis


def test_leere_eingabe_ergibt_leeren_string():
    assert rendern(None) == ""
    assert rendern("") == ""
    assert rendern("   ") == ""


def test_erlaubtes_tag_mit_gefaehrlichem_attribut():
    """Ein erlaubtes Tag mit gefährlichem Attribut: das Tag bleibt, Attribut muss weg."""
    ergebnis = rendern("<strong onclick=\"alert(1)\">Text</strong>")
    assert "<strong>" in ergebnis
    assert "onclick" not in ergebnis.lower()
    assert "Text" in ergebnis


def test_iframe_wird_entfernt():
    """Eingebettetes iframe muss vollständig verschwinden."""
    ergebnis = rendern("Hallo <iframe src=\"https://evil.com\"></iframe> Welt")
    assert "<iframe" not in ergebnis.lower()
    assert "Hallo" in ergebnis
    assert "Welt" in ergebnis


def test_style_block_wird_entfernt():
    """Ein <style>-Block muss vollständig verschwinden."""
    ergebnis = rendern("<style>body { display: none; }</style>Text")
    assert "<style" not in ergebnis.lower()
    assert "Text" in ergebnis


def test_href_attribut_wird_entfernt():
    """Selbst wenn ein Link irgendwie durchkommt, hat es kein href."""
    ergebnis = rendern("<a href=\"javascript:alert(1)\">Link</a>")
    assert "href" not in ergebnis.lower()
    assert "javascript" not in ergebnis.lower()


def test_text_knapp_unter_grenze_wird_gerendert():
    """Ein Text knapp unter MAX_LAENGE wird normal gerendert."""
    text = "a" * 4999
    ergebnis = rendern(text)
    assert ergebnis  # Sollte nicht leer sein
    assert "a" in ergebnis


def test_text_ueber_grenze_loest_ausnahme_aus():
    """Ein Text über MAX_LAENGE löst MarkdownZuLang mit beiden Zahlen aus."""
    text = "a" * 5001
    with pytest.raises(MarkdownZuLang) as info:
        rendern(text)

    fehler_text = str(info.value)
    assert "5001" in fehler_text  # Tatsächliche Länge
    assert "5000" in fehler_text  # Erlaubte Länge
    # Prüfe, dass die Nachricht verständlich ist
    assert "Zeichen" in fehler_text or "lang" in fehler_text.lower()


def test_tief_verschachteltes_markdown_an_grenze_ist_schnell():
    """Tief verschachtelte Listen sollten schnell fehlschlagen, nicht lange rechnen."""
    # Erzeuge tief verschachtelte Listen nahe der Grenze
    # Jede Ebene: "- " (2 Zeichen) + Text (~20) + Newline (1) ≈ 24 Zeichen pro Ebene
    # Bei 5000 Zeichen: ~200 Ebenen möglich
    # Wir bauen etwas, das ohne die Grenze superlinear wäre
    verschachtelte_liste = ""
    for i in range(250):
        verschachtelte_liste += ("  " * i) + f"- Ebene {i}\n"

    # Sollte schnell fehlschlagen, nicht ewig rechnen
    with pytest.raises(MarkdownZuLang):
        rendern(verschachtelte_liste)
