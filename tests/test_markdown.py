from app.markdown import rendern


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
