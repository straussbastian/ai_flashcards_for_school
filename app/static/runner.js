/* ====================================================================
   Der Runner der Lernseite.

   Diese Datei ist der <script>-Block aus dem abgenommenen Prototyp
   docs/design/prototyp.html, an die echten Daten gehaengt. Ablauf,
   Texte, Tastenkuerzel und Zeiten stammen woertlich von dort; der
   Prototyp ist laut Spec (Abschnitt 6, Regel 0) die verbindliche
   Referenz. Wo sich diese Datei anders verhaelt als er, ist diese
   Datei falsch.

   Die Abweichungen gegenueber dem Prototyp sind einzeln kommentiert
   und jeweils mit "ABWEICHUNG" markiert. Es sind fuenf:
     1. Das Bundle kommt aus #bundle-daten statt aus einer Konstanten.
     2. Vier Felder werden als HTML eingesetzt statt als Klartext.
     3. Die Zusammensetzung zaehlt der Server (BUNDLE.anzahl).
     4. reihenfolge = "fest" laesst die Kartenreihenfolge stehen.
     5. Ein Bundle ohne Karten zeigt einen Hinweis statt des Knopfes.

   Nach dem Laden spricht der Runner mit niemandem mehr: keine
   Serveranfrage, kein Cookie, kein Local- oder SessionStorage. Neu
   laden heisst neu anfangen - das ist keine Bequemlichkeit, sondern
   die technische Zusage aus der Spec.
   ==================================================================== */

(() => {
  "use strict";

  /* ABWEICHUNG 1: Im Prototyp stand hier ein fest eingebautes
     Beispiel-Bundle. Die echte Seite bekommt genau dieselbe Struktur
     vom Server, entschaerft eingebettet in #bundle-daten (siehe
     app/routen/lernseite.py, _einbetten, und app/bundle_json.py). */
  const BUNDLE = JSON.parse(document.getElementById("bundle-daten").textContent);

  /* ==================================================================
     WAS HIER HTML IST UND WAS NICHT

     Genau vier Felder tragen HTML: vorderseite, rueckseite,
     erklaerung und beschreibung. Dieses HTML kommt AUSSCHLIESSLICH aus
     app/markdown.rendern(): markdown-it rendert, nh3 saeubert auf die
     Liste erlaubter Tags (app/markdown.py, ERLAUBTE_TAGS). rendern()
     ist die einzige Verteidigungslinie zwischen dem, was eine Lehrkraft
     - oder ein Agent in ihrem Namen ueber MCP - in die Datenbank
     schreibt, und dem, was im Browser der Lernenden landet.

     Alles andere wird als Klartext gesetzt, insbesondere die
     Antworttexte, der Titel und die Klasse. Die laufen nicht durch
     rendern() und duerfen deshalb NIE als HTML eingesetzt werden. Ein
     als HTML eingesetzter Antworttext waere ein Cross-Site-Scripting
     auf einer Seite, die Schuelerinnen und Schueler ohne Anmeldung
     aufrufen.

     Die Regel in einem Satz: Wer hier an rendern() vorbei HTML
     einsetzt, baut ein Cross-Site-Scripting ein.

     Praktisch heisst das: htmlKnoten() nur fuer diese vier Felder,
     knoten() fuer alles andere. Es gibt in dieser Datei zwei
     Zuweisungen an innerHTML: die in htmlKnoten() haengt HTML sichtbar
     in die Seite, die in alsText() weiter unten liest es aus einem nie
     eingehaengten Hilfsknoten wieder als Klartext aus (fuer die
     Screenreader-Ansage). Beide bekommen ausschliesslich HTML aus
     genau diesen vier Feldern zu sehen - nie einen Antworttext, nie
     einen Titel.
     ================================================================== */

  /* ================== Hilfsmittel ================== */

  const BUCHSTABEN = ["A", "B", "C", "D"];
  const $ = (id) => document.getElementById(id);

  const mischen = (liste) => {
    const kopie = liste.slice();
    for (let i = kopie.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [kopie[i], kopie[j]] = [kopie[j], kopie[i]];
    }
    return kopie;
  };

  // Klartext. Fuer alles, was nicht durch rendern() gelaufen ist.
  const knoten = (tag, klasse, text) => {
    const el = document.createElement(tag);
    if (klasse) el.className = klasse;
    if (text !== undefined) el.textContent = text;
    return el;
  };

  /* ABWEICHUNG 2: Der Prototyp setzte auch die vier Markdown-Felder als
     Klartext, weil er kein Markdown kannte. Hier ist es gesaeubertes
     HTML aus app/markdown.rendern() - siehe den Block oben.

     Die eine der zwei innerHTML-Zuweisungen der Datei, die HTML in die
     sichtbare Seite haengt (die andere steht in alsText() weiter
     unten und haengt nichts ein). Aufrufer sind ausschliesslich:
     BUNDLE.beschreibung, karte.vorderseite, karte.rueckseite und
     karte.erklaerung.

     Die zusaetzliche Klasse "markdown" ist kein Schmuck: rendern()
     liefert Block-Markup ("Sechs Monate" wird zu <p>Sechs Monate</p>),
     und app/static/lernseite.css nimmt darueber dem ersten und letzten
     Kind den Absatzabstand. Sie ist ausserdem der Suchbegriff, mit dem
     sich alle HTML-Stellen der Seite auf einmal finden lassen. */
  const htmlKnoten = (tag, klasse, html) => {
    const el = document.createElement(tag);
    el.className = klasse ? `${klasse} markdown` : "markdown";
    el.innerHTML = html;
    return el;
  };

  // Fuer die Ansage an den Screenreader: aus dem gerenderten HTML den
  // reinen Text gewinnen. Ohne das laese eine Sprachausgabe die Tags
  // mit vor. Auch hier gilt: Es geht nur HTML aus rendern() hinein, und
  // der Knoten wird nie in die Seite gehaengt.
  const alsText = (html) => {
    const hilfe = document.createElement("div");
    hilfe.innerHTML = html;
    return hilfe.textContent.trim();
  };

  // Jeder Knopf, der auch per Tastatur erreichbar ist, traegt sein Kuerzel
  // sichtbar. Was man druecken kann, soll man auch sehen koennen.
  const knopf = (klasse, taste, text, beiKlick) => {
    const b = knoten("button", klasse);
    b.type = "button";
    if (taste) b.append(knoten("span", "taste", taste));
    b.append(document.createTextNode(text));
    b.addEventListener("click", beiKlick);
    return b;
  };

  /* ABWEICHUNG 5: Der Hinweis fuer ein Bundle ohne Karten steht im
     Template (app/templates/lernseite.html) und wird von dort
     uebernommen, damit derselbe Satz nicht an zwei Stellen gepflegt
     werden muss. Ausgelesen wird er, bevor der Runner den Inhalt der
     Karte zum ersten Mal ersetzt. */
  const LEER_HINWEIS =
    $("karte-innen").querySelector(".hinweis")?.textContent.trim() || "";

  /* ================== Zustand ================== */

  let lauf = null;      // { karten: [...], index: 0 }
  let ansicht = "start"; // start | karte | ergebnis

  /* ABWEICHUNG 4: Der Prototyp mischte die Karten immer. Das Bundle
     traegt jetzt reihenfolge: Bei "fest" bleibt die Kartenreihenfolge,
     wie sie aus der Datenbank kommt (nach position sortiert, siehe
     app/bundle_json.py). Die Antworten werden laut Spec trotzdem bei
     jedem Durchlauf neu gemischt. */
  const kartenFolge = (quelle) =>
    BUNDLE.reihenfolge === "fest" ? quelle.slice() : mischen(quelle);

  const durchlaufBauen = (quelle) => {
    const karten = kartenFolge(quelle).map((k) => {
      if (k.art === "flashcard") {
        return { ...k, gewusst: null };
      }
      // Antworten mischen, die richtige Position mitwandern lassen.
      const paare = mischen(k.antworten.map((text, i) => ({ text, richtig: i === k.richtige_index })));
      return {
        ...k,
        gemischte: paare,
        richtige_position: paare.findIndex((p) => p.richtig),
        gewaehlt: null
      };
    });
    return { karten, index: 0 };
  };

  const aktuelle = () => lauf.karten[lauf.index];
  const beantwortet = (k) => (k.art === "flashcard" ? k.gewusst !== null : k.gewaehlt !== null);

  const punkte = () => {
    let erreicht = 0, moeglich = 0;
    for (const k of lauf.karten) {
      if (k.art === "frage") {
        moeglich++;
        if (k.gewaehlt === k.richtige_position) erreicht++;
      } else if (BUNDLE.selbsteinschaetzung) {
        moeglich++;
        if (k.gewusst) erreicht++;
      }
    }
    return { erreicht, moeglich };
  };

  const danebenGegangen = () =>
    lauf.karten.filter((k) =>
      k.art === "frage" ? k.gewaehlt !== null && k.gewaehlt !== k.richtige_position
                        : k.gewusst === false);

  const ansagen = (text) => { $("ansage").textContent = text; };

  /* ================== Zeichnen ================== */

  // Die Tastenleiste zeigt immer nur, was in genau diesem Moment geht.
  // Eine Leiste, die Tasten nennt, die gerade nichts tun, erzieht dazu,
  // sie nicht mehr zu lesen.
  const tastenhinweis = () => {
    // ABWEICHUNG 5: Ohne Karten gibt es nichts zu starten, also nennt
    // die Leiste auch keine Taste.
    if (ansicht === "start") return BUNDLE.anzahl.gesamt ? "Eingabetaste startet" : "";
    if (ansicht === "ergebnis") return "A nochmal · B nur die Fehler · Esc zur Startseite";
    const k = aktuelle();
    if (k.art === "frage") {
      return k.gewaehlt === null
        ? "A B C D wählen · ← → blättern · Esc beenden"
        : "← → blättern · Esc beenden";
    }
    if (!k.aufgedeckt) return "Leertaste umdrehen · ← → blättern · Esc beenden";
    if (BUNDLE.selbsteinschaetzung && k.gewusst === null)
      return "A wusste ich · B wusste ich nicht · ← → blättern · Esc beenden";
    return "← → blättern · Esc beenden";
  };

  const kopfUndFussSetzen = () => {
    const imLauf = ansicht === "karte";
    $("kopf").hidden = !imLauf;
    $("fuss").hidden = !imLauf;
    $("tastenleiste").textContent = tastenhinweis();

    const geist1 = $("geist-1"), geist2 = $("geist-2");
    const rest = imLauf ? lauf.karten.length - lauf.index - 1 : 0;
    geist1.hidden = !(imLauf && rest >= 1);
    geist2.hidden = !(imLauf && rest >= 2);

    if (imLauf) {
      $("fortschritt-text").textContent = `Karte ${lauf.index + 1} von ${lauf.karten.length}`;
      $("fortschritt-balken").style.width = `${((lauf.index + 1) / lauf.karten.length) * 100}%`;
      $("zurueck").disabled = lauf.index === 0;
      $("weiter").textContent = lauf.index === lauf.karten.length - 1 ? "Ergebnis →" : "weiter →";
    }
  };

  const seiteBauen = (klasse) => knoten("div", `seite ${klasse || ""}`.trim());

  const zeichneStart = () => {
    ansicht = "start";
    const s = seiteBauen();

    // klasse und beschreibung sind optional und dann ein leerer String
    // (siehe app/bundle_json.py). Ein leerer Chip und ein leerer Absatz
    // haetten auf der Startseite nichts zu suchen.
    if (BUNDLE.klasse) s.append(knoten("span", "klasse", BUNDLE.klasse));
    s.append(knoten("h1", "titel", BUNDLE.titel));
    if (BUNDLE.beschreibung) {
      // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
      // Block oben.
      s.append(htmlKnoten("div", "beschreibung", BUNDLE.beschreibung));
    }

    if (BUNDLE.anzahl.gesamt === 0) {
      /* ABWEICHUNG 5: Ohne Karten kein Start-Knopf, sondern der Hinweis
         aus dem Template. Die Zusammensetzung entfaellt mit: Dreimal
         die Null sagt weniger als der Satz darunter. */
      const hinweis = knoten("p", "hinweis", LEER_HINWEIS);
      s.append(hinweis);
      karteErsetzen([s], false);
      kopfUndFussSetzen();
      return;
    }

    /* ABWEICHUNG 3: Der Prototyp zaehlte die Karten im Browser. Jetzt
       zaehlt der Server (app/bundle_json.py, Feld anzahl). */
    const zusammen = knoten("div", "zusammensetzung");
    [[BUNDLE.anzahl.gesamt, "Karten"], [BUNDLE.anzahl.flashcards, "zum Lernen"],
     [BUNDLE.anzahl.fragen, "Fragen"]]
      .forEach(([zahl, was]) => {
        const sp = knoten("span");
        sp.append(knoten("b", null, String(zahl)), document.createTextNode(was));
        zusammen.append(sp);
      });
    s.append(zusammen);

    const start = knopf("knopf", null, "Los geht's →", () => starten(BUNDLE.karten));
    start.style.marginTop = "auto";
    start.style.alignSelf = "flex-start";
    s.append(start);

    karteErsetzen([s], false);
    kopfUndFussSetzen();
    start.focus();
  };

  const zeichneKarte = (mitAnimation) => {
    ansicht = "karte";
    const k = aktuelle();
    const seiten = [];

    const vorn = seiteBauen();
    vorn.append(
      knoten("span", "augenbraue", k.art === "frage" ? "Frage" : "Lernkarte"),
      // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
      // Block oben.
      htmlKnoten("div", "frage", k.vorderseite)
    );

    if (k.art === "frage") {
      const liste = knoten("div", "antworten");
      k.gemischte.forEach((antwort, i) => {
        const b = knoten("button", "antwort");
        b.type = "button";
        // KLARTEXT, und das bleibt so: Antworttexte laufen nicht durch
        // rendern() und werden nie als HTML eingesetzt.
        b.append(knoten("span", "taste", BUCHSTABEN[i]), document.createTextNode(antwort.text));
        b.addEventListener("click", () => antworten(i));
        liste.append(b);
      });
      vorn.append(liste);
    } else {
      const drehen = knoten("button", "knopf leise", "Umdrehen");
      drehen.type = "button";
      drehen.style.marginTop = "auto";
      drehen.style.alignSelf = "flex-start";
      drehen.addEventListener("click", umdrehen);
      vorn.append(drehen, knoten("span", "hinweis", "oder Leertaste"));
    }
    seiten.push(vorn);

    const hinten = seiteBauen("rueckseite");
    if (k.art === "frage") {
      const richtig = k.gewaehlt === k.richtige_position;
      hinten.append(knoten("p", `urteil ${richtig ? "ja" : "nein"}`, richtig ? "Richtig!" : "Leider falsch"));
      // KLARTEXT: Die Loesung besteht aus Antworttexten. Sie laufen
      // nicht durch rendern() und werden nie als HTML eingesetzt.
      const loesung = knoten("p", "loesung");
      if (!richtig && k.gewaehlt !== null) {
        loesung.append(knoten("span", "deine", `Deine Antwort: ${k.gemischte[k.gewaehlt].text}`), knoten("br"));
      }
      loesung.append(document.createTextNode("Richtig ist: "), knoten("strong", null, k.gemischte[k.richtige_position].text));
      hinten.append(loesung);
      // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
      // Block oben. (Eine Flashcard traegt gar kein Erklaerungsfeld,
      // deshalb steht die Pruefung hier und nicht weiter oben.)
      if (k.erklaerung) hinten.append(htmlKnoten("div", "erklaerung", k.erklaerung));
    } else {
      hinten.append(
        knoten("span", "augenbraue", "Antwort"),
        // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
        // Block oben.
        htmlKnoten("div", "loesung", k.rueckseite)
      );
      if (BUNDLE.selbsteinschaetzung && k.gewusst === null) {
        const wahl = knoten("div", "selbsteinschaetzung");
        wahl.append(
          knopf("knopf", "A", "Wusste ich", () => einschaetzen(true)),
          knopf("knopf leise", "B", "Wusste ich nicht", () => einschaetzen(false))
        );
        hinten.append(wahl);
      } else if (k.gewusst !== null) {
        hinten.append(knoten("p", "erklaerung", k.gewusst ? "Als gewusst gewertet." : "Als nicht gewusst gewertet."));
      }
    }
    seiten.push(hinten);

    karteErsetzen(seiten, mitAnimation);
    $("karte").classList.toggle("gedreht", beantwortet(k) || k.aufgedeckt === true);
    kopfUndFussSetzen();
  };

  const zeichneErgebnis = () => {
    ansicht = "ergebnis";
    const { erreicht, moeglich } = punkte();
    const fragen = lauf.karten.filter((k) => k.art === "frage");
    const fragenRichtig = fragen.filter((k) => k.gewaehlt === k.richtige_position).length;
    const karten = lauf.karten.filter((k) => k.art === "flashcard");
    const kartenGewusst = karten.filter((k) => k.gewusst === true).length;
    const daneben = danebenGegangen();

    const s = seiteBauen("rueckseite");
    s.style.transform = "none";
    s.style.position = "relative";
    s.style.background = "var(--zettel-vorn)";

    const anteil = moeglich ? erreicht / moeglich : 0;
    const fazit = anteil === 1 ? "Alles richtig. Stark."
                : anteil >= .8 ? "Stark! Nur wenig daneben."
                : anteil >= .5 ? "Solide – schau dir die Fehler an."
                : "Da geht noch was. Nimm die Fehler nochmal.";

    s.append(
      knoten("span", "klasse", "Geschafft"),
      (() => { const p = knoten("p", "punktzahl", String(erreicht));
               p.append(knoten("small", null, ` / ${moeglich}`)); return p; })(),
      knoten("p", "fazit", fazit)
    );

    if (fragen.length && karten.length) {
      const auf = knoten("div", "aufschluesselung");
      const k1 = knoten("div", "kachel gut");
      k1.append(knoten("b", null, `${fragenRichtig}/${fragen.length}`), document.createTextNode("Fragen richtig"));
      const k2 = knoten("div", `kachel ${kartenGewusst === karten.length ? "gut" : "schlecht"}`);
      k2.append(knoten("b", null, `${kartenGewusst}/${karten.length}`), document.createTextNode("Karten gewusst"));
      auf.append(k1, k2);
      s.append(auf);
    }

    if (daneben.length) {
      const liste = knoten("div", "fehlerliste");
      daneben.forEach((k) => {
        const eintrag = knoten("div", "fehler");
        // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
        // Block oben. Der Antworttext daneben bleibt Klartext.
        eintrag.append(htmlKnoten("span", null, k.vorderseite), knoten("br"));
        if (k.art === "frage") {
          eintrag.append(knoten("i", null, `Du: ${k.gemischte[k.gewaehlt].text} · `),
                         knoten("b", null, k.gemischte[k.richtige_position].text));
        } else {
          // HTML aus app/markdown.rendern(), dort gesaeubert.
          eintrag.append(htmlKnoten("b", null, k.rueckseite));
        }
        liste.append(eintrag);
      });
      s.append(liste);
    }

    const knoepfe = knoten("div", "ergebnis-knoepfe");
    const nochmal = knopf("knopf", "A", "Nochmal starten", () => starten(BUNDLE.karten));
    knoepfe.append(nochmal);

    if (daneben.length) {
      knoepfe.append(knopf("knopf leise", "B", `Nur die Fehler (${daneben.length})`,
        () => starten(daneben.map(ursprung))));
    }
    s.append(knoepfe);

    karteErsetzen([s], false);
    kopfUndFussSetzen();
    ansagen(`Ergebnis: ${erreicht} von ${moeglich}.`);
    nochmal.focus();
  };

  // Aus einer Laufkarte die urspruengliche Kartendefinition zurueckgewinnen,
  // damit der Wiederholungsdurchlauf frisch gemischt startet.
  const ursprung = (k) => BUNDLE.karten.find((o) => o.vorderseite === k.vorderseite);

  const karteErsetzen = (seiten, mitAnimation) => {
    const karte = $("karte");
    if (!mitAnimation) {
      karte.classList.add("ohne-animation");
      karte.classList.remove("gedreht");
    }
    const innen = $("karte-innen");
    innen.replaceChildren(...seiten);
    if (!mitAnimation) {
      // Ein Frame ohne Uebergang, damit beim Blaettern nichts flackert.
      requestAnimationFrame(() => karte.classList.remove("ohne-animation"));
    }
  };

  /* ================== Handlungen ================== */

  const starten = (quelle) => {
    lauf = durchlaufBauen(quelle);
    zeichneKarte(false);
    ansagen(`Los geht's. Karte 1 von ${lauf.karten.length}.`);
    $("karte").querySelector("button")?.focus();
  };

  const umdrehen = () => {
    const k = aktuelle();
    if (k.art !== "flashcard") return;
    k.aufgedeckt = true;
    $("karte").classList.add("gedreht");
    kopfUndFussSetzen();   // Die Tastenleiste zeigt jetzt A und B.
    // alsText(): Die Rueckseite ist HTML; die Sprachausgabe soll den
    // Text hoeren, nicht das Markup.
    ansagen(`Antwort: ${alsText(k.rueckseite)}`);
    setTimeout(() => $("karte").querySelector(".rueckseite button")?.focus(), 300);
  };

  const einschaetzen = (gewusst) => {
    aktuelle().gewusst = gewusst;
    ansagen(gewusst ? "Als gewusst gewertet." : "Als nicht gewusst gewertet.");
    setTimeout(vor, 350);
  };

  const antworten = (position) => {
    const k = aktuelle();
    if (k.gewaehlt !== null) return;
    k.gewaehlt = position;
    const richtig = position === k.richtige_position;
    zeichneKarte(true);
    $("karte").classList.add("gedreht");
    ansagen(richtig
      ? "Richtig."
      : `Falsch. Richtig ist: ${k.gemischte[k.richtige_position].text}`);
    // Der angeklickte Knopf ist mit dem Umdrehen verschwunden. Ohne diesen
    // Schritt haette niemand mehr den Tastaturfokus - Tab faengt dann wieder
    // ganz vorn an.
    $("karte").focus({ preventScroll: true });
  };

  const vor = () => {
    if (lauf.index === lauf.karten.length - 1) { zeichneErgebnis(); return; }
    lauf.index++;
    zeichneKarte(false);
    ansagen(`Karte ${lauf.index + 1} von ${lauf.karten.length}.`);
  };

  const zurueck = () => {
    if (lauf.index === 0) return;
    lauf.index--;
    zeichneKarte(false);
    ansagen(`Karte ${lauf.index + 1} von ${lauf.karten.length}.`);
  };

  /* ================== Bedienung ================== */

  $("weiter").addEventListener("click", vor);
  $("zurueck").addEventListener("click", zurueck);
  $("beenden-knopf").addEventListener("click", zeichneStart);

  // Alles, was klickbar ist, ist auch mit der Tastatur erreichbar. Wo zwei
  // Moeglichkeiten zur Wahl stehen, sind es immer A und B - dieselbe Geste
  // wie bei den Antworten, damit man sich nur eine Regel merken muss.
  const taste = (el) => el?.click();

  document.addEventListener("keydown", (e) => {
    const gross = e.key.toUpperCase();

    if (ansicht === "start") {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        // Ohne Karten gibt es keinen Knopf; dann passiert hier nichts.
        taste($("karte").querySelector(".knopf"));
      }
      return;
    }

    if (ansicht === "ergebnis") {
      if (e.key === "Escape") { e.preventDefault(); zeichneStart(); return; }
      const knoepfe = $("karte").querySelectorAll(".ergebnis-knoepfe .knopf");
      if (gross === "A" || e.key === "Enter") { e.preventDefault(); taste(knoepfe[0]); }
      if (gross === "B") { e.preventDefault(); taste(knoepfe[1]); }
      return;
    }

    const k = aktuelle();

    if (e.key === "Escape") { e.preventDefault(); zeichneStart(); return; }
    if (e.key === "ArrowRight") { e.preventDefault(); vor(); return; }
    if (e.key === "ArrowLeft") { e.preventDefault(); zurueck(); return; }

    if (k.art === "flashcard") {
      // Vorderseite: umdrehen. Rueckseite: einschaetzen.
      if (!k.aufgedeckt) {
        if (e.key === " " || e.key === "Enter") { e.preventDefault(); umdrehen(); }
        return;
      }
      if (BUNDLE.selbsteinschaetzung && k.gewusst === null) {
        if (gross === "A") { e.preventDefault(); einschaetzen(true); }
        if (gross === "B") { e.preventDefault(); einschaetzen(false); }
      } else if (e.key === " " || e.key === "Enter") {
        e.preventDefault(); vor();
      }
      return;
    }

    if (k.gewaehlt !== null) {
      // Frage ist beantwortet - nur noch blaettern.
      if (e.key === " " || e.key === "Enter") { e.preventDefault(); vor(); }
      return;
    }
    const treffer = BUCHSTABEN.indexOf(gross);
    if (treffer >= 0 && treffer < k.gemischte.length) { e.preventDefault(); antworten(treffer); return; }
    const zahl = Number(e.key);
    if (zahl >= 1 && zahl <= k.gemischte.length) { e.preventDefault(); antworten(zahl - 1); }
  });

  zeichneStart();
})();
