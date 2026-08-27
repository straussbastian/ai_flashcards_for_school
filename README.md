# Flashcards für die Berufsschule

Lernseiten mit Karteikarten und Multiple-Choice-Fragen. Lernende erhalten
von ihrer Lehrkraft einen Link zu einer Lernseite. Keine Anmeldung nötig,
keine gespeicherten Ergebnisse. Die Lernseiten selbst werden noch nicht
bereitgestellt – dieser Teil folgt in einem späteren Plan.

Alles läuft in **einem** Container: PostgreSQL und Webserver, zusammengehalten
von `supervisord`.

## Das Wichtigste zuerst: das Volume

Die Datenbank läuft im selben Container wie die Anwendung und liegt unter
`/data/pgdata`. Es muss ein persistentes Volume auf **`/data`** gemountet sein
– in Coolify unter *Persistent Storage*, lokal erledigt das `run-local.sh`.

Ohne dieses Volume startet der Container bewusst nicht, sondern bricht mit
einer Klartextmeldung ab – lieber ein klarer Fehler als stillschweigend
verlorene Lernseiten.

Damit ist auch die Sicherung geklärt: Alles Sicherungswürdige liegt unter
`/data`; wer dieses Volume sichert, hat alles. Die Anwendung selbst bringt
deshalb keine Backup-Funktion mit.

### Die Hintertür: `ALLOW_EPHEMERAL_DATA`

`ALLOW_EPHEMERAL_DATA=1` schaltet genau diese Prüfung ab. Der Container startet
dann auch ohne Volume und schreibt die Datenbank in seine eigene, flüchtige
Schicht: **Beim nächsten Stoppen sind alle Lernseiten weg.**

Die Variable ist ausschließlich zum kurzen Ausprobieren gedacht – etwa
`docker run` ohne Volume, nur um zu sehen, ob das Image überhaupt hochkommt.
**Im Betrieb hat sie nichts zu suchen.** Wer sie einmal in Coolify setzt und
dort stehen lässt, verliert die wichtigste Schutzprüfung dieses Projekts
dauerhaft und unsichtbar: Der Container startet weiterhin, meldet sich gesund,
und der Datenverlust fällt erst beim nächsten Deployment auf. Ein einzeiliges
`WARNUNG:` im Log ist alles, was dann noch daran erinnert.

## Den Container lokal betreiben

```bash
./run-local.sh
```

Das Skript baut das Image, legt `./daten` als Volume an und startet den
Container auf `http://localhost:8000`. Der erste Start dauert länger, weil das
Datenbank-Cluster angelegt wird. Prüfen:

```bash
curl -s http://localhost:8000/healthz
# {"status":"ok","datenbank":"ok"}
```

Logs mitlesen mit `docker logs -f flashcards-lokal`, stoppen mit
`docker rm -f flashcards-lokal`. Das Verzeichnis `./daten` bleibt liegen –
beim nächsten Start ist alles wieder da.

Die Passwörter in `run-local.sh` sind Entwicklungspasswörter und stehen
absichtlich im Klartext. Für den Betrieb werden die Werte in Coolify gesetzt.

## Entwicklung

Für die Arbeit am Code läuft die Datenbank außerhalb des Containers, über
`compose.dev.yml` auf Port 55432:

```bash
uv sync
docker compose -f compose.dev.yml up -d
cp .env.example .env          # DATABASE_URL auf Port 55432 umstellen
set -a; . ./.env; set +a
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

`TEST_DATABASE_URL` steht in `.env.example` bereits auf den Werten von
`compose.dev.yml` (Port 55432, Passwort `entwicklung`) und muss nicht
angefasst werden. Anzupassen ist nur `DATABASE_URL`: Der Beispielwert dort
beschreibt den Betrieb – Datenbank im selben Container, Port 5432 –, für die
Entwicklung zeigt sie auf `localhost:55432` mit dem Passwort `entwicklung`.

**Ältere lokale Datenbank vorhanden?** Migrationen wurden zwischenzeitlich
fortlaufend nummeriert (`0001` statt eines Hash-Namens). Steht in einer
bestehenden lokalen Datenbank noch `alembic_version = 'ccc906f048c0'`, meldet
`alembic upgrade head` „Can't locate revision identified by
'ccc906f048c0'“. Es gibt dafür keine Migration – die Datenbank muss einmalig
neu angelegt werden:

```bash
docker compose -f compose.dev.yml down -v   # wirft auch die Testdatenbank weg
docker compose -f compose.dev.yml up -d
uv run alembic upgrade head
```

Tests (die Testdatenbank wird einmalig angelegt):

```bash
docker compose -f compose.dev.yml exec db createdb -U flashcards flashcards_test
set -a; . ./.env; set +a
uv run pytest
```

Die Container-Tests bauen das Image und brauchen ein laufendes Docker. Ohne
Docker werden sie übersprungen.

## Tests in GitHub Actions

Bei jedem Push und jedem Pull Request läuft `.github/workflows/tests.yml`:
Datenbank aus derselben `compose.dev.yml` hochfahren, warten bis PostgreSQL
über TCP antwortet, Testdatenbank anlegen, `alembic upgrade head`, dann
`alembic check` – das schlägt an, sobald Modelle und Migrationen
auseinanderlaufen – und zuletzt `uv run pytest -v`.

Auf dem Runner gibt es keine `.env`. Die Umgebungsvariablen stehen im
Workflow, damit die **vollständige** Suite läuft und nichts übersprungen wird.
Es sind erkennbare Wegwerfwerte für die Wegwerfdatenbank des Runners und
absichtlich im Klartext – keine Geheimnisse. Die echten Werte für den Betrieb
werden in Coolify gesetzt.

Die Container-Tests bauen das Image mit kaltem Cache; der Lauf dauert deshalb
einige Minuten. Ob er durchgelaufen ist, steht unter *Actions* im Repository
sowie als Häkchen neben dem Commit und bei den Checks eines Pull Requests.

## Betrieb auf Coolify

Coolify zieht sich das Repository selbst per CI/CD. Einzurichten ist dort:

1. Neue Anwendung aus diesem Git-Repository, Build über das `Dockerfile`
2. **Persistent Storage: Volume auf `/data`** – ohne das startet der Container nicht
3. Umgebungsvariablen aus `.env.example` setzen; `DATABASE_URL` zeigt auf
   `localhost:5432` **im** Container, das Passwort darin muss zu
   `POSTGRES_PASSWORD` passen, `BASE_URL` auf die echte Domain
4. Domain zuweisen, HTTPS aktivieren
5. Healthcheck auf `/healthz`
6. **Stop-Grace-Period großzügig setzen** (mindestens 60 Sekunden). PostgreSQL
   bekommt beim Herunterfahren bewusst Zeit für einen sauberen Checkpoint
   (`stopwaitsecs=30` in `docker/supervisord.conf`). Ist die Grace-Period zu
   knapp, wird es abgeschossen und fährt beim nächsten Start per
   Crash-Recovery hoch – langsamer und ohne Not riskant.

## Inhalte pflegen

Es gibt bewusst **keine Administrationsoberfläche**. Die Lernseiten werden
später ausschließlich über einen MCP-Server gepflegt, den ein KI-Agent
bedient. Dieser Teil ist noch nicht gebaut.

## Aufbau

| Verzeichnis | Inhalt |
|---|---|
| `app/` | Anwendung |
| `migrations/` | Alembic |
| `docker/` | Startskripte und Prozessverwaltung |
| `tests/` | Testsuite |
| `docs/superpowers/specs/` | Design-Spec |
| `docs/design/mockups/` | Freigegebene Entwürfe – Referenz für die Optik |
