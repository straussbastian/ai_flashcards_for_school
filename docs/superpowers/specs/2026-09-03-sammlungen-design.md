# Sammlungen

**Datum:** 2026-09-03

Ein Bündel von Lernpaketen unter einer eigenen Drei-Wort-Adresse. Die
Lehrkraft schickt der Klasse **einen** Link statt dreizehn.

---

## Ausgangslage

Gemessen am laufenden System: 25 Lernpakete, davon 13 Englisch-Vokabeln,
betitelt `Englisch 1:` bis `Englisch 12:`. Daraus drei Befunde:

1. **Dreizehn Links für einen Zusammenhang.** Es gibt keinen Weg, eine Reihe
   von Lernpaketen als eine Sache weiterzugeben.
2. **Die Reihenfolge steckt im Titel** (`Englisch 1:`, `KER 1/2/3`,
   `Teil 1 von 3`). Als Text getarnt, für niemanden auswertbar — und
   alphabetisch sortiert stünde `Englisch 10` vor `Englisch 2`.
3. **Ein Lernpaket kann heute zu genau einem Zusammenhang gehören**, weil
   `gruppe` ein einzelnes Feld ist.

## Was eine Sammlung ist — und was nicht

Eine Sammlung ist eine **Seite mit einer Adresse, für die Lernenden**.

`gruppe` bleibt daneben bestehen und behält eine andere Aufgabe: das
Wiederfinden beim Pflegen, für die Lehrkraft, über `bundle_liste`. Beide
lösen verschiedene Probleme für verschiedene Leute; keines ersetzt das
andere.

---

## 1 · Der Adressraum wird strukturell eindeutig

Sammlungen bekommen dieselbe Form von Adresse wie Lernpakete. Damit teilen
sich **zwei Tabellen einen Adressraum** — und keine Datenbank kann eine
Eindeutigkeit über zwei Tabellen erzwingen.

Ein Wettlauf beim Anlegen ergäbe zwei Zeilen mit derselben Adresse, und
`/{slug}` lieferte still aus, was es zuerst findet. Bei einer Anwendung,
deren gesamte Zugangssicherung die unerratbare Adresse ist, wäre
„unwahrscheinlich" die falsche Antwort: Ein Link, den eine Klasse in der Hand
hat, darf niemals auf etwas anderes zeigen als beim Weitergeben.

Deshalb eine gemeinsame Tabelle, auf die beide verweisen:

```
adressen         slug varchar(120) PRIMARY KEY
                 art  varchar(20) NOT NULL   -- 'paket' | 'sammlung'

bundles.slug     → adressen.slug   (FK)
sammlungen.slug  → adressen.slug   (FK)
```

Die Eindeutigkeit garantiert damit die Datenbank selbst.

**Das ist nur deshalb sauber, weil in dieser Anwendung nichts je gelöscht
wird.** Es gibt kein `bundle_loeschen` — nur `bundle_deaktivieren`. Eine
Adresse wird also nie frei, und es braucht kein Aufräumen verwaister
Einträge. Wer später ein echtes Löschen einführt, muss diese Tabelle
mitdenken.

`freien_slug_finden` prüft künftig gegen `adressen` statt gegen `bundles` und
gilt damit für beide Arten.

### Migration

`adressen` anlegen, aus `bundles.slug` befüllen (`art = 'paket'`), dann den
Fremdschlüssel setzen. Bestehende Adressen ändern sich **nicht** — kein
ausgegebener Link wird ungültig. Das ist die Bedingung, unter der diese
Migration überhaupt vertretbar ist.

---

## 2 · Datenmodell

```
sammlungen
  id            uuid PK
  slug          varchar(120) UNIQUE, FK → adressen.slug
  titel         text NOT NULL
  beschreibung  text NULL          (Markdown, wie beim Lernpaket)
  gruppe        text NULL          (zum Wiederfinden, wie beim Lernpaket)
  aktiv         boolean NOT NULL DEFAULT true
  erstellt_am, geaendert_am

sammlung_pakete
  sammlung_id   uuid FK → sammlungen ON DELETE CASCADE
  bundle_id     uuid FK → bundles    ON DELETE CASCADE
  position      integer NOT NULL
  PRIMARY KEY (sammlung_id, bundle_id)
  UNIQUE (sammlung_id, position) DEFERRABLE INITIALLY DEFERRED
```

**n:m, ausdrücklich.** Ein Lernpaket darf in mehreren Sammlungen liegen —
„Englisch 3" gleichzeitig in „Englisch komplett" und in „Prüfung Januar",
mit eigener Position in jeder. Der Primärschlüssel verhindert nur dasselbe
Paket **zweimal in derselben** Sammlung.

`DEFERRABLE` bei der Position aus demselben Grund wie bei den Karten:
Umsortieren erzeugt zwangsläufig kurzzeitig doppelte Positionen, geprüft wird
erst beim Commit.

Die Zeitstempel führt das ORM (`onupdate=func.now()`), wie überall sonst.

---

## 3 · Die Routen

| Adresse | Antwort |
|---|---|
| `/{slug}` | Sammlung **oder** Lernpaket — `adressen.art` entscheidet |
| `/{sammlung}/{paket}` | das Lernpaket **im Kontext** dieser Sammlung |
| `/{paket}` | unverändert das einzelne Lernpaket |

Die zweisegmentige Route wird **vor** `/{slug}` eingehängt; `/{slug}` bleibt
die letzte Route überhaupt (so steht es schon heute in `app/main.py`).

Beide Segmente werden gegen dasselbe `ADRESSE`-Muster geprüft, mit
`re.fullmatch` und aus denselben Gründen wie bisher (404 statt 422; kein
Schlupfloch über ein abschließendes `\n`).

### Randfälle

| Fall | Antwort |
|---|---|
| Sammlung gibt es nicht | 404, dieselbe deutsche Seite wie heute |
| Sammlung ist deaktiviert | 404 — wie ein deaktiviertes Lernpaket |
| Paket gibt es nicht | 404 |
| Paket ist deaktiviert | 404 |
| Paket liegt **nicht** in dieser Sammlung | 404 — **nicht** stillschweigend das Paket ohne Kontext zeigen. Eine erfundene Kombination ist ein Irrtum und soll als solcher erscheinen. |
| Sammlung ohne Pakete | Seite mit Hinweis, wie ein Lernpaket ohne Karten |

---

## 4 · Was die Lernende sieht

### Die Sammlungsseite

**Kein JavaScript.** Titel, Beschreibung und die Lernpakete in ihrer
Reihenfolge — ein serverseitiges Template im vorhandenen Zettel-Stil
(`lernseite.css`, dieselben Klassen). Der Runner bleibt unangetastet.

Je Paket: Titel, Kartenzahl und Zusammensetzung, verlinkt auf die
verschachtelte Adresse. **Deaktivierte Pakete erscheinen nicht** und werden
auch nicht mitgezählt.

### Das Lernpaket im Kontext

`bundle_json.bauen()` bekommt einen optionalen Block:

```json
"sammlung": {
  "titel": "Englisch komplett",
  "url": "/leise-katze-blinkt",
  "naechstes": { "titel": "Englisch 2: Schule", "url": "/leise-katze-blinkt/gelassene-treppe-hobelt" }
}
```

Fehlt der Block (Aufruf ohne Sammlung), verhält sich der Runner exakt wie
heute. Ist er da, trägt der Ergebnisbildschirm zusätzlich **„weiter zu
Englisch 2"** und **„zurück zur Sammlung"**. `naechstes` ist `null` beim
letzten Paket.

Das Nächste bestimmt der **Server** aus der Position, nicht der Browser: Der
Runner kennt nur sein eigenes Paket, und die Reihenfolge gehört ins
Datenmodell.

---

## 5 · MCP

Sechs neue Werkzeuge:

| Werkzeug | Zweck |
|---|---|
| `sammlung_anlegen` | Titel, optional Beschreibung/Gruppe, optional gleich Pakete |
| `sammlung_liste` | wie `bundle_liste`, mit Filter auf `gruppe` und `nur_aktive` |
| `sammlung_anzeigen` | die Sammlung mit ihren Paketen in Reihenfolge |
| `sammlung_aendern` | Kopfdaten; die Adresse bleibt unangetastet |
| `sammlung_pakete_setzen` | **die ganze Liste** in der gewünschten Reihenfolge |
| `sammlung_deaktivieren` | unsichtbar schalten, wie beim Lernpaket |

**Der Preis, ausdrücklich benannt:** Die Werkzeugliste wächst von 8 auf 14.
Jedes zusätzliche Werkzeug ist eines, bei dem der Agent danebengreifen kann.

Deshalb `sammlung_pakete_setzen` als **ein** Werkzeug, das die vollständige
Liste ersetzt, statt `hinzufuegen`/`entfernen`/`verschieben` als drei. Der
Agent liest mit `sammlung_anzeigen`, ordnet, schreibt zurück. Ein Paket
mehrfach in derselben Liste ist ein Klartext-Fehler; eine leere Liste ist
erlaubt und leert die Sammlung.

Jede Antwort nennt die vollständige URL der Sammlung — so wie es die
Serveranweisung für alle Werkzeuge verlangt.

---

## 6 · Tests

| Ebene | Was |
|---|---|
| Modell | `adressen` erzwingt Eindeutigkeit über beide Tabellen; Position eindeutig je Sammlung; dasselbe Paket nicht zweimal in einer Sammlung |
| Migration | hoch und runter mit echten Daten; **bestehende Adressen unverändert** |
| Slug | `freien_slug_finden` meidet belegte Paket- **und** Sammlungsadressen |
| MCP | die sechs Werkzeuge; `pakete_setzen` mit Dopplung, mit leerer Liste, mit unbekanntem Slug |
| Route | Sammlung, Paket, verschachtelt; die sechs Randfälle aus Abschnitt 3 |
| bundle_json | Block `sammlung` vorhanden/abwesend; `naechstes` beim letzten Paket `null` |
| Browser | Sammlungsseite listet in Reihenfolge; ein Paket im Kontext durchlaufen und über „weiter" im nächsten landen; ohne Kontext ist der Ergebnisbildschirm unverändert |

Ein Test verdient eigene Erwähnung: **dasselbe Paket in zwei Sammlungen**,
über beide Adressen aufgerufen, muss jeweils den richtigen Rückweg und das
richtige nächste Paket zeigen. Das ist der Grund, warum die Adresse
verschachtelt ist, und damit die Zusicherung, die am ehesten unbemerkt
brechen würde.

---

## 7 · Nicht Teil dieser Spec

- **Sammlungen in Sammlungen.** Eine Ebene reicht.
- **Fortschritt über die Sammlung hinweg.** Es wird nichts gespeichert; das
  ist eine Zusage der Spec und keine Lücke.
- **Eine Übersicht aller Sammlungen im Browser.** Die Startseite bleibt leer.
  Wer eine Sammlung sehen will, braucht ihre Adresse — genau wie bei einem
  Lernpaket.
- **`gruppe` durch Sammlungen ersetzen.** Beide bleiben, mit
  unterschiedlichen Aufgaben (siehe oben).

---

## 8 · Risiken

**Die gemeinsame Adresstabelle ist der einzige Eingriff in Bestehendes.**
Sie berührt `bundles`, eine Tabelle mit echten Daten hinter ausgegebenen
Links. Die Migration darf keine einzige Adresse verändern; ein Tippfehler
dort macht jeden verteilten Link ungültig, und niemand merkt es, bis eine
Klasse davorsteht. Der Migrationstest prüft deshalb ausdrücklich die
Unveränderlichkeit bestehender Adressen.

**Vierzehn Werkzeuge sind viele.** Ob der Agent damit noch zuverlässig das
richtige greift, lässt sich vorher nicht ausrechnen — das zeigt erst der
Gebrauch. Sollte es klemmen, ist die naheliegende Antwort nicht, Werkzeuge
zusammenzulegen, sondern ihre Beschreibungen zu schärfen.

**Die verschachtelte Adresse verdoppelt die Wege zu einem Lernpaket.** Jede
Änderung an der Lernseite muss künftig in beiden Zusammenhängen bedacht
werden — mit Sammlung und ohne. Die Browsertests decken beide ab, damit das
nicht vom Erinnern abhängt.
