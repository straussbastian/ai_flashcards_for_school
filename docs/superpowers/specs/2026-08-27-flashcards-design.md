# Flashcards für die Berufsschule – Design

Stand: 2026-08-27
Repo: `straussbastian/ai_flashcards_for_school`
Grundlage: [idee.md](../../../idee.md), ausgearbeitet im Brainstorming vom 27.08.2026

## 1. Ziel

Eine öffentlich erreichbare Lernseite, auf der Schülerinnen und Schüler einer Berufsschule Karteikarten durchgehen und Multiple-Choice-Fragen beantworten. Jedes Lernpaket („Bundle") hat eine eigene Adresse aus drei deutschen Wörtern, zum Beispiel `rote-katze-springt`. Wer den Link kennt, kann sofort loslegen – keine Anmeldung, keine Konten.

Gepflegt werden die Inhalte ausschließlich über einen MCP-Server. Die Lehrerin arbeitet mit Claude Cowork, lässt ihren Agenten aus einem Arbeitsblatt ein Bundle bauen und bekommt den fertigen Link zurück. Es gibt bewusst **kein Administrationsoberfläche**.

Betrieb: ein Docker-Container auf einem Coolify-Server.

### Nutzer

- **Die Lehrerin** – nicht IT-affin, aber KI-erfahren. Ihre einzige Bedienoberfläche ist ihr Agent. Sie fasst weder Terminal noch Logs noch `.env` an.
- **Die Lernenden** – Berufsschule, also junge Erwachsene, häufig am eigenen Handy. Sie erhalten nur einen Link.

### Ausdrücklich nicht Teil dieses Projekts

- Keine Benutzerkonten, keine Anmeldung für Lernende
- Kein Speichern von Ergebnissen, keine Cookies, kein LocalStorage
- Keine Auswertung oder Statistik für die Lehrerin
- Keine Bilder, keine LaTeX-Formeln auf Karten
- Kein Admin-Frontend

## 2. Getroffene Entscheidungen

| Thema | Entscheidung |
|---|---|
| Stack | Python 3.13, FastAPI, ein Prozess für Web, MCP und OAuth |
| Container | Alles in einem Container: Postgres und App unter `supervisord` |
| Ergebnisse | Nur im Browser, nichts wird gespeichert |
| Flashcard-Bewertung | Flag pro Bundle (`selbsteinschaetzung`) |
| Drei-Wort-URL | Server würfelt aus gepflegten deutschen Wortlisten |
| Karteninhalt | Text mit einfachem Markdown |
| Optik | Dunkle Tafel, gelbe Post-its mit Stapel, klare Systemschrift |
| Auflösung | Karte dreht um und zeigt Verdikt, Lösung und Erklärung |
| Ergebnisseite | Punktzahl, Fehlerliste und ein Durchlauf nur mit den Fehlern |
| Mobile Navigation | Sichtbare Zurück/Weiter-Balken, kein Wischen |
| Frontend-Logik | Bundle als JSON, Runner im Browser, kein Build-Schritt |
| MCP-Auth | OAuth 2.1 mit Dynamic Client Registration |
| MCP-Transport | Nur Streamable HTTP über HTTPS. Kein stdio. |
| Reihenfolge | Karten und Antworten werden bei jedem Start gemischt |

## 3. Architektur und Betrieb

### Ein Container, zwei Prozesse

Basis ist Debian mit Python 3.13 und PostgreSQL 17. `supervisord` verwaltet beide Prozesse und startet einen abgestürzten Dienst neu.

Startreihenfolge: Postgres hochfahren → auf Bereitschaft warten → Alembic-Migrationen → Uvicorn.

### Persistenz

`PGDATA` liegt auf `/data/pgdata`. `/data` **muss** in Coolify als persistentes Volume gemountet sein.

Der Container prüft das beim Start: Ist `/data` kein Mountpoint, bricht er mit einer Klartextmeldung ab, statt still eine leere Datenbank anzulegen. Das ist die kritische Stelle der Ein-Container-Variante und gehört an den Anfang der README.

### Backups

**Nicht Teil dieser Anwendung.** Sicherungen übernimmt Coolify auf Ebene des Volumes. Im Container läuft dafür kein eigener Prozess und liegt kein eigenes Skript — die Anwendung kümmert sich um Lernkarten, nicht um Betriebsführung.

Zu wissen ist nur: Alles, was gesichert werden muss, liegt unter `/data`. Wer das Volume sichert, hat alles.

### Routen

| Pfad | Zweck |
|---|---|
| `GET /{slug}` | Lernseite, serverseitig gerendert, Bundle als JSON eingebettet |
| `GET /` | Schlichte Landeseite ohne Bundle-Liste (Bundles sind nicht öffentlich auffindbar) |
| `POST /mcp` | MCP-Server, Streamable HTTP |
| `GET /.well-known/oauth-protected-resource` | OAuth-Discovery |
| `GET /.well-known/oauth-authorization-server` | OAuth-Discovery |
| `POST /oauth/register` | Dynamic Client Registration |
| `GET/POST /oauth/authorize` | Login- und Zustimmungsseite |
| `POST /oauth/token` | Token-Ausgabe und Refresh |
| `GET /healthz` | Healthcheck inklusive Datenbankverbindung |
| `GET /static/*` | CSS, JS, Schriften |

### Konfiguration

Alles über `.env`, im Repo liegt `.env.example`. Keine Geheimnisse im Image, keine im Git.

| Variable | Bedeutung |
|---|---|
| `POSTGRES_PASSWORD` | Passwort der lokalen Datenbank |
| `DATABASE_URL` | Verbindung, zeigt auf localhost im selben Container |
| `APP_SECRET` | Signaturschlüssel für OAuth-Tokens |
| `TEACHER_PASSWORD` | Das eine Passwort für die OAuth-Zustimmungsseite |
| `BASE_URL` | Öffentliche Basis-URL, z. B. `https://karten.example.de` – wird für erzeugte Links und OAuth-Metadaten gebraucht |
| `TZ` | Zeitzone, Standard `Europe/Berlin` |

### Bibliotheken

FastAPI, SQLAlchemy 2, Alembic, psycopg 3, Jinja2, das offizielle `mcp`-SDK, `markdown-it-py` zum Rendern, `nh3` zum Säubern, `pytest`, `pytest-asyncio`, `playwright`.

## 4. Datenmodell

### `bundles`

| Spalte | Typ | Anmerkung |
|---|---|---|
| `id` | uuid, PK | |
| `slug` | text, unique, not null | die drei Wörter, bindestrichgetrennt |
| `titel` | text, not null | |
| `beschreibung` | text | Markdown, optional |
| `klasse` | text | optional, z. B. „FS 23b" |
| `selbsteinschaetzung` | bool, default true | zählen Flashcards beim Ergebnis mit |
| `reihenfolge` | text, default `zufall` | `zufall` oder `fest` |
| `aktiv` | bool, default true | |
| `erstellt_am`, `geaendert_am` | timestamptz | |

### `karten`

| Spalte | Typ | Anmerkung |
|---|---|---|
| `id` | uuid, PK | |
| `bundle_id` | uuid, FK → bundles, on delete cascade | |
| `position` | int, not null | Reihenfolge bei `reihenfolge = fest`, sonst nur zum Bearbeiten |
| `art` | text, not null | `flashcard` oder `frage` |
| `vorderseite` | text, not null | Markdown. Bei `frage` die Frage |
| `rueckseite` | text | Markdown, nur bei `flashcard` |
| `antworten` | jsonb | nur bei `frage`: Textliste `["Split", "Zagreb", …]`, zwei bis vier Einträge |
| `richtige_index` | int | nur bei `frage`: Position der richtigen Antwort in `antworten`, nullbasiert |
| `erklaerung` | text | optional, Markdown, wird auf der Rückseite gezeigt |
| `erstellt_am`, `geaendert_am` | timestamptz | |

`(bundle_id, position)` ist eindeutig.

### Constraints in der Datenbank

Falsche Daten dürfen gar nicht erst hineinkommen – nicht nur die Anwendung prüft:

- `art = 'flashcard'` → `rueckseite` gesetzt, `antworten`, `richtige_index`, `erklaerung` leer
- `art = 'frage'` → `antworten` und `richtige_index` gesetzt, `rueckseite` leer
- `antworten` ist ein JSON-Array mit zwei bis vier Einträgen
- `richtige_index` liegt zwischen 0 und `länge(antworten) - 1`
- `reihenfolge` in (`zufall`, `fest`)

**Warum ein Index und kein Buchstabe:** Die Antwortreihenfolge wird bei jedem Durchlauf neu gemischt. Die Buchstaben A–D vergibt erst der Browser nach dem Mischen – ein in der Datenbank gespeicherter Buchstabe wäre nach dem ersten Mischen falsch. Gespeichert wird deshalb die Position, angezeigt wird der Buchstabe.

### Slug-Erzeugung

Drei gepflegte deutsche Wortlisten (Adjektiv, Nomen, Verb), jeweils **mindestens 30 Einträge**, im Repo als Textdatei. 30 × 30 × 30 ergibt 27.000 Adressen – für eine Schule reichlich und nicht durchprobierbar. Wer erweitert, hält sich an dieselbe Regel; der Test `test_alle_woerter_sind_url_tauglich` erzwingt sie. Kleinbuchstaben, keine Umlaute in der URL, keine anstößigen oder verwechselbaren Wörter. Bei Kollision wird neu gezogen, maximal zehn Versuche, danach ein Fehler mit Klartextmeldung.

## 5. MCP-Server

### Transport und Absicherung

Streamable HTTP unter `POST /mcp`, ausschließlich über HTTPS. Kein stdio – Cowork verbindet aus Anthropics Cloud (Quellbereich `160.79.104.0/21`), nicht vom Rechner der Lehrerin.

### OAuth 2.1 mit Dynamic Client Registration

Ein Ein-Personen-Login, kein Benutzersystem:

1. `/mcp` antwortet ohne gültiges Token mit `401` und `WWW-Authenticate: Bearer resource_metadata="…"`. Das ist der Auslöser des gesamten Ablaufs.
2. Claude liest die Protected-Resource-Metadaten. `resource` muss **exakt** der URL entsprechen, die die Lehrerin eingetragen hat, inklusive Pfad.
3. Claude registriert sich selbst über `/oauth/register` (RFC 7591).
4. `/oauth/authorize` zeigt eine schlichte Seite: „Möchtest du Claude Zugriff auf deine Lernseiten geben?" plus Passwortfeld. Geprüft wird gegen `TEACHER_PASSWORD`.
5. `/oauth/token` gibt einen Access-Token (eine Stunde) und einen Refresh-Token aus. Body ist `application/x-www-form-urlencoded`.
6. Refresh-Tokens rotieren; der alte wird beim Ausgeben des neuen ungültig.

Weitere Pflichten:

- PKCE mit `S256` ist Pflicht, `code_challenge_methods_supported: ["S256"]` steht in den Metadaten
- Erlaubte Redirect-URIs: `https://claude.ai/api/mcp/auth_callback` sowie `http://localhost/callback` und `http://127.0.0.1/callback` mit **ignoriertem Port** (Claude Code)
- Abgelaufene oder zurückgezogene Refresh-Tokens werden mit `invalid_grant` beantwortet, nicht mit einem eigenen Fehlercode
- Alle OAuth-Endpunkte antworten deutlich unter zehn Sekunden
- Registrierte Clients und ausgegebene Tokens liegen in Postgres und überstehen Deployments

### Werkzeuge

Grob geschnitten: ein Aufruf soll aus einem Arbeitsblatt ein fertiges Bundle machen. Beschreibungen und Fehlermeldungen sind auf Deutsch und im Klartext formuliert, weil der Agent sie der Lehrerin vorliest. Jede schreibende Antwort enthält den fertigen Link.

| Werkzeug | Eingabe | Ergebnis |
|---|---|---|
| `bundle_anlegen` | `titel`, `beschreibung?`, `klasse?`, `selbsteinschaetzung?`, `karten[]` | Slug, vollständige URL, Anzahl angelegter Karten |
| `bundle_liste` | `klasse?`, `nur_aktive?` | Liste mit Slug, URL, Titel, Klasse, Kartenzahl, aktiv |
| `bundle_anzeigen` | `slug` | Bundle mit allen Karten samt IDs und Positionen |
| `bundle_aendern` | `slug`, optional `titel`, `beschreibung`, `klasse`, `selbsteinschaetzung`, `reihenfolge` | aktualisiertes Bundle |
| `karten_hinzufuegen` | `slug`, `karten[]` | neue Karten mit IDs, neue Gesamtzahl |
| `karte_aendern` | `karte_id`, zu ändernde Felder | aktualisierte Karte |
| `karte_loeschen` | `karte_id` | Bestätigung, verbleibende Kartenzahl |
| `bundle_deaktivieren` | `slug`, `aktiv` (bool) | neuer Zustand |

Eine Karte im Eingabeformat:

```json
{
  "art": "frage",
  "vorderseite": "Was ist die Hauptstadt von Kroatien?",
  "antworten": ["Split", "Zagreb", "Dubrovnik", "Rijeka"],
  "richtige_antwort": "Zagreb",
  "erklaerung": "Zagreb liegt im Landesinneren, Split und Dubrovnik an der Küste."
}
```

Der Agent gibt die richtige Antwort als **Text** an, nicht als Buchstaben. Der Server sucht den Text in `antworten` und speichert dessen Position als `richtige_index`. Das verhindert die häufigste Fehlerquelle, nämlich verrutschte Zuordnungen. Passt der Text auf keine Antwortmöglichkeit, kommt eine Klartextmeldung zurück; kommt er mehrfach vor, ebenfalls.

Für Flashcards entsprechend `"art": "flashcard"` mit `vorderseite` und `rueckseite`.

**In der Werkzeugbeschreibung ausdrücklich vermerkt:** Antwortmöglichkeiten wie „keine der genannten" oder „A und B sind richtig" nicht verwenden, weil die Reihenfolge bei jedem Durchlauf gemischt wird.

**Kein endgültiges Löschen über MCP.** `bundle_deaktivieren` setzt `aktiv = false`; die Seite zeigt dann einen freundlichen Hinweis. Ein Versehen ist damit ein Handgriff, kein Datenverlust.

### Fehlermeldungen

Deutsch, konkret, mit Handlungsanweisung. Beispiele:

- „Die Karte auf Position 3 hat keine richtige Antwort. Bitte gib den Text einer der Antwortmöglichkeiten an."
- „Ein Bundle mit dem Slug `rote-katze-springt` gibt es nicht. Mit `bundle_liste` siehst du alle vorhandenen."
- „Eine Frage braucht zwei bis vier Antwortmöglichkeiten, diese hat sechs."

## 6. Frontend

### Auslieferung

`GET /{slug}` liefert eine serverseitig gerenderte Seite. Das komplette Bundle steckt als JSON im Dokument – Markdown ist zu diesem Zeitpunkt bereits zu gesäubertem HTML gerendert. Der Browser bekommt also fertiges HTML und braucht keinen Markdown-Parser.

Nach dem ersten Aufruf gibt es keine weiteren Serveranfragen. Das erzwingt technisch, was versprochen wurde: Es kann nichts gespeichert werden.

### Zustände des Runners

1. **Start** – Klasse als Chip, Titel, Beschreibung, Zusammensetzung („20 Karten · 10 zum Lernen · 10 Fragen", vom Server gezählt), Start-Button
2. **Karte** – oben „Frage 7 von 20" mit Fortschrittsbalken und Beenden, in der Mitte die Karte, unten Zurück/Weiter
3. **Ergebnis** – große Punktzahl, Aufschlüsselung Fragen/Karten, Liste der falsch beantworteten Fragen mit richtiger Lösung, Buttons „Nochmal starten" und „Nur die Fehler"
4. **Fehlerwiederholung** – derselbe Ablauf, nur mit den Karten, die im Durchlauf danebengingen: falsch beantwortete Fragen und – falls `selbsteinschaetzung` aktiv ist – Flashcards, die mit „Wusste ich nicht" bewertet wurden. Auch hier wird neu gemischt. Das Ergebnis dieses Durchlaufs ersetzt das vorherige nicht, sondern wird eigenständig gezeigt.

Beim Start und bei jedem Neustart werden **Karten und Antwortreihenfolge frisch gemischt** (Fisher-Yates). Bei `reihenfolge = fest` bleibt die Kartenreihenfolge, die Antworten werden trotzdem gemischt.

### Interaktion

**Flashcard:** Klick oder Leertaste dreht die Karte. Ist `selbsteinschaetzung` aktiv, erscheinen auf der Rückseite „Wusste ich" und „Wusste ich nicht"; das Ergebnis zählt mit. Sonst nur „Weiter".

**Frage:** Die Buchstaben A–D werden **nach** dem Mischen vergeben, also der Reihe nach von oben. Auswahl per Klick oder Taste A–D. Die Karte dreht sich und zeigt „Richtig!" oder „Leider falsch", darunter die eigene Antwort, die richtige Lösung und – falls vorhanden – die Erklärung.

**Steuerung.** Am Handy zwei breite Balken unten, kein Wischen. Bereits beantwortete Karten behalten beim Zurückblättern ihr Ergebnis; eine Antwort kann nicht nachträglich geändert werden.

Am Rechner ist **jedes** Bedienelement mit der Tastatur erreichbar — es gibt keine Stelle, an der man zur Maus greifen muss. Dahinter steht eine einzige Regel: **Wo zwei Möglichkeiten zur Wahl stehen, sind es immer A und B.** Dieselbe Geste wie bei den Antworten, damit man sich nur eine Sache merken muss.

| Wo | Taste |
|---|---|
| Startseite | Eingabetaste startet |
| Flashcard, Vorderseite | Leertaste dreht um |
| Flashcard, Rückseite | `A` wusste ich · `B` wusste ich nicht |
| Quizfrage | `A`–`D`, alternativ `1`–`4` |
| Ergebnis | `A` nochmal starten · `B` nur die Fehler |
| Überall | `←` `→` blättern · `Esc` beenden |

Zwei Dinge gehören dazu, sonst trägt die Regel nicht:

**Die Kürzel stehen sichtbar auf den Knöpfen.** Ein Kürzel, das man nicht sieht, benutzt niemand.

**Die Tastenleiste zeigt nur, was gerade wirklich geht.** Sie wechselt mit dem Zustand — auf der Kartenvorderseite „Leertaste umdrehen", nach dem Umdrehen „A wusste ich · B wusste ich nicht", bei einer beantworteten Frage nur noch „← → blättern". Eine Leiste, die Tasten nennt, die gerade nichts tun, erzieht dazu, sie nicht mehr zu lesen.

Der Tastaturfokus darf nie verloren gehen. Nach dem Beantworten verschwindet der angeklickte Knopf mit der Drehung; der Fokus wandert deshalb auf die Karte, sonst begänne Tab wieder ganz vorn.

### Optik

Aus den freigegebenen Mockups, damit die Umsetzung nicht davon abweicht:

| Element | Wert |
|---|---|
| Hintergrund | `radial-gradient(120% 90% at 50% 0%, #2a3138 0%, #16191d 70%)` |
| Raster darüber | Linien `rgba(255,255,255,.028)`, Abstand 22 px |
| Post-it Vorderseite | `linear-gradient(158deg, #ffe57a 0%, #ffd23f 100%)` |
| Post-it Rückseite | `linear-gradient(158deg, #ffdf6b 0%, #f7c62f 100%)` |
| Text auf der Karte | `#2b2410` |
| Stapel dahinter | `#e9bf3a` (−2,2° / −7 px, +7 px) und `#f0cd52` (+1,2° / +4 px, +3 px) |
| Schatten der Karte | `0 18px 32px rgba(0,0,0,.55)` |
| Richtig | `#2f9e52`, Rand `#257e41` |
| Falsch | `#d1392f`, Rand `#a72d25` |
| Fortschrittsbalken | Spur `#2c343c`, Füllung `#ffd23f` |
| Umklappen | `transform: rotateY(180deg)`, `.55s cubic-bezier(.2,.7,.3,1)` |
| Schrift | `system-ui`, keine Webfont-Abhängigkeit |

### Wie wir Abweichung vom Mockup verhindern

Erfahrungsgemäß sieht das fertige Ergebnis oft ganz anders aus als der Entwurf, weil Mockups weggeworfen werden und die Umsetzung aus dem Gedächtnis entsteht. Dagegen drei feste Regeln:

0. **Es gibt einen bedienbaren Prototypen**, `docs/design/prototyp.html`. Er enthält den kompletten Ablauf mit fest eingebauten Beispielkarten — Umklappen, Mischen, Selbsteinschätzung, Tastaturbedienung, Ergebnis mit Fehlerliste und Fehler-Wiederholung. Er ist vom Auftraggeber am Handy und am Rechner durchgespielt und abgenommen. **Er ist die verbindliche Referenz für Plan 3**, nicht nur eine Anschauung: Wo die echte Umsetzung sich anders verhält, ist die echte Umsetzung falsch — es sei denn, jemand entscheidet ausdrücklich anders.
1. **Die freigegebenen Mockups liegen im Repo**, unter `docs/design/mockups/`. Sie sind Referenz, nicht Dekoration. (Sie enthalten ihr CSS inline; die Klassen `.cards` und `.options` stammen aus dem Brainstorming-Rahmen und fehlen beim direkten Öffnen – die Karten selbst rendern korrekt.)
2. **Die Werte aus der Tabelle oben werden wörtlich übernommen**, als CSS-Custom-Properties in einer einzigen Datei `static/css/tokens.css`. Keine „ungefähr dieses Gelb"-Entscheidungen im Verlauf der Umsetzung. Jede Abweichung ist damit eine sichtbare Änderung an einer Datei, nicht ein schleichendes Abdriften.
3. **Playwright macht Screenshots** der fertigen Seiten in den drei Viewports (390 px, 820 px, 1440 px). Die werden vor der Abnahme neben die Mockups gelegt und angeschaut. Erst dann gilt die Optik als umgesetzt.

### Responsiv

Ein Layout, drei Ausprägungen – keine getrennte Mobilseite.

- **Handy hochkant:** Karte füllt die Breite, Antwortflächen mindestens 44 px hoch, Navigation als zwei breite Balken unten
- **Tablet:** identisch, mehr Weißraum, hoch wie quer nutzbar
- **Rechner:** Karte zentriert und in der Breite begrenzt, darunter die Tastaturleiste

Lange Fragen scrollen innerhalb der Karte, die Seite selbst scrollt nie waagerecht.

### Barrierefreiheit

- Ergebnis „richtig"/„falsch" wird über `aria-live` angesagt
- Fokus wandert beim Kartenwechsel auf die neue Karte
- Antwortmöglichkeiten sind echte Buttons, mit Tab erreichbar
- Bei `prefers-reduced-motion: reduce` entfällt die Drehung, die Rückseite erscheint direkt

## 7. Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| Slug existiert nicht | 404 mit freundlichem Text, kein Hinweis auf andere Bundles |
| Bundle inaktiv | 410 mit „Diese Lernseite ist nicht mehr aktiv." |
| Bundle ohne Karten | Startseite erklärt, dass noch keine Karten hinterlegt sind, kein Start-Button |
| Datenbank weg | `/healthz` schlägt an, Lernseiten zeigen eine Wartungsmeldung |
| MCP ohne Token | `401` mit `WWW-Authenticate` – Auslöser des OAuth-Ablaufs, kein Tool-Fehler |
| MCP mit ungültigen Daten | Deutsche Klartextmeldung mit Angabe der betroffenen Karte |

## 8. Tests

**pytest**

- MCP-Werkzeuge einzeln: Anlegen, Auflisten, Ändern, Löschen, Deaktivieren
- Datenbank-Constraints: kaputte Karten lassen sich nicht speichern
- Zuordnung `richtige_antwort` als Text → `richtige_index`, inklusive der Fehlerfälle „Text kommt nicht vor" und „Text kommt mehrfach vor"
- Slug-Erzeugung inklusive Kollision
- OAuth vollständig: 401-Handshake, Discovery, Registrierung, Autorisierung mit richtigem und falschem Passwort, Token, Refresh mit Rotation, abgelaufener Token
- Markdown-Rendering: erlaubtes Markdown kommt durch, eingeschleuste Skripte werden entfernt
- Routen: 404, 410, leeres Bundle, `/healthz`

**Playwright**

- Flashcard umdrehen, Selbsteinschätzung zählt
- Frage richtig und falsch beantworten, Farben und Lösung stimmen
- Punktestand am Ende korrekt
- Fehlerwiederholung enthält genau die falschen Karten
- Tastaturbedienung vollständig
- Handy-Viewport: Balken bedienbar, kein waagerechtes Scrollen
- Neu laden setzt alles zurück

## 9. Betrieb

### Zuerst lokal

Entwickelt und abgenommen wird auf dem eigenen Rechner: Image bauen, Container mit einem lokalen Verzeichnis als `/data`-Volume starten, gegen `http://localhost:8000` prüfen. Erst wenn das trägt, kommt der Server dazu.

Weil Cowork MCP-Server aus Anthropics Cloud erreicht und nicht vom Rechner der Lehrkraft, ist ein lokaler Container von dort nicht erreichbar. Der OAuth-Ablauf wird deshalb lokal über Tests geprüft; für einen Praxistest mit echtem Cowork braucht es einen Tunnel (`cloudflared`) oder das Server-Deployment.

### Später auf Coolify

Coolify zieht sich das Repository eigenständig per CI/CD. Einzurichten ist dort:

1. Anwendung aus dem Git-Repo anlegen, Dockerfile-Build
2. **Persistentes Volume auf `/data`** – ohne das startet der Container bewusst nicht
3. Umgebungsvariablen aus `.env.example` setzen, `BASE_URL` auf die echte Domain
4. Domain zuweisen, HTTPS über Coolify
5. Healthcheck auf `/healthz`
6. In Cowork unter Customize → Connectors den Server als Custom Connector mit `BASE_URL/mcp` hinzufügen, „Verbinden" klicken, `TEACHER_PASSWORD` eingeben

## 10. Risiken

**OAuth ist der fehleranfälligste Teil.** Discovery, exakte `resource`-Übereinstimmung und PKCE müssen stimmen, sonst meldet Claude nur „Couldn't reach the MCP server". Deshalb wird OAuth als eigenes Implementierungspaket gebaut und vollständig getestet, bevor die Werkzeuge dazukommen.

**Der Volume-Mount** ist der einzige Weg, wie Daten verloren gehen können. Den fehlenden Mount fängt der Startcheck ab: Ohne Volume auf `/data` startet der Container gar nicht erst. Einen nächtlichen Dump bringt die Anwendung bewusst **nicht** mit – alles Sicherungswürdige liegt unter `/data`, und für Sicherungen ist die Betriebsebene zuständig (Snapshots des Volumes in Coolify bzw. auf dem Host). Das Restrisiko bleibt damit: Ein Volume, das zwar gemountet, aber nirgends gesichert wird, überlebt keinen Plattenschaden.

**Die Lösungen stehen im Seitenquelltext.** Bewusst akzeptiert: Es gibt keine Noten, die Seite dient dem Üben. Wer den Quelltext liest, betrügt sich selbst.

**Ein Container statt zwei** bedeutet, dass ein Postgres-Update ein Neubauen des Images heißt und dass `supervisord` die Prozesse überwacht statt Docker. Bewusste Entscheidung zugunsten eines einzelnen Deployment-Artefakts.
