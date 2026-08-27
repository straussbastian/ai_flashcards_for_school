/* ====================================================================
   Der Runner der Lernseite.

   Diese Datei ist der <script>-Block aus dem abgenommenen Prototyp
   docs/design/prototyp.html, an die echten Daten gehaengt. Ablauf,
   Texte, Tastenkuerzel und Zeiten stammen woertlich von dort; der
   Prototyp ist laut Spec (Abschnitt 6, Regel 0) die verbindliche
   Referenz. Wo sich diese Datei anders verhaelt als er, ist diese
   Datei falsch.

   Die Abweichungen gegenueber dem Prototyp sind einzeln kommentiert
   und jeweils mit "ABWEICHUNG" markiert. Es sind sechs:
     1. Das Bundle kommt aus #bundle-daten statt aus einer Konstanten.
     2. Vier Felder werden als HTML eingesetzt statt als Klartext.
     3. Die Zusammensetzung zaehlt der Server (BUNDLE.anzahl).
     4. reihenfolge = "fest" laesst die Kartenreihenfolge stehen.
     5. Ein Bundle ohne Karten zeigt einen Hinweis statt des Knopfes.
     6. alsText() liest ohne innerHTML und trennt Bloecke.
     7. Die Rueckseite traegt einen Weiter-Knopf.
     8. Tastenleiste und Tastenbedienung kommen aus einer Quelle.
     9. Beim Blaettern wandert der Fokus auf die neue Karte.

   Ab Nummer 6 sind es Fehlerbehebungen: Der Prototyp kannte nur eine
   Konfiguration (selbsteinschaetzung: true) und nur kurze Texte,
   deshalb konnte er sie nicht zeigen. An diesen Stellen ist er nicht
   mehr die Referenz - die Spec ist es.

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
     knoten() fuer alles andere. Es gibt in dieser Datei genau eine
     Zuweisung an innerHTML, die in htmlKnoten(). Sie bekommt
     ausschliesslich HTML aus genau diesen vier Feldern zu sehen - nie
     einen Antworttext, nie einen Titel. (alsText() weiter unten liest
     dasselbe HTML als Klartext wieder aus, benutzt dafuer aber
     DOMParser und kein innerHTML - siehe ABWEICHUNG 6.)
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

  /* Fuer die Ansage an den Screenreader: aus dem gerenderten HTML den
     reinen Text gewinnen. Ohne das laese eine Sprachausgabe die Tags
     mit vor. Auch hier gilt: Es geht nur HTML aus rendern() hinein, und
     nichts davon wird je in die Seite gehaengt.

     ABWEICHUNG 6: Zweierlei gegenueber dem Prototyp, der diese Funktion
     gar nicht brauchte (er kannte kein HTML).

     Erstens DOMParser statt eines Hilfsknotens mit innerHTML.
     parseFromString baut ein eigenes, nie eingehaengtes Dokument: Darin
     laedt kein Bild, laeuft kein Skript, feuert kein Ereignisattribut.
     Mit innerHTML an einem createElement-Knoten war das heute zwar
     folgenlos, aber nur durch die Konvention oben bewacht - hier ist es
     unabhaengig davon harmlos, auch fuer einen spaeteren Aufrufer, der
     die Regel nicht kennt. Nebenbei bleibt damit genau eine
     innerHTML-Zuweisung in dieser Datei, so wie der Block oben es sagt.

     Zweitens werden die Bloecke getrennt. textContent klebt sie sonst
     aneinander, sobald zwischen ihnen kein Zeilenumbruch steht: aus den
     Absaetzen "A" und "B" wuerde "AB". Der Trenner haengt so nicht mehr
     daran, wie der Renderer sein HTML einrueckt. Genommen wird jeweils
     der innerste Block, damit der Text eines <li> nicht doppelt in der
     Ansage landet. */
  const BLOCKTAGS = "p, li, pre, blockquote, h3, h4";
  const alsText = (html) => {
    const koerper = new DOMParser().parseFromString(html, "text/html").body;
    const bloecke = [...koerper.querySelectorAll(BLOCKTAGS)]
      .filter((el) => !el.querySelector(BLOCKTAGS))
      .map((el) => el.textContent.trim())
      .filter(Boolean);
    return (bloecke.length ? bloecke.join(" ") : koerper.textContent).trim();
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

  /* ABWEICHUNG 7: Was auf der Rueckseite steht, entscheiden ab hier zwei
     Funktionen - und zwar fuer die Knoepfe und fuer die Tastenleiste
     dieselben. Der Prototyp beantwortete diese Fragen an jeder Stelle
     neu.

     einschaetzungOffen(): Die Selbsteinschaetzung steht noch aus. Nur
     dann gehoeren "Wusste ich" und "Wusste ich nicht" auf die
     Rueckseite.

     weiterOffen(): Die Rueckseite, die gerade zu sehen ist, fuehrt
     weiter - bei einer beantworteten Frage und bei einer aufgedeckten
     Lernkarte ohne offene Selbsteinschaetzung. Die Spec woertlich: "Ist
     selbsteinschaetzung aktiv, erscheinen auf der Rueckseite 'Wusste
     ich' und 'Wusste ich nicht'. Sonst nur 'Weiter'." Bei abgeschalteter
     Selbsteinschaetzung bleibt gewusst fuer immer null; die alte
     Bedingung k.gewusst !== null hat dort deshalb nie gegriffen, und die
     Karte trug ueberhaupt keinen Knopf mehr. */
  const einschaetzungOffen = (k) =>
    k.art === "flashcard" && BUNDLE.selbsteinschaetzung && k.gewusst === null;

  const weiterOffen = (k) =>
    k.art === "frage" ? k.gewaehlt !== null
                      : k.aufgedeckt === true && !einschaetzungOffen(k);

  const letzteKarte = () => lauf.index === lauf.karten.length - 1;
  // Eine Beschriftung fuer beide Weiter-Knoepfe: den auf der Karte und
  // den im Navigationsbalken unten.
  const weiterText = () => (letzteKarte() ? "Ergebnis →" : "weiter →");

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

  /* Die Tastenleiste zeigt immer nur, was in genau diesem Moment geht.
     Eine Leiste, die Tasten nennt, die gerade nichts tun, erzieht dazu,
     sie nicht mehr zu lesen.

     ABWEICHUNG 8: Im Prototyp standen zwei unabhaengige Beschreibungen
     desselben Sachverhalts nebeneinander - die Leiste als feste Saetze
     je Ansicht, die Bedienung als eigene Fallunterscheidung im
     keydown-Hoerer weiter unten. Zwei Beschreibungen laufen frueher
     oder spaeter auseinander, und diese taten es: Im Ergebnis ohne
     Fehler bot die Leiste "B nur die Fehler" an, obwohl dieser Knopf
     nur bei Fehlern ueberhaupt gebaut wird - ausgerechnet im besten
     Lauf griff eine angebotene Taste ins Leere. Bei einer Frage mit nur
     zwei Antworten nannte sie C und D.

     Eine zusaetzliche if-Abfrage haette genau diesen einen Fall
     zugedeckt und den naechsten abgewartet. Deshalb gibt es jetzt nur
     noch eine Quelle: belegung() beschreibt fuer den aktuellen Zustand,
     welche Taste was tut und wie sie in der Leiste heisst. Die Leiste
     ist nichts anderes als die Beschriftung dieser Liste, und der
     keydown-Hoerer fuehrt genau diese Liste aus. Eine Taste kann damit
     nicht mehr angezeigt werden, ohne zu wirken - und nicht mehr
     wirken, ohne angezeigt zu sein. Die Wortlaute stammen weiter aus
     dem Prototyp.

     tun() bekommt die gedrueckte Taste, damit ein Eintrag mehrere
     Tasten zusammenfassen kann (A bis D, die beiden Pfeile). */
  const belegung = () => {
    const eintraege = [];

    if (ansicht === "start") {
      // ABWEICHUNG 5: Ohne Karten gibt es nichts zu starten, also nennt
      // die Leiste auch keine Taste.
      if (BUNDLE.anzahl.gesamt) {
        eintraege.push({ tasten: ["Enter", " "], zeige: "Eingabetaste startet",
                         tun: () => starten(BUNDLE.karten) });
      }
      return eintraege;
    }

    if (ansicht === "ergebnis") {
      eintraege.push({ tasten: ["A", "Enter"], zeige: "A nochmal",
                       tun: () => starten(BUNDLE.karten) });
      // Der Knopf entsteht nur, wenn etwas danebenging - die Taste jetzt
      // aus derselben Bedingung.
      const daneben = danebenGegangen();
      if (daneben.length) {
        eintraege.push({ tasten: ["B"], zeige: "B nur die Fehler",
                         tun: () => starten(daneben.map(ursprung)) });
      }
      eintraege.push({ tasten: ["Escape"], zeige: "Esc zur Startseite", tun: zeichneStart });
      return eintraege;
    }

    const k = aktuelle();

    if (k.art === "frage" && k.gewaehlt === null) {
      // Nur so viele Buchstaben, wie es Antworten gibt: Eine Frage traegt
      // laut Datenbank zwei bis vier.
      const buchstaben = BUCHSTABEN.slice(0, k.gemischte.length);
      eintraege.push({
        tasten: buchstaben.concat(buchstaben.map((_, i) => String(i + 1))),
        zeige: `${buchstaben.join(" ")} wählen`,
        tun: (gedrueckt) => {
          const nr = BUCHSTABEN.indexOf(gedrueckt);
          antworten(nr >= 0 ? nr : Number(gedrueckt) - 1);
        }
      });
    }

    if (k.art === "flashcard" && !k.aufgedeckt) {
      eintraege.push({ tasten: [" ", "Enter"], zeige: "Leertaste umdrehen", tun: umdrehen });
    }

    if (k.aufgedeckt === true && einschaetzungOffen(k)) {
      eintraege.push({ tasten: ["A"], zeige: "A wusste ich", tun: () => einschaetzen(true) });
      eintraege.push({ tasten: ["B"], zeige: "B wusste ich nicht", tun: () => einschaetzen(false) });
    }

    // Dieselbe Bedingung wie der Weiter-Knopf auf der Rueckseite
    // (ABWEICHUNG 7), damit Knopf und Taste nicht auseinanderlaufen.
    if (weiterOffen(k)) {
      eintraege.push({ tasten: ["A", "Enter", " "],
                       zeige: letzteKarte() ? "A Ergebnis" : "A weiter", tun: vor });
    }

    // Auf der ersten Karte gibt es nichts zurueckzublaettern - der Knopf
    // unten ist im selben Fall disabled, also nennt die Leiste den
    // Linkspfeil hier auch nicht.
    eintraege.push(lauf.index === 0
      ? { tasten: ["ArrowRight"], zeige: "→ blättern", tun: vor }
      : { tasten: ["ArrowLeft", "ArrowRight"], zeige: "← → blättern",
          tun: (gedrueckt) => (gedrueckt === "ArrowRight" ? vor() : zurueck()) });

    eintraege.push({ tasten: ["Escape"], zeige: "Esc beenden", tun: zeichneStart });
    return eintraege;
  };

  const tastenhinweis = () => belegung().map((e) => e.zeige).join(" · ");

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
      $("weiter").textContent = weiterText();   // ABWEICHUNG 7: eine Beschriftung, zwei Knoepfe
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
      /* ABWEICHUNG 7, Teil 1: Der freigegebene Entwurf
         docs/design/mockups/quiz-aufloesung.html trug in Variante B auf
         der Rueckseite einen Knopf ("weiter →"); der Prototyp hat ihn
         unterwegs verloren. Ohne ihn kommt am Rechner niemand mit der
         Maus weiter: Die Fussleiste ist dort per @media (hover: hover)
         ausgeblendet, und die Rueckseite trug sonst kein einziges
         Bedienelement. */
      hinten.append(knopf("knopf", "A", weiterText(), vor));
    } else {
      hinten.append(
        knoten("span", "augenbraue", "Antwort"),
        // HTML aus app/markdown.rendern(), dort gesaeubert. Siehe den
        // Block oben.
        htmlKnoten("div", "loesung", k.rueckseite)
      );
      if (einschaetzungOffen(k)) {
        const wahl = knoten("div", "selbsteinschaetzung");
        wahl.append(
          knopf("knopf", "A", "Wusste ich", () => einschaetzen(true)),
          knopf("knopf leise", "B", "Wusste ich nicht", () => einschaetzen(false))
        );
        hinten.append(wahl);
      } else {
        /* ABWEICHUNG 7, Teil 2: Derselbe Knopf wie oben, hier fuer die
           Lernkarte. Der Prototyp haengte den Zweig an k.gewusst !== null
           und liess bei abgeschalteter Selbsteinschaetzung gar nichts
           uebrig - zusammen mit der am Rechner ausgeblendeten Fussleiste
           blieb dann kein sichtbarer Weg vorwaerts. */
        if (k.gewusst !== null) {
          hinten.append(knoten("p", "erklaerung", k.gewusst ? "Als gewusst gewertet." : "Als nicht gewusst gewertet."));
        }
        hinten.append(knopf("knopf", "A", weiterText(), vor));
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
    /* preventScroll gehoert hier dazu: Der Knopf steht am Ende der
       Rueckseite. Ohne diesen Zusatz scrollt der Browser ihn beim
       Fokussieren in den Blick - bei einer langen Antwort saehe die
       Lernende zuerst deren Ende. Der Fokus wandert trotzdem, die Taste
       A wirkt trotzdem; nur der Blick bleibt am Anfang der Antwort.
       antworten() macht es an derselben Stelle genauso. */
    setTimeout(() => $("karte").querySelector(".rueckseite button")?.focus({ preventScroll: true }), 300);
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

  /* ABWEICHUNG 9: Der Prototyp ersetzte beim Blaettern den Karteninhalt,
     ohne den Fokus mitzunehmen. Lag er auf einem Knopf der Karte, war
     dieser Knopf nach replaceChildren fort und der Fokus landete auf
     <body>: Tab faengt danach wieder ganz vorn an, und eine
     Sprachausgabe verliert die Stelle. Die Spec fordert beides
     ausdruecklich - "Fokus wandert beim Kartenwechsel auf die neue
     Karte" und "Der Tastaturfokus darf nie verloren gehen".

     antworten() macht es schon richtig und setzt den Fokus auf die Karte
     (die dafuer tabindex="-1" traegt); hier ist es nachgezogen.

     Nur wenn der Fokus wirklich in der Karte lag - oder nirgends -
     wandert er mit. Stand er auf einem der Navigationsbalken unten,
     bleibt er dort: Die werden nicht ersetzt, und ihn wegzunehmen waere
     am Handy ein Rueckschritt, wo genau diese Balken das Bedienelement
     zum Weiterblaettern sind. */
  const blaettern = (schritt) => {
    const aktiv = document.activeElement;
    const fokusInDerKarte = !aktiv || aktiv === document.body || $("karte").contains(aktiv);
    lauf.index += schritt;
    zeichneKarte(false);
    ansagen(`Karte ${lauf.index + 1} von ${lauf.karten.length}.`);
    if (fokusInDerKarte) $("karte").focus({ preventScroll: true });
  };

  const vor = () => {
    if (lauf.index === lauf.karten.length - 1) { zeichneErgebnis(); return; }
    blaettern(1);
  };

  const zurueck = () => {
    if (lauf.index === 0) return;
    blaettern(-1);
  };

  /* ================== Bedienung ================== */

  $("weiter").addEventListener("click", vor);
  $("zurueck").addEventListener("click", zurueck);
  $("beenden-knopf").addEventListener("click", zeichneStart);

  /* Alles, was klickbar ist, ist auch mit der Tastatur erreichbar. Wo
     zwei Moeglichkeiten zur Wahl stehen, sind es immer A und B -
     dieselbe Geste wie bei den Antworten, damit man sich nur eine Regel
     merken muss.

     ABWEICHUNG 8: Der Prototyp loeste die Tasten aus, indem er den
     passenden Knopf suchte und anklickte. Das ging nur gut, solange
     Leiste, Hoerer und Knopfliste dasselbe meinten. Jetzt rufen Knopf
     und Taste dieselbe Funktion auf, und belegung() sagt, welche. */

  document.addEventListener("keydown", (e) => {
    // ABWEICHUNG 8: Der Hoerer entscheidet nichts mehr selbst, er fuehrt
    // aus, was belegung() fuer den aktuellen Zustand nennt - und das ist
    // genau das, was auch in der Tastenleiste steht. Verglichen wird die
    // Taste roh und in Grossschreibung, damit "a" wie "A" wirkt und
    // "Enter", " " oder "ArrowRight" unveraendert durchgehen.
    const gross = e.key.length === 1 ? e.key.toUpperCase() : e.key;
    for (const eintrag of belegung()) {
      if (eintrag.tasten.includes(e.key) || eintrag.tasten.includes(gross)) {
        e.preventDefault();
        eintrag.tun(gross);
        return;
      }
    }
  });

  zeichneStart();
})();
