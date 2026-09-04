# Technische Beschreibung

Ein Überblick über Zweck, Aufbau und Bedienung – ohne Programmcode. Stand:
4. September 2026.

Dieselbe Beschreibung als eigenständige Seite für den Browser:
[technische-beschreibung.html](technische-beschreibung.html).

Für die ausführbaren Anleitungen siehe [betrieb-server.md](betrieb-server.md)
(Betrieb auf einem eigenen Server) und
[praxistest-cowork.md](praxistest-cowork.md) (den Agenten verbinden).

---

## 1. Zweck

Eine Lehrkraft an einer Berufsschule soll Lernmaterial in Minuten
veröffentlichen können, ohne eine Software zu bedienen, ohne Daten ihrer
Schülerinnen und Schüler zu verwalten und ohne jemanden um Erlaubnis zu
fragen.

Das Programm löst genau eine Aufgabe: Es macht aus Unterrichtsinhalten eine
Lernseite, die unter einem teilbaren Link im Browser läuft. Der Inhalt kommt
nicht über eine Eingabemaske herein, sondern über einen KI-Agenten – die
Lehrkraft schickt ein Arbeitsblatt, eine Vokabelliste oder einen
Prüfungskatalog in den Chat und bekommt eine fertige Adresse zurück.

Für die Lernenden ist es eine gewöhnliche Webseite: Link öffnen, Startknopf
drücken, Karte für Karte durcharbeiten, am Ende das Ergebnis sehen. Es gibt
keine Anmeldung, keine Installation und keine Spur, die zurückbleibt.

> Die gestaltende Entscheidung des Projekts: **Die Verwaltungsoberfläche ist
> der Chat.** Es gibt keinen Adminbereich, in den sich jemand einloggen könnte
> – und damit auch keinen, den jemand angreifen, erklären oder pflegen müsste.

---

## 2. Das Ganze in einem Bild

Zwei Wege führen zur selben Anwendung. Der obere gehört der Lehrkraft und ist
abgesichert; der untere gehört der Klasse und ist offen für jeden, der die
Adresse kennt.

```
  Lehrkraft ──▶ KI-Agent ─── MCP · HTTPS · OAuth 2.1 ──┐
  (im Chat)     (Cowork)                               │
                                          ┌────────────▼────────────┐
                                          │  Anwendung              │
                                          │  FastAPI · ein Prozess  │
                                          │  ─────────────────────  │      ┌──────────────┐
                                          │  POST /mcp   – pflegen  │─────▶│ PostgreSQL   │
                                          │  /oauth/…    – anmelden │      │ Volume pgdata│
  Klasse ────── Link aus drei Wörtern ───▶│  GET /{adresse} – lernen│      └──────────────┘
  (im Browser)                            │  GET /healthz           │
                                          └─────────────────────────┘
```

Die Anwendung ist ein einziger Prozess: Lernseiten, MCP-Endpunkt und
OAuth-Server liegen darin nebeneinander. Nach außen erreichbar sind nur
HTTP-Wege; die Datenbank hat weder lokal noch auf dem Server einen
veröffentlichten Port.

---

## 3. Die vier Begriffe, die man kennen muss

### Die Drei-Wort-Adresse

Jede veröffentlichte Seite bekommt eine Adresse aus drei deutschen Wörtern –
Adjektiv, Nomen, Verb, aus je 200 Wörtern gewürfelt. Das sind acht Millionen
mögliche Adressen. Sie ist gleichzeitig der Zugang: Wer sie hat, darf lernen;
wer sie nicht hat, bekommt dieselbe Fehlerseite wie bei einem Tippfehler.
Lernpakete und Sammlungen teilen sich einen einzigen Adressraum, den die
Datenbank selbst eindeutig hält.

### Das Lernpaket

Eine Lernseite mit ihren Karten – der Normalfall, etwa „Unregelmäßige Verben,
Teil 3“. Es trägt einen Titel, wahlweise einen Einleitungstext in Markdown und
eine *Gruppe* (ein Fach oder eine Klasse, etwa „Englisch“ oder „WBA3“), die der
Lehrkraft beim Wiederfinden hilft und die Lernenden nicht weiter betrifft.

### Die Karte

Es gibt genau zwei Arten:

- **Karteikarte** – Vorderseite und Rückseite. Anklicken dreht sie um.
- **Frage** – zwei bis vier Antwortmöglichkeiten, genau eine davon richtig,
  dazu wahlweise eine Erklärung, die nach dem Antworten erscheint.

Alle Textfelder sind Markdown und auf 5.000 Zeichen begrenzt; Titel auf 200,
Gruppe auf 60.

### Die Sammlung

Ein Bündel von Lernpaketen unter einer eigenen Drei-Wort-Adresse – damit die
Lehrkraft *einen* Link weitergeben kann statt dreizehn. Die Sammlung zeigt ihre
Pakete als nummerierte Liste; von einem Paket aus führt ein Knopf weiter zum
nächsten und einer zurück zur Übersicht. Ein Lernpaket darf in mehreren
Sammlungen liegen, jeweils an anderer Stelle.

---

## 4. Bedienung durch die Lehrkraft

Über einen KI-Agenten, der sich einmalig mit dem Server verbindet. Danach
genügt der Satz: „Bau mir aus diesem Arbeitsblatt ein Lernpaket."

Technisch ist das ein **MCP-Server** (Model Context Protocol) unter
`POST /mcp`. Die Lehrkraft trägt in ihrem Agenten – erprobt mit Claude Cowork –
die Adresse dieses Endpunkts ein, meldet sich einmal mit dem Passwort an, das
der Betreiber gesetzt hat, und bestätigt die Verbindung. Von da an stehen dem
Agenten vierzehn Werkzeuge zur Verfügung. Nach jeder Änderung antwortet der
Server mit dem vollständigen, anklickbaren Link.

### Werkzeuge für Lernpakete

| Werkzeug | Wofür |
|---|---|
| `bundle_anlegen` | Ein neues Lernpaket samt allen Karten in einem Aufruf |
| `bundle_liste` | Was gibt es? Filterbar nach Gruppe; stillgelegte auf Wunsch |
| `bundle_anzeigen` | Ein Paket mit allen Karten und deren Kennungen |
| `bundle_aendern` | Titel, Beschreibung, Gruppe, Reihenfolge, Stichprobe – der Link bleibt |
| `bundle_deaktivieren` | Unsichtbar schalten und wieder zurück |
| `karten_hinzufuegen` | Weitere Karten, wahlweise an einer bestimmten Stelle |
| `karte_aendern` | Eine einzelne Karte berichtigen |
| `karte_loeschen` | Eine einzelne Karte entfernen |

### Werkzeuge für Sammlungen

| Werkzeug | Wofür |
|---|---|
| `sammlung_anlegen` | Eine neue Sammlung, wahlweise gleich mit Paketen |
| `sammlung_liste` | Übersicht, wie bei den Lernpaketen |
| `sammlung_anzeigen` | Eine Sammlung mit ihren Paketen in ihrer Reihenfolge |
| `sammlung_aendern` | Titel, Beschreibung, Gruppe |
| `sammlung_pakete_setzen` | Welche Pakete in welcher Reihenfolge darin stehen |
| `sammlung_deaktivieren` | Unsichtbar schalten und wieder zurück |

### Was sich pro Lernpaket einstellen lässt

- **Reihenfolge** – `zufall` mischt die Karten bei jedem Durchlauf neu, `fest`
  behält die eingegebene Folge bei. Die Antwortmöglichkeiten einer Frage werden
  in beiden Fällen immer neu gemischt.
- **Karten pro Durchlauf** – aus einem Paket mit 200 Karten werden bei jedem
  Start etwa 20 zufällig gezogen. Ohne Angabe kommen alle dran.
- **Selbsteinschätzung** – ob Karteikarten mit „Wusste ich“ / „Wusste ich
  nicht“ ins Ergebnis eingehen oder reines Lernmaterial bleiben.

**Endgültiges Löschen gibt es nicht.** Ein Paket oder eine Sammlung lässt sich
stilllegen – Aufrufer sehen dann einen Hinweis statt der Seite –, aber nichts
kann versehentlich weggeworfen werden. Deshalb wird auch keine Adresse je
wieder frei.

---

## 5. Bedienung durch die Klasse

Der Link geht in den Klassenchat, als QR-Code an die Wand oder auf das
Arbeitsblatt. Alles Weitere passiert im Browser.

### Der Ablauf

- **Startseite.** Titel, Gruppe, Einleitungstext und die Zusammensetzung des
  Pakets: wie viele Karten insgesamt, wie viele zum Lernen, wie viele Fragen.
  Wird nur eine Stichprobe abgefragt, steht das dabei. Dann: „Los geht's“.
- **Karteikarte.** Vorderseite lesen, umdrehen, Rückseite lesen. Ist die
  Selbsteinschätzung eingeschaltet, folgt die Frage, ob man es wusste.
- **Frage.** Eine Antwort von A bis D wählen. Die Auflösung kommt sofort:
  richtig oder falsch, dazu die richtige Antwort und, falls hinterlegt, die
  Erklärung.
- **Ergebnis.** Punktzahl, ein kurzes Fazit und die Liste dessen, was
  danebenging. Von dort führen drei Wege weiter: alles nochmal, nur die Fehler,
  oder – innerhalb einer Sammlung – weiter zum nächsten Paket.

### Tastatur

Die Seite ist vollständig mit der Tastatur bedienbar, und jeder Knopf trägt
sein Kürzel sichtbar: `Enter` startet, `Leertaste` dreht eine Karteikarte um,
`A`–`D` beantworten eine Frage, `←` und `→` blättern. Beim Blättern wandert der
Fokus mit, und jede Auflösung wird für Sprachausgaben angesagt.

---

## 6. Was das Programm bewusst nicht tut

Diese Punkte sind keine Lücken, sondern der Kern des Entwurfs. Sie sind der
Grund, warum die Anwendung in einer Schule ohne Rückfragen laufen kann.

| | |
|---|---|
| **Keine Anmeldung für Lernende** | Kein Konto, kein Passwort, keine Klassenliste. Wer den Link hat, kann lernen. |
| **Keine gespeicherten Ergebnisse** | Die Punktzahl steht am Ende auf dem Bildschirm und ist danach fort. Sie wird nirgends gespeichert und nirgends übermittelt – auch nicht an die Lehrkraft. |
| **Keine Cookies, kein Speicher im Browser, keine Zählpixel** | Der Zwischenstand lebt nur im Arbeitsspeicher der geöffneten Seite. Neu laden heißt neu anfangen. Nach dem Laden spricht die Seite mit niemandem mehr. |
| **Keine fremden Server** | Keine Schriftarten, Bilder oder Skripte von außerhalb. Die Sicherheitsrichtlinie der Seite verbietet sie ausdrücklich. |
| **Keine Verwaltungsoberfläche** | Es gibt keine Anmeldeseite für Menschen. Inhalte kommen ausschließlich über den KI-Agenten herein. |
| **Kein endgültiges Löschen** | Nur Stilllegen. Ein falsch verstandener Auftrag kann kein halbes Schuljahr Arbeit vernichten. |

---

## 7. Aufbau

Drei Container, mehr nicht. Die Anwendung selbst ist ein einziger Prozess:
Lernseiten, MCP-Endpunkt und OAuth-Server sind Routen darin, keine getrennten
Dienste.

| Baustein | Was darin läuft |
|---|---|
| **Anwendung** | Python 3.13, FastAPI, uvicorn. Seiten aus Jinja2-Vorlagen, Daten über SQLAlchemy, Schema-Änderungen über Alembic. |
| **Datenbank** | PostgreSQL 17, das offizielle Abbild, unverändert. Ohne veröffentlichten Port – nur aus dem Docker-Netz erreichbar. |
| **Rückwärtsproxy** | Caddy, nur im Serverbetrieb. Holt das HTTPS-Zertifikat selbsttätig bei Let's Encrypt und erneuert es. |

### Wie die Inhalte zur Seite werden

Alle Texte sind Markdown. Beim Ausliefern rendert markdown-it sie zu HTML, und
nh3 säubert das Ergebnis anschließend gegen eine Positivliste erlaubter
Elemente – Attribute werden vollständig entfernt. Das ist die einzige Stelle,
an der aus Text HTML wird, und damit die Verteidigungslinie zwischen dem, was
ein Agent schreibt, und dem, was im Browser der Lernenden landet. Antworttexte,
Titel und Gruppe laufen gar nicht erst durch diesen Weg und werden immer als
reiner Text gesetzt.

Die Karten reisen als Datenblock mit der Seite mit. Der Ablauf im Browser –
Mischen, Umdrehen, Auswerten – läuft danach ohne jede weitere Anfrage an den
Server.

### Was die Datenbank selbst erzwingt

Ein großer Teil der Regeln steht nicht im Programmcode, sondern als Bedingung
im Schema: dass eine Frage zwischen zwei und vier Antworten hat, dass genau
eine davon als richtig markiert ist, dass keine davon leer ist, dass eine
Karteikarte eine Rückseite hat und eine Frage keine, dass Titel und
Karteninhalte ihre Längengrenzen einhalten. Falsche Daten können deshalb gar
nicht erst hineingelangen – unabhängig davon, welcher Agent sie schickt.

---

## 8. Sicherheit

### Der Zugang der Lehrkraft

Der MCP-Endpunkt ist mit **OAuth 2.1** abgesichert. Der Agent meldet sich
selbsttätig als Client an (dynamische Registrierung), findet die Endpunkte über
die üblichen Discovery-Dokumente und weist sich mit PKCE S256 aus, nicht mit
einem Client-Geheimnis. Der einzige menschliche Schritt ist eine
Zustimmungsseite, auf der das Betreiberpasswort eingegeben wird – die einzige
Seite des Projekts mit einem Formular.

- Ein Autorisierungscode gilt **zehn Minuten** und lässt sich genau einmal
  einlösen.
- Ein Zugriffstoken gilt **eine Stunde**, ein Erneuerungstoken **30 Tage**.
- Erneuerungstokens rotieren. Wird ein bereits verbrauchter zum zweiten Mal
  vorgelegt, verfällt die gesamte Token-Familie – ein gestohlener Token wird
  dadurch erkennbar und wertlos.
- Tokens und Codes liegen ausschließlich als Hash in der Datenbank.
- Alle öffentlichen Adressen entstehen aus dem eingetragenen Wert `BASE_URL`
  und niemals aus einem Anfragekopf – hinter einem Rückwärtsproxy wären die
  fälschbar.

### Der Zugang der Lernenden

Es gibt keinen. Die Lernseite ist öffentlich für jeden, der die Adresse kennt.
Eine formal falsche und eine unbekannte Adresse liefern dieselbe Antwort, sodass
sich aus dem Unterschied nichts erraten lässt; ein stillgelegtes Paket sagt
ausdrücklich, dass es stillgelegt wurde.

### Im Browser

Jede Antwort trägt eine strenge Inhaltsrichtlinie: `default-src 'none'`.
Skripte und Stile nur von der Seite selbst, keine Bilder, keine Schriftarten,
keine Netzverbindungen, keine Einbettung in fremde Rahmen. Der Datenblock mit
den Karten wird so eingebettet, dass ein Karteninhalt ihn nicht verlassen kann.

HTTPS ist Pflicht, nicht Empfehlung: Die verbindenden Agenten sprechen
ausschließlich über HTTPS mit dem Server.

---

## 9. Betrieb

Ein kleiner Server ab etwa vier Euro im Monat genügt. Auf dem Server selbst
wird nichts gebaut und nichts eingerichtet; das fertige Abbild kommt aus der
Registry.

### Die vier Werte, die gesetzt werden müssen

| Wert | Bedeutung |
|---|---|
| `DATABASE_URL` | Wo die Datenbank steht, samt Zugangsdaten |
| `APP_SECRET` | Signaturschlüssel für die OAuth-Tokens; lang und zufällig |
| `TEACHER_PASSWORD` | Das eine Passwort, mit dem sich die Lehrkraft beim Verbinden anmeldet |
| `BASE_URL` | Die öffentliche Adresse. Pflichtangabe ohne Vorgabewert – ohne sie startet die Anwendung nicht. |

`BASE_URL` hat mit Absicht keinen Vorgabewert: Aus ihr entstehen sowohl die
Links, die die Lehrkraft bekommt, als auch alle OAuth-Adressen. Ein vergessener
Wert soll beim Start auffallen und nicht erst an einem Link, den niemand öffnen
kann.

### Sichern

Alles, was zu sichern ist, liegt im Docker-Volume `pgdata`. Wer dieses Volume
sichert, hat alles; die Anwendung bringt deshalb keine eigene Sicherungsfunktion
mit. Das Herunterfahren des Verbunds lässt das Volume unberührt – nur ein
ausdrücklicher Zusatzschalter wirft es mit weg.

### Nachsehen, ob es läuft

Unter `/healthz` antwortet die Anwendung mit ihrem Zustand und dem der
Datenbank – geeignet für eine automatische Überwachung.

### Prüfen und Ausrollen

Die Testsuite läuft im Container gegen genau den Stapel, der später auch im
Betrieb läuft: dasselbe Abbild, dasselbe PostgreSQL 17. Auf dem Rechner braucht
es dafür nichts außer Docker. 339 Testfunktionen decken die Werkzeuge, den
OAuth-Ablauf, die Datenbankregeln und die Seiten ab; hinzu kommen Browsertests
gegen einen echten Chromium. Ein Lauf prüft außerdem, ob Datenmodell und
Migrationen auseinandergelaufen sind.

Bei jeder Änderung an der Hauptlinie läuft dieselbe Suite in GitHub Actions.
Erst danach – und nur bei grünem Ergebnis – wird das Abbild gebaut, in die
Registry geladen und auf dem Betriebsserver ausgerollt. Die Reihenfolge ist der
Punkt.

---

## 10. Grenzen und Annahmen

Damit niemand etwas erwartet, was das Programm nicht leistet:

- **Kein Lernstand, keine Auswertung.** Es gibt keinerlei Rückmeldung darüber,
  wer was wie oft geübt hat. Wer eine Bewertung braucht, braucht ein anderes
  Werkzeug.
- **Die Adresse ist der einzige Schutz.** Ein Link, der weitergegeben wird, ist
  offen. Für Prüfungsinhalte, die niemand vorher sehen darf, ist die Anwendung
  nicht gedacht.
- **Ein Passwort für alle Pflegenden.** Es gibt keine Benutzerverwaltung – wer
  das Betreiberpasswort kennt, kann sämtliche Inhalte pflegen.
- **Nur Text.** Karten tragen Markdown, keine Bilder, Audiodateien oder
  Anhänge. Die Sicherheitsrichtlinie verbietet Bildquellen ausdrücklich.
- **Zwei bis vier Antwortmöglichkeiten je Frage**, genau eine richtig.
  Mehrfachauswahl, Lückentexte oder Zuordnungsaufgaben gibt es nicht.
- **Nichts wird gelöscht.** Wer Inhalte wirklich entfernen muss, kommt an die
  Datenbank – über die Anwendung geht es nicht.

Die Anwendung setzt voraus, dass ein KI-Agent mit MCP-Unterstützung vorhanden
ist. Ohne ihn lassen sich keine Inhalte anlegen; die bereits veröffentlichten
Lernseiten laufen davon unberührt weiter.
