# Flashcards für die Berufsschule

Lernseiten mit Karteikarten und Multiple-Choice-Fragen. Lernende erhalten
von ihrer Lehrkraft einen Link zu einer Lernseite. Keine Anmeldung nötig,
keine gespeicherten Ergebnisse.

Der Verbund besteht aus **zwei** Diensten, beschrieben in `compose.yml`:

| Dienst | Was darin läuft |
|---|---|
| `app` | Lernseiten, MCP-Server und OAuth – ein einziger `uvicorn`. `/mcp` ist eine Route in `app/main.py`, kein eigener Prozess. |
| `db` | PostgreSQL 17, das offizielle Abbild, unverändert |

## Das Wichtigste zuerst: das Volume

Die Lernpakete liegen im Volume **`pgdata`**, das an
`/var/lib/postgresql/data` im Dienst `db` hängt. Wer dieses Volume sichert,
hat alles; die Anwendung bringt deshalb keine eigene Backup-Funktion mit.

Zwei Befehle, die man auseinanderhalten muss:

```bash
docker compose down        # beendet den Verbund, das Volume bleibt
docker compose down -v     # beendet ihn UND wirft alle Lernpakete weg
```

In Coolify muss für dieses Volume ein persistenter Speicher eingerichtet
sein, sonst sind die Lernpakete nach dem nächsten Deployment fort.

## Lokal betreiben

```bash
cp .env.example .env       # Werte eintragen, siehe Kommentare darin
docker compose up -d --build
```

Der Verbund läuft dann auf `http://localhost:8000`. Der Dienst `app` wartet
selbst darauf, dass die Datenbank Verbindungen annimmt, spielt die
Migrationen ein und startet erst dann den Webserver. Prüfen:

```bash
curl -s http://localhost:8000/healthz
# {"status":"ok","datenbank":"ok"}
```

Logs mitlesen mit `docker compose logs -f`, beenden mit
`docker compose down`. Beim nächsten Start ist alles wieder da.

Die Werte in der `.env` sind auf einem Entwicklungsrechner
Entwicklungspasswörter. Der Container ist an `127.0.0.1` gebunden und damit
nur vom Rechner selbst erreichbar; nach außen geht es ausschließlich über
einen ausdrücklich gestarteten Tunnel. Für den Betrieb werden die Werte in
Coolify gesetzt und tauchen nirgends im Git auf.

Die **Datenbank ist von außen nirgends erreichbar** – sie hat bewusst keinen
veröffentlichten Port, weder hier noch auf dem Server. Die Anwendung erreicht
sie im gemeinsamen Docker-Netz unter `db`.

## Tests

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

## Entwicklung

Gearbeitet wird durch den Container. Nach einer Änderung am Code:

```bash
docker compose up -d --build
```

Das dauert wenige Sekunden: Die teuren Schichten (Systempakete, Python-Abhängigkeiten)
liegen im Cache, neu gebaut wird nur das Kopieren von `app/`.

Für einen Blick in die Datenbank geht man in den Container statt an einen
Port:

```bash
docker compose exec db psql -U flashcards -d flashcards
```

Ein `uvicorn --reload` auf dem Rechner gegen diese Datenbank ist bewusst
**nicht** vorgesehen. Es bräuchte einen veröffentlichten Datenbank-Port, und
den soll es nirgends geben – auch nicht auf dem eigenen Rechner, damit die
Verhältnisse hier dieselben sind wie auf dem Server.

**Ältere lokale Datenbank vorhanden?** Migrationen wurden zwischenzeitlich
fortlaufend nummeriert (`0001` statt eines Hash-Namens). Steht in einer
bestehenden Datenbank noch `alembic_version = 'ccc906f048c0'`, meldet
`alembic upgrade head` „Can't locate revision identified by
'ccc906f048c0'“. Es gibt dafür keine Migration – die Datenbank muss einmalig
neu angelegt werden:

```bash
docker compose down -v     # wirft die Datenbank weg
docker compose up -d
```

## Tests in GitHub Actions

Bei jedem Push und jedem Pull Request läuft `.github/workflows/tests.yml`.
Der Workflow besteht aus genau einem inhaltlichen Schritt – demselben
Compose-Aufruf wie oben. Auf dem Runner wird nichts eingerichtet: Was die
Tests brauchen, bringt `compose.test.yml` mit.

`--exit-code-from test` macht den Rückgabewert von pytest zum Rückgabewert
des Jobs: Ein roter Lauf ist ein roter Container ist ein roter Job.

Die Wegwerfwerte für den Testlauf stehen im Klartext in `compose.test.yml`.
Sie gelten nur für den jeweiligen Lauf, die Datenbank wird danach mitsamt
Cluster weggeworfen – keine Geheimnisse. Die echten Werte für den Betrieb
werden in Coolify gesetzt.

Der erste Lauf baut das Testabbild mit kaltem Cache und lädt dabei einen
vollständigen Chromium; das dauert einige Minuten. Ob er durchgelaufen ist,
steht unter *Actions* im Repository sowie als Häkchen neben dem Commit.

## Betrieb auf Coolify

Coolify zieht sich das Repository selbst per CI/CD. Einzurichten ist dort:

1. Neue Anwendung aus diesem Git-Repository, **Build über `compose.yml`**
   (Docker Compose, nicht das nackte `Dockerfile` – die Anwendung allein
   hat keine Datenbank)
2. **Persistentes Volume für `pgdata`** – ohne das sind die Lernpakete beim
   nächsten Deployment fort
3. Umgebungsvariablen aus `.env.example` setzen. `DATABASE_URL` zeigt auf
   `db:5432`; Benutzer, Passwort und Datenbankname darin müssen zu
   `POSTGRES_USER`, `POSTGRES_PASSWORD` und `POSTGRES_DB` passen, `BASE_URL`
   auf die echte Domain
4. Domain auf den Dienst `app` zuweisen, HTTPS aktivieren
5. Healthcheck auf `/healthz`

Zum Passwort: Das Abbild `postgres` legt die Rolle nur beim **Erststart** an.
Ein später geändertes `POSTGRES_PASSWORD` lässt eine bestehende Rolle
unberührt – die Anwendung käme dann nicht mehr an ihre Datenbank. Wer das
Passwort wechselt, muss es zusätzlich in der Datenbank selbst ändern:

```bash
docker compose exec db psql -U flashcards -c \
    "alter role flashcards password 'neues-passwort'"
```

## Inhalte pflegen

Es gibt bewusst **keine Administrationsoberfläche**. Die Lernseiten werden
ausschließlich über den MCP-Server unter `POST /mcp` gepflegt, den ein
KI-Agent bedient – abgesichert mit OAuth 2.1 und dem `TEACHER_PASSWORD`.

Acht Werkzeuge stehen bereit: `bundle_anlegen`, `bundle_liste`,
`bundle_anzeigen`, `bundle_aendern`, `karten_hinzufuegen`, `karte_aendern`,
`karte_loeschen` und `bundle_deaktivieren`. Endgültiges Löschen gibt es
darüber bewusst nicht – `bundle_deaktivieren` schaltet ein Lernpaket
unsichtbar, ohne etwas wegzuwerfen. `bundle_liste` zeigt standardmäßig nur
die aktiven Lernpakete; mit `nur_aktive=false` kommen die stillgelegten
wieder dazu.

Wie du den Server mit Claude Cowork verbindest, steht in
[docs/praxistest-cowork.md](docs/praxistest-cowork.md).

## Aufbau

| Datei / Verzeichnis | Inhalt |
|---|---|
| `compose.yml` | Der Betriebsverbund: `app` und `db` |
| `compose.test.yml` | Der Testlauf: `test` und `db`, beides flüchtig |
| `Dockerfile` | Zwei Stufen: `betrieb` und darauf aufbauend `test` |
| `docker/` | Die beiden Startskripte |
| `app/` | Anwendung |
| `migrations/` | Alembic |
| `tests/` | Testsuite |
| `docs/superpowers/specs/` | Design-Spec |
| `docs/design/mockups/` | Freigegebene Entwürfe – Referenz für die Optik |
