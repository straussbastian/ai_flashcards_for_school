<div align="center">

<img src="docs/bilder/lernseite.svg" alt="Eine Lernseite: links ein gelber Zettel mit einer Karteikartenfrage, rechts eine Multiple-Choice-Frage mit hervorgehobener richtiger Antwort" width="820">

# Flashcards für die Berufsschule

**Karteikarten und Quizfragen als Lernseite im Netz.**
Die Lehrkraft gibt ihrem KI-Agenten ein Arbeitsblatt und bekommt einen Link
zurück. Die Klasse öffnet ihn und legt los – ohne Konto, ohne App,
ohne dass irgendwo ein Ergebnis gespeichert wird.

[![Tests](https://github.com/straussbastian/ai_flashcards_for_school/actions/workflows/tests.yml/badge.svg)](https://github.com/straussbastian/ai_flashcards_for_school/actions/workflows/tests.yml)

**Deutsch** · [English](README.md)

</div>

---

## Wie das im Alltag aussieht

Die Lehrkraft sagt ihrem Agenten:

> „Bau mir aus diesem Arbeitsblatt ein Lernpaket."

Der Agent legt es an und antwortet mit einer Adresse aus drei Wörtern:

```
https://karten.deine-schule.de/blaue-katze-springt
```

Dieser Link geht an die Klasse – im Klassenchat, als QR-Code an der Wand,
auf dem Arbeitsblatt. Wer ihn öffnet, sieht einen Startknopf und danach
eine Karte nach der anderen: Zettel werden zum Umdrehen angeklickt,
Quizfragen mit A/B/C/D beantwortet, mit Maus oder Tastatur. Falsch
beantwortet heißt: Die richtige Antwort wird gleich mitgezeigt. Am Ende
steht das Ergebnis, und ein Knopf setzt alles auf null.

## Was die Lernseiten bewusst nicht tun

| | |
|---|---|
| **Keine Anmeldung** | Wer den Link hat, kann lernen. Kein Konto, kein Passwort, keine Klassenliste. |
| **Keine Ergebnisse** | Die Punktzahl steht am Ende auf dem Bildschirm und ist danach fort. Sie wird nirgends gespeichert und nirgends übermittelt. |
| **Keine Cookies, keine Zählpixel** | Der Zwischenstand lebt im Browser, solange der Durchgang läuft. |
| **Keine Verwaltungsoberfläche** | Es gibt keinen Adminbereich, in den sich jemand einloggen könnte – Inhalte kommen ausschließlich über den KI-Agenten herein. |
| **Kein endgültiges Löschen** | Ein Lernpaket lässt sich unsichtbar schalten, aber nicht versehentlich wegwerfen. |

## Zum Nachlesen

| Dokument | Worum es geht |
|---|---|
| **[Technische Beschreibung](https://straussbastian.github.io/ai_flashcards_for_school/technische-beschreibung.html)** | Zweck, Aufbau, Bedienung, Sicherheit, Betrieb und Grenzen auf einer Seite – ohne eine Zeile Programmcode. Für Kolleginnen und Kollegen, Schulleitung und Datenschutz. Im Repository daneben als [Markdown](docs/technische-beschreibung.md). |
| **[Architekturdiagramm](https://straussbastian.github.io/ai_flashcards_for_school/architektur.html)** | Die Anlage als anklickbares Schaubild: welcher Weg wohin führt und was alles hinter dem einen veröffentlichten Port liegt |
| [docs/betrieb-server.md](docs/betrieb-server.md) | Betrieb auf einem eigenen Server, Schritt für Schritt |
| [docs/praxistest-cowork.md](docs/praxistest-cowork.md) | Den MCP-Server mit Claude Cowork verbinden |

Die beiden ersten Seiten liegen als GitHub Pages im Netz und öffnen sich mit
einem Klick. Dieselben Dateien stehen im Repository unter `docs/` – nach dem
Klonen genügt dort ein Doppelklick.

## Selbst betreiben – welcher Weg ist meiner?

| Ich möchte … | Weg | Aufwand |
|---|---|---|
| es mir nur einmal ansehen | [Auf dem eigenen Rechner](#auf-dem-eigenen-rechner-ansehen) | 5 Minuten, Docker genügt |
| es mit meinen Klassen benutzen | **[Auf einem eigenen Server](docs/betrieb-server.md)** | einmalig ~30 Minuten, ab 4 € im Monat |
| daran mitarbeiten | [Für Entwicklerinnen und Entwickler](#für-entwicklerinnen-und-entwickler) | Docker, sonst nichts |

### Auf dem eigenen Rechner ansehen

Gebraucht wird nur Docker – kein Python, kein PostgreSQL, nichts sonst.

```bash
git clone https://github.com/straussbastian/ai_flashcards_for_school.git
cd ai_flashcards_for_school
cp .env.example .env       # Werte eintragen, siehe Kommentare darin
docker compose up -d --build
```

`compose.yml` veröffentlicht mit Absicht keinen Port: Die Anwendung ist nur
aus dem Docker-Netz erreichbar, genau wie später auf dem Server hinter dem
Rückwärtsproxy. Für einen Blick in den Browser braucht es deshalb einmalig
eine Ergänzung daneben – Docker Compose liest sie von selbst mit, und die
`.gitignore` hält sie aus dem Repository heraus:

```bash
cat > compose.override.yml <<'ENDE'
services:
  app:
    ports:
      # 127.0.0.1: nur vom Rechner selbst erreichbar, nach aussen nur
      # ueber einen ausdruecklich gestarteten Tunnel.
      - "127.0.0.1:8000:8000"
ENDE

docker compose up -d
```

Dann steht die Anwendung auf `http://localhost:8000`. Prüfen:

```bash
curl -s http://localhost:8000/healthz
# {"status":"ok","datenbank":"ok"}
```

Logs mitlesen mit `docker compose logs -f`, beenden mit
`docker compose down`. Beim nächsten Start ist alles wieder da – außer man
hängt ein `-v` an, siehe unten.

### Auf einem eigenen Server

Die vollständige Anleitung steht in **[docs/betrieb-server.md](docs/betrieb-server.md)**.
Kurz gefasst läuft sie darauf hinaus:

```bash
curl -O https://raw.githubusercontent.com/straussbastian/ai_flashcards_for_school/main/compose.server.yml
# eine .env mit vier Werten daneben legen
docker compose -f compose.server.yml up -d
```

`compose.server.yml` zieht das fertige Abbild aus der GitHub-Registry,
startet PostgreSQL daneben und stellt einen Caddy davor, der sich sein
Zertifikat bei Let's Encrypt selbst besorgt. Auf dem Server wird nichts
gebaut und nichts eingerichtet; das Repository muss dort nicht einmal
liegen.

## Inhalte pflegen

Es gibt bewusst **keine Administrationsoberfläche**. Die Lernseiten werden
ausschließlich über den MCP-Server unter `POST /mcp` gepflegt, den ein
KI-Agent bedient – abgesichert mit OAuth 2.1 und dem `TEACHER_PASSWORD`.

| Werkzeug | Wofür |
|---|---|
| `bundle_anlegen` | Ein neues Lernpaket samt Karten in einem Aufruf |
| `bundle_liste` | Was gibt es? Standardmäßig nur die aktiven; `nur_aktive=false` zeigt auch die stillgelegten |
| `bundle_anzeigen` | Ein Paket mit allen Karten |
| `bundle_aendern` | Titel, Beschreibung, Gruppe – der Link bleibt derselbe |
| `karten_hinzufuegen` | Weitere Karten an ein bestehendes Paket |
| `karte_aendern` | Eine einzelne Karte berichtigen |
| `karte_loeschen` | Eine einzelne Karte entfernen |
| `bundle_deaktivieren` | Das Paket unsichtbar schalten, ohne etwas wegzuwerfen |

Eine Sammlung bündelt mehrere Lernpakete unter einer Adresse, damit die
Klasse **einen** Link statt vieler bekommt:

| Werkzeug | Wofür |
|---|---|
| `sammlung_anlegen` | Eine neue Sammlung unter einer eigenen Drei-Wort-Adresse |
| `sammlung_liste` | Die Sammlungen mit Adresse, Link, Titel, Gruppe und Paketzahl |
| `sammlung_anzeigen` | Eine Sammlung mit ihren Paketen, in deren Reihenfolge |
| `sammlung_aendern` | Titel, Beschreibung, Gruppe – der Link bleibt derselbe |
| `sammlung_pakete_setzen` | Die übergebene Liste **ersetzt** die bisherige vollständig, in der angegebenen Reihenfolge |
| `sammlung_deaktivieren` | Die Sammlung unsichtbar schalten; die Pakete darin bleiben einzeln erreichbar |

Endgültiges Löschen eines Pakets gibt es hier mit Absicht nicht.

Ein paar Möglichkeiten sieht man den Werkzeugnamen nicht an:

- **Stichprobe** – ein Paket fragt pro Durchlauf nur einen Teil seiner
  Karten ab, zufällig gezogen: zehn von vierzig, jedes Mal andere.
- **Reihenfolge** – die Karten kommen bei jedem Durchlauf gemischt oder
  immer in derselben Folge. Die Antworten einer Quizfrage werden ohnehin
  jedes Mal neu gemischt.
- **Selbsteinschätzung** – auf der Rückseite einer Karteikarte stehen
  „Wusste ich“ und „Wusste ich nicht“, und beides zählt beim Ergebnis mit.
  Abgeschaltet zählen nur die Quizfragen.
- **Einfügen an einer Stelle** – neue Karten wandern wahlweise ans Ende oder
  mitten hinein.
- **Gruppen** – „WBA3“ oder „Englisch“, eine Klasse oder ein Fach; die
  Listen lassen sich danach filtern.

Welche Angaben ein Werkzeug im Einzelnen erwartet, steht in seiner
Beschreibung im MCP-Server selbst. Der Agent liest sie mit; die Lehrkraft
muss sie nicht kennen.

Wie der Server mit Claude Cowork verbunden wird, steht in
[docs/praxistest-cowork.md](docs/praxistest-cowork.md).

## Das Wichtigste zum Sichern: das Volume

Die Lernpakete liegen im Volume **`pgdata`**, das an
`/var/lib/postgresql/data` im Dienst `db` hängt. Wer dieses Volume sichert,
hat alles; die Anwendung bringt deshalb keine eigene Backup-Funktion mit.

Zwei Befehle, die man auseinanderhalten muss:

```bash
docker compose down        # beendet den Verbund, das Volume bleibt
docker compose down -v     # beendet ihn UND wirft alle Lernpakete weg
```

Ein Weg, die Lernpakete als Datei aus dem Server zu holen, steht in
[docs/betrieb-server.md](docs/betrieb-server.md#im-betrieb).

---

## Für Entwicklerinnen und Entwickler

Der Verbund in `compose.yml` besteht aus **zwei** Diensten:

| Dienst | Was darin läuft |
|---|---|
| `app` | Lernseiten, MCP-Server und OAuth – ein einziger `uvicorn`. `/mcp` ist eine Route in `app/main.py`, kein eigener Prozess. |
| `db` | PostgreSQL 17, das offizielle Abbild, unverändert |

Die **Datenbank ist von außen nirgends erreichbar** – sie hat bewusst keinen
veröffentlichten Port, weder lokal noch auf dem Server. Die Anwendung erreicht
sie im gemeinsamen Docker-Netz unter `db`.

Die Werte in der `.env` sind auf einem Entwicklungsrechner
Entwicklungspasswörter. Für den Betrieb werden sie auf dem Server gesetzt
und tauchen nirgends im Git auf.

### Tests

Die Suite läuft **im Container**, gegen genau den Stapel, der später auch im
Betrieb läuft: dasselbe Abbild (`Dockerfile`, Stufe `test` baut auf `betrieb`
auf), dasselbe PostgreSQL 17.

```bash
docker compose -f compose.test.yml up --build \
    --abort-on-container-exit --exit-code-from test
```

Auf dem Rechner wird dafür nichts gebraucht und nichts angefasst: kein
Python, kein `uv`, kein PostgreSQL, kein Chromium, keine `.env`. Der
Container bringt alles mit, prüft sich selbst und beendet sich mit dem
Rückgabewert von pytest.

Der Reihe nach passiert darin (`docker/test-start.sh`): auf die Datenbank
warten, `flashcards_test` anlegen, `alembic upgrade head`, `alembic check` –
das schlägt an, sobald Modelle und Migrationen auseinanderlaufen –, dann
`pytest`, und zuletzt `pytest -m browser` für die Browsertests gegen einen
echten Chromium.

Nur eine Auswahl, ohne den ganzen Durchlauf:

```bash
docker compose -f compose.test.yml run --rm test -k oauth -x
docker compose -f compose.test.yml run --rm test -m browser
```

### Entwicklung

Gearbeitet wird durch den Container. Nach einer Änderung am Code:

```bash
docker compose up -d --build
```

Das dauert wenige Sekunden: Die teuren Schichten (Systempakete,
Python-Abhängigkeiten) liegen im Cache, neu gebaut wird nur das Kopieren von
`app/`.

Für einen Blick in die Datenbank geht man in den Container statt an einen
Port:

```bash
docker compose exec db psql -U flashcards -d flashcards
```

Ein `uvicorn --reload` auf dem Rechner gegen diese Datenbank ist bewusst
**nicht** vorgesehen. Es bräuchte einen veröffentlichten Datenbank-Port, und
den soll es nirgends geben – auch nicht auf dem eigenen Rechner, damit die
Verhältnisse hier dieselben sind wie auf dem Server.

<details>
<summary><strong>Ältere lokale Datenbank vorhanden?</strong></summary>

Migrationen wurden zwischenzeitlich fortlaufend nummeriert (`0001` statt
eines Hash-Namens). Steht in einer bestehenden Datenbank noch
`alembic_version = 'ccc906f048c0'`, meldet `alembic upgrade head` „Can't
locate revision identified by 'ccc906f048c0'". Es gibt dafür keine
Migration – die Datenbank muss einmalig neu angelegt werden:

```bash
docker compose down -v     # wirft die Datenbank weg
docker compose up -d
```

</details>

### Was in GitHub Actions passiert

`.github/workflows/tests.yml` läuft bei jedem Push und jedem Pull Request
und hat drei Jobs:

| Job | Wann | Was |
|---|---|---|
| `tests` | immer | Derselbe Compose-Aufruf wie oben. `--exit-code-from test` macht den Rückgabewert von pytest zum Rückgabewert des Jobs: Ein roter Lauf ist ein roter Container ist ein roter Job. |
| `abbild` | nur `main`, nur nach grünem `tests` | Baut die Stufe `betrieb` und lädt sie als `ghcr.io/straussbastian/ai_flashcards_for_school:main` hoch – das Abbild, das `compose.server.yml` zieht. |
| `deploy` | nur `main`, nur nach grünem `tests` | Stößt das Deployment auf dem Betriebsserver an. |

Die Reihenfolge ist der Punkt: Erst grün, dann ausrollen. In einem Fork
lädt `abbild` in die Registry des Forks – dafür genügt das Token des Laufs –,
und `deploy` bricht mit einer Klartextmeldung über die fehlenden Secrets ab.
Die Testsuite läuft davon unbeeindruckt.

Die Wegwerfwerte für den Testlauf stehen im Klartext in `compose.test.yml`.
Sie gelten nur für den jeweiligen Lauf, die Datenbank wird danach mitsamt
Cluster weggeworfen – keine Geheimnisse.

Der erste Lauf baut das Testabbild mit kaltem Cache und lädt dabei einen
vollständigen Chromium; das dauert einige Minuten.

### Aufbau

| Datei / Verzeichnis | Inhalt |
|---|---|
| `compose.yml` | Der Entwicklungsverbund: `app` (gebaut) und `db` |
| `compose.server.yml` | Der Betriebsverbund für einen eigenen Server: `caddy`, `app` (fertiges Abbild) und `db` |
| `compose.test.yml` | Der Testlauf: `test` und `db`, beides flüchtig |
| `Dockerfile` | Zwei Stufen: `betrieb` und darauf aufbauend `test` |
| `docker/` | Die beiden Startskripte |
| `app/` | Anwendung |
| `migrations/` | Alembic |
| `tests/` | Testsuite |
| `docs/technische-beschreibung.md` | Zweck, Aufbau und Bedienung im Überblick – ohne Programmcode |
| `docs/technische-beschreibung.html` | Dieselbe Beschreibung als eigenständige Seite für den Browser |
| `docs/technische-beschreibung.html` | Dieselbe Beschreibung als gestaltete Seite für den Browser |
| `docs/architektur.html` | Architekturdiagramm, anklickbar |
| `docs/betrieb-server.md` | Betrieb auf einem eigenen Server, auch die Coolify-Variante |
| `docs/praxistest-cowork.md` | Den MCP-Server mit Claude Cowork verbinden |
| `docs/superpowers/specs/` | Design-Spec |
| `docs/design/mockups/` | Freigegebene Entwürfe – Referenz für die Optik |
| `LICENSE` | MIT |

---

## Lizenz

[MIT](LICENSE) – © 2026 Bastian Strauss, Varel · [bastianstrauss.digital](https://bastianstrauss.digital)

Benutzen, verändern, weitergeben, auch gewerblich: alles erlaubt. Die
einzige Bedingung ist, dass der Copyright-Hinweis aus der Datei `LICENSE`
in Kopien und abgeleiteten Werken stehen bleibt. Eine Schule, die dieses
Repository nimmt und auf einem eigenen Server betreibt, muss niemanden
fragen.
