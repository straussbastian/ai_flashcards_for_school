# Stichprobe, Einfügen, Umbenennung

**Datum:** 2026-08-29
**Zuschnitt:** Drei kleine, voneinander unabhängige Verbesserungen. Eine Spec,
ein Plan.

Bewusst **nicht** Teil dieser Spec: die *Sammlung* — ein Bündel von
Lernpaketen unter eigener Drei-Wort-Adresse. Die ist der nächste, größere
Schritt und bekommt eine eigene Spec.

---

## Ausgangslage

Gemessen am laufenden System (25 Lernpakete):

| Beobachtung | Zahl |
|---|---|
| Lernpakete gesamt | 25 |
| davon Englisch-Vokabeln | 13 |
| größtes Paket | **203 Karten** |
| Pakete ohne Klassenangabe | 3 |
| verschiedene Werte in `klasse` | `Englisch` (13), `WBA3` (7), `WKG2`, `wkm1`, leer (3) |

Daraus die drei Anliegen:

1. **203 Karten sind ein Durchlauf, den niemand macht.** Es gibt keine
   Möglichkeit, nur einen Teil abzufragen.
2. **Karten lassen sich nur hinten anhängen.** Die Funktion heißt
   `karten_anhaengen` und setzt `max(position) + 1`. Wer eine Vokabel an der
   richtigen Stelle nachtragen will, kann es nicht.
3. **`klasse` heißt falsch.** Das Feld trägt „Englisch" (ein Fach) neben
   „WBA3" (eine Klasse). Der Name engt ein, obwohl das Feld längst allgemeiner
   benutzt wird.

---

## A · Stichprobe: nur x Karten je Durchlauf

### Datenmodell

Neue Spalte an `bundles`:

```
karten_pro_durchlauf   INTEGER NULL
```

`NULL` heißt „alle Karten" — das ist das heutige Verhalten und bleibt die
Vorgabe. CHECK-Constraint: `karten_pro_durchlauf IS NULL OR karten_pro_durchlauf > 0`.

Bewusst **keine** Obergrenze und **keine** Prüfung gegen die Kartenzahl: Ein
Wert größer als das Paket ist kein Fehler, sondern bedeutet „alle" (siehe
Randfälle). Eine Prüfung gegen die Kartenzahl wäre außerdem nicht haltbar —
Karten kommen und gehen, der Wert am Paket bleibt.

### Der Kern: zwei getrennte Entscheidungen

Im Runner (`durchlaufBauen`) werden **welche** Karten und **in welcher
Reihenfolge** getrennt entschieden, und zwar in dieser Folge:

```
1. WELCHE:   x Karten zufällig aus dem Pool ziehen
2. FOLGE:    danach die Einstellung "reihenfolge" anwenden
             fest   → nach ursprünglicher Position sortieren
             zufall → mischen
```

**Die Reihenfolge dieser beiden Schritte ist die eigentliche Entscheidung
dieser Spec.** Andersherum — erst ordnen, dann „die ersten x" nehmen — ergäbe
bei `reihenfolge: fest` bei jedem Aufruf **dieselben** x Karten. Der Rest des
Pakets käme nie dran. Die Stichprobe muss auch dann wechseln, wenn die
Anzeigereihenfolge fest ist.

```js
const stichprobe = (quelle) => {
  const x = BUNDLE.karten_pro_durchlauf;
  if (!x || x >= quelle.length) return quelle.slice();
  return mischen(quelle).slice(0, x);
};

const kartenFolge = (quelle) => {
  const gezogen = stichprobe(quelle);
  return BUNDLE.reihenfolge === "fest"
    ? gezogen.sort((a, b) => quelle.indexOf(a) - quelle.indexOf(b))
    : mischen(gezogen);
};
```

### Was sich dadurch von selbst richtig verhält

Nachgesehen im Runner, nicht angenommen:

- **„Nochmal starten"** ruft `starten(BUNDLE.karten)` mit dem **vollen Pool**
  auf. Die Stichprobe wird dadurch bei jedem Neustart neu gezogen. Kein
  Sonderfall nötig.
- **„Nur die Fehler"** ruft `starten(daneben.map(ursprung))` mit einer
  Teilmenge auf. Die Fehlerliste kann nie größer sein als der Durchlauf, und
  der ist höchstens x — `stichprobe()` kürzt dort also nie. Ebenfalls kein
  Sonderfall.

### Anzeige

Die Startseite nennt beide Zahlen, sonst wirkt „Karte 3 von 20" bei einem
203er-Paket wie ein Fehler:

> **20** von 203 Karten — bei jedem Start neu gezogen

Bei `karten_pro_durchlauf = NULL` bleibt die Startseite unverändert.

Der Fortschritt in der Kopfzeile („Karte 3 von 20") und die Ergebnisseite
zählen weiterhin **innerhalb des Durchlaufs**. Das ist richtig so: Bewertet
wird, was abgefragt wurde.

### Randfälle

| Fall | Verhalten |
|---|---|
| `x` ≥ Kartenzahl | alle Karten, keine Meldung |
| `x` = 1 | ein Durchlauf mit einer Karte |
| `x` = 0 oder negativ | von der Datenbank abgelehnt |
| Paket ohne Karten | unverändert der bestehende Hinweis |

### MCP

`bundle_anlegen` und `bundle_aendern` bekommen den optionalen Parameter
`karten_pro_durchlauf`. `bundle_liste` und `bundle_anzeigen` geben ihn mit
aus.

**Wie setzt man auf „alle Karten" zurück?** `bundle_aendern` unterscheidet
heute „nicht angegeben" (`None`) von „löschen" über einen **leeren Text** —
so steht es bei `beschreibung` und `gruppe`. Für eine Zahl gibt es keinen
leeren Text.

Deshalb: **`karten_pro_durchlauf = 0` bedeutet „alle Karten"** und setzt das
Feld auf `NULL`. Das kollidiert mit nichts, weil `0` als gespeicherter Wert
ohnehin vom CHECK-Constraint abgelehnt wird — die Null ist frei und kann diese
eine Bedeutung tragen. In der Werkzeugbeschreibung steht das wörtlich, damit
der Agent nicht raten muss:

> Wie viele Karten je Durchlauf abgefragt werden. `0` bedeutet: alle.

Ohne diese Festlegung gäbe es keinen Weg zurück: Ein einmal gesetztes
`karten_pro_durchlauf` ließe sich nie wieder aufheben, weil `None` bereits
„nicht angegeben" heißt.

---

## B · Karten an einer Stelle einfügen

### MCP-Signatur

`karten_hinzufuegen` bekommt einen optionalen Parameter:

```
position: int | None     0-basiert. Leer = ans Ende (heutiges Verhalten).
```

Gewählt wurde die Zahl und nicht `nach_karte_id`, weil `bundle_anzeigen` zu
jeder Karte bereits ihre `position` ausgibt — der Agent hat sie unmittelbar
zur Hand, und `0` als „ganz nach vorn" braucht keinen Sonderwert.

**Bekannte Schwäche dieser Wahl:** Positionen verschieben sich, sobald jemand
anderes zwischendurch einfügt. Der Wert kann also veralten. Im
Ein-Personen-Betrieb über einen Agenten, der unmittelbar vor dem Schreiben
liest, ist das folgenlos; bei mehreren gleichzeitigen Bearbeitern wäre
`nach_karte_id` die stabilere Wahl. Dies ausdrücklich hier notiert, damit die
Entscheidung später nachvollziehbar ist.

### Umnummerieren

Beim Einfügen an Position `p` mit `n` neuen Karten rücken alle Karten ab `p`
um `n` nach hinten — **in derselben Transaktion**. Möglich ist das nur, weil
`uq_karten_bundle_position` als `DEFERRABLE INITIALLY DEFERRED` angelegt ist:
Während der Umnummerierung gibt es zwangsläufig kurzzeitig doppelte
Positionen, geprüft wird erst beim Commit.

Das Verschieben muss **absteigend** geschehen (höchste Position zuerst) oder
in einem einzigen `UPDATE ... SET position = position + n WHERE position >= p`.
Letzteres ist vorzuziehen: ein Befehl, keine Reihenfolgefrage.

### Randfälle

| Fall | Verhalten |
|---|---|
| `position` fehlt | ans Ende, wie bisher |
| `position` = 0 | ganz nach vorn |
| `position` > höchste Position | ans Ende, kein Fehler |
| `position` negativ | Klartext-Fehler über MCP |
| Paket ohne Karten | jede Position ergibt Position 0 |

### Ausdrücklich nicht dabei

Eine bestehende Karte **verschieben**. Das ist ein anderes Verb und wäre ein
eigenes Werkzeug (`karte_verschieben`). Es hier mitzunehmen würde
`karte_aendern` eine zweite Aufgabe geben.

---

## C · `klasse` → `gruppe`

Eine reine Umbenennung. **Kein Verhalten ändert sich**, das Feld bleibt ein
einzelnes Freitextfeld.

### Betroffene Stellen

| Datei | Was |
|---|---|
| `app/models.py` | Spalte, `MAX_KLASSE_LAENGE`, Constraint-Name |
| `migrations/` | neue Revision: `ALTER TABLE ... RENAME COLUMN` |
| `app/mcp/dienste.py` | Parameter und Filter |
| `app/mcp/karten.py` | `klasse_pruefen` |
| `app/mcp/werkzeuge.py` | drei Werkzeug-Signaturen und Beschreibungen |
| `app/bundle_json.py` | Feld an den Browser |
| `app/static/runner.js` | **nur** `BUNDLE.klasse` (siehe unten) |
| Tests | 9 Dateien |

### Die Falle in runner.js

In `app/static/runner.js` steht `klasse` **neunmal**, aber nur **einmal**
meint es dieses Feld:

```js
const knoten = (tag, klasse, text) => …        // CSS-Klasse
const htmlKnoten = (tag, klasse, html) => …    // CSS-Klasse
const knopf = (klasse, taste, …) => …          // CSS-Klasse
const seiteBauen = (klasse) => …               // CSS-Klasse
knoten("span", "klasse", "Geschafft")          // CSS-Klasse (Ergebnisseite)

if (BUNDLE.klasse) s.append(knoten("span", "klasse", BUNDLE.klasse));
//     ^^^^^^^^^^^^^ das Feld        ^^^^^^^^ CSS-Klasse
```

Ein pauschales Suchen-und-Ersetzen zerlegt den Runner. Zu ändern ist
**ausschließlich** `BUNDLE.klasse` → `BUNDLE.gruppe`.

Die CSS-Klasse `.klasse` in `lernseite.css` bleibt, wie sie heißt: Sie
gestaltet auch das Wort „Geschafft" auf der Ergebnisseite und ist damit ein
Stil, kein Feld.

### Drift bremsen

`bundle_liste` gibt zusätzlich zurück, welche Werte bereits vergeben sind:

```
"vorhandene_gruppen": ["Englisch", "WBA3", "WKG2", "wkm1"]
```

Damit sieht der Agent beim Anlegen, was es schon gibt, und schreibt „WBA3"
statt „wba3". Das ist kein Zwang, sondern ein Hinweis — bewusst keine
Auswahlliste und keine Normalisierung.

**Nicht behoben und bewusst so:** `wkm1` steht weiterhin neben `WKG2`, und das
eine Feld trägt weiterhin Fach *und* Klasse. Wer das ändern will, braucht
mehrere Werte je Paket; das ist eine eigene Entscheidung und nicht Teil dieser
Umbenennung.

---

## Migration

Eine Alembic-Revision für alle drei Punkte:

1. `ALTER TABLE bundles RENAME COLUMN klasse TO gruppe`
2. Constraint `ck_bundles_klasse_max_laenge` → `ck_bundles_gruppe_max_laenge`
3. `ALTER TABLE bundles ADD COLUMN karten_pro_durchlauf INTEGER NULL`
4. CHECK `karten_pro_durchlauf IS NULL OR karten_pro_durchlauf > 0`

`downgrade()` macht alle vier rückgängig. Bestehende Daten bleiben unberührt —
ein `RENAME COLUMN` bewegt keine Zeilen.

Für Punkt B ist **keine** Migration nötig: Positionen und Constraint gibt es
bereits.

---

## Tests

| Ebene | Was geprüft wird |
|---|---|
| Modell | die beiden neuen Constraints lehnen ab (`0`, negativ) |
| Migration | `alembic upgrade head` und `downgrade` laufen durch; `alembic check` bleibt still |
| MCP | `karten_pro_durchlauf` setzen, ändern, zurücksetzen; `position` einfügen (0, Mitte, zu groß, negativ); `gruppe` in allen drei Werkzeugen; `vorhandene_gruppen` |
| Dienste | Umnummerierung: Positionen bleiben lückenlos und eindeutig |
| Browser | Stichprobe: Durchlauf hat x Karten; zwei Durchläufe ziehen (über mehrere Versuche) nicht dieselbe Menge; bei `reihenfolge: fest` stehen die gezogenen Karten in ursprünglicher Reihenfolge; Startseite nennt beide Zahlen |

Der Browsertest zur wechselnden Stichprobe muss über **mehrere Durchläufe**
prüfen und nicht über einen: Zwei Ziehungen können zufällig gleich sein. Bei
20 aus 203 ist das astronomisch unwahrscheinlich, bei kleinen Testpaketen
nicht — der Test benutzt deshalb ein Paket, in dem die Wahrscheinlichkeit
klein genug ist, und prüft „nicht alle Durchläufe identisch" statt „diese
beiden verschieden".

---

## Risiken

**Die Umbenennung ist die riskanteste der drei Änderungen**, obwohl sie
inhaltlich nichts tut: Sie berührt 8 Quelldateien und 9 Testdateien, und in
`runner.js` bedeutet dasselbe Wort zweierlei. Ein unachtsames Ersetzen bricht
die Darstellung, ohne dass ein Test zwingend anschlägt — die CSS-Klasse
`.klasse` ist reine Optik.

**Die Stichprobe ändert, was eine Ergebniszahl bedeutet.** „18 von 20" heißt
künftig „18 von 20 abgefragten", nicht „von 203". Die Startseite muss das
deutlich machen, sonst hält die Klasse ein Paket für vollständig durchgearbeitet,
das sie zu einem Zehntel gesehen hat.
