# Entscheidungen während Plan 1

Beim Bau des Fundaments sind unterwegs Fragen aufgetaucht, die der Plan nicht
beantwortet hat. Sie wurden entschieden, statt die Arbeit anzuhalten — jede mit
Begründung und mit der Angabe, was sie kostet, falls sie falsch war.

Diese Liste ist der Ort, an dem du sie nachlesen und umstoßen kannst. Sie stammt
aus dem Arbeitsprotokoll der Ausführung, das selbst nicht versioniert wird.

Stand: 2026-08-27, 34 Entscheidungen.

---

### 1. Konflikt 1 — `tests/conftest.py` bekommt in T3 einen autouse-Override von `get_session` auf die Testsession (`app.dependency_overrides`). Grund: Tests duerfen nie die Entwicklungsdatenbank anfassen; sonst haengt ein gruener Test an zufaelligem lokalem Zustand. Kosten falls falsch: gering, der Override ist vier Zeilen und leicht zurueckzunehmen.

### 2. Konflikt 2 — T4 nimmt `tests/conftest.py` in die zu aendernden Dateien auf und ergaenzt `from app import models  # noqa: F401`. Grund: Ohne den Import legt `create_all` keine Tabellen an und saemtliche Modelltests scheitern mit "relation does not exist". Kosten falls falsch: keine, der Import ist folgenlos, wenn er ueberfluessig waere.

### 3. Konflikt 3 — In `tests/test_config.py` wird `Settings` durchgaengig mit `_env_file=None` gebaut. Grund: Der Test soll die Pflichtfeld-Pruefung von pydantic testen, nicht den Inhalt der lokalen `.env`. Kosten falls falsch: keine.

### 4. Konflikt 4 — `TEST_DATABASE_URL` wird erst **innerhalb** der `test_engine`-Fixture gelesen; fehlt sie, wird per `pytest.skip` uebersprungen statt das Einsammeln abzubrechen. Grund: Tests ohne Datenbankbezug (Konfiguration, Markdown, Container) muessen auch ohne laufende Datenbank durchlaufen. Kosten falls falsch: gering — im schlimmsten Fall werden DB-Tests still uebersprungen, deshalb muss die Skip-Meldung den Grund nennen.

### 5. Konflikt 5 — Der Constraint bleibt deferrable (das Umsortieren spaeter braucht das), aber der Test setzt ihn vorher explizit scharf: `SET CONSTRAINTS uq_karten_bundle_position IMMEDIATE`. Grund: So bleibt die spaetere Umsortierung moeglich und der Test prueft trotzdem echt. Kosten falls falsch: gering, betrifft nur diesen einen Test.

### 6. Konflikt 6 — Im Container laufen alle Wartungsverbindungen (`initdb`, Rolle anlegen, `pg_dump`) ueber den lokalen Socket ohne `-h localhost`, weil `--auth-local=trust` gilt; `initdb` bekommt `-D "$PGDATA"` ausdruecklich mit. Nur die Anwendung selbst verbindet ueber `localhost` mit Passwort (scram). Grund: Sonst scheitert der Erststart des Containers reproduzierbar an der Authentifizierung. Kosten falls falsch: hoch, wenn uebersehen — der Container waere nie gestartet; deshalb vorab geklaert.

### 7. Umgebung — lokal ist Python 3.14.4 installiert, der Container nutzt 3.13. Task 1 legt zusaetzlich `.python-version` mit `3.13` an, damit `uv` lokal dieselbe Version zieht wie das Image. Grund: Ohne Pin wird lokal gegen 3.14 getestet und im Container gegen 3.13 ausgeliefert — genau die Drift, die spaet und schlecht auffaellt. Kosten falls falsch: keine, eine Datei mit einer Zeile.

### 8. Task 1 ⚠️ "PostgreSQL 17 aus dem Diff nicht pruefbar" — kein Mangel. Infrastruktur ist Gegenstand von Task 7 (Dockerfile mit postgresql-17), dort wird es geprueft. Kosten falls falsch: keine, Task 7 deckt es ab.

### 9. Task 1 minor "Deprecation-Warning" wird nicht sofort behoben, sondern an Task 3 weitergereicht, der `tests/test_main.py` ohnehin anfasst. Grund: Einen eigenen Fix-Durchlauf fuer eine Warnung zu starten kostet mehr als der Befund wert ist, und Task 3 fasst die Datei sowieso an. Kosten falls falsch: gering, die Warnung bleibt bis Task 3 stehen.

### 10. Task 2 Befund "get_settings() ist zu 0% getestet" — der Befund gilt, wird behoben. Grund: Task 3 baut direkt auf dieser Funktion auf, und der lru_cache ist genau die Stelle, an der spaeter stille Fehler entstehen. Der Brief hatte die Luecke, das entschuldigt sie nicht. Fix-Runde 1. Kosten falls falsch: gering, ein zusaetzlicher Test.

### 11. Task 2 Befund "pydantic-Fehlermeldungen sind englisch" — kein Mangel, wird nicht behoben. Grund: Die Spec fordert deutsche Fehlermeldungen fuer die MCP-Oberflaeche, weil der Agent sie der Lehrerin vorliest (Spec Abschnitt 5). Konfigurationsfehler beim Start sieht ausschliesslich der Betreiber; pydantic dafuer zu lokalisieren waere Aufwand ohne Nutzen. Meine Formulierung der Global Constraints war hier zu weit gefasst. Kosten falls falsch: keine — betrifft nur Text, den die Zielnutzerin nie sieht.

### 12. Task 2 Hinweis "lru_cache braucht cache_clear zwischen Tests" wird als Schnittstellenhinweis an Task 3 weitergereicht. Kosten falls falsch: gering.

### 13. Task 3 hat `httpx2>=2.12.0` als neue Dev-Abhaengigkeit eingezogen, um die Starlette-Deprecation-Warnung zu beheben. Ich habe das Paket vor der Review selbst geprueft: veroeffentlicht von Pydantic Services Inc. (engineering@pydantic.dev), Repository github.com/pydantic/httpx2, erklaerte Fortfuehrung von httpx unter neuer Stewardship, Version 2.12.0 vom 18.08.2026. Kein Typosquat, Abhaengigkeit akzeptiert. Grund fuer die Pruefung: Ein unbekanntes Paket einzuziehen, um eine Warnung loszuwerden, ist ein Lieferketten-Risiko und wird nicht durchgewunken. Offen bleibt, ob `httpx` daneben noch gebraucht wird — das beurteilt die Review. Kosten falls falsch: hoch, deshalb geprueft statt angenommen.

### 14. Befund 1 wird an der Wurzel behoben statt per verzoegertem Import — Engine-Erzeugung in app/db.py wird faul (`get_engine()`/`get_session_factory()` mit lru_cache). Grund: Der verzoegerte Import waere ein Pflaster an einer Stelle; faule Erzeugung macht den Import von app.db und app.main grundsaetzlich umgebungsfrei. Das ist zugleich Voraussetzung fuer die vom Nutzer gewuenschte GitHub-CI, wo es per Definition keine lokale .env gibt. Aenderung an der geplanten Schnittstelle: `app.db.engine`/`app.db.SessionLocal` entfallen zugunsten der beiden Funktionen; nichts in Plan 1 konsumiert die Attribute ausser get_session selbst. Kosten falls falsch: gering, betrifft eine Datei und ihre Aufrufer.

### 15. Befund 2 wird behoben — gemeinsame `client`-Fixture in conftest, die den Override selbst setzt und abraeumt. Grund: Eine Sicherheitsgarantie darf nicht davon abhaengen, dass kuenftige Testdateien an eine Fixture denken. Kosten falls falsch: gering.

### 16. Nutzerwunsch waehrend der Ausfuehrung — Tests sollen spaeter in GitHub Actions laufen. Entscheidung: KEINE separate compose.test.yaml, sondern dieselbe compose.dev.yml in CI hochfahren. Grund: Zwei Compose-Dateien, die dasselbe Postgres beschreiben, driften auseinander und erzeugen "gruen in CI, rot lokal". Wird als Task 9 in Plan 1 aufgenommen und nach Task 8 ausgeschrieben. Kosten falls falsch: gering, eine Workflow-Datei.

### 17. Hintergrund-Sicherheitspruefung hat pyproject.toml als Lieferketten-Risiko markiert (httpx2). Geprueft und abgehakt: Repository pydantic/httpx2 existiert unter der Pydantic-Organisation (1000 Sterne, 2263 Commits, aktiv), PyPI weist Pydantic Services Inc. als Herausgeber aus, erklaerte Fortfuehrung von httpx. Zusaetzlich entscheidend: httpx2 ist reine Dev-Abhaengigkeit und wird vom geplanten Dockerfile per `uv sync --frozen --no-dev` nie ins Produktionsimage installiert. Kosten falls falsch: begrenzt auf die Entwicklungsumgebung, nicht auf den ausgelieferten Container.

### 18. Alle drei Wichtig-Befunde werden behoben, und die Migration 0001 wird dabei **an Ort und Stelle geaendert** statt eine 0002 nachzuschieben. Grund: Nichts ist deployt, es gibt keine Datenbank im Feld, deren Zustand zu bewahren waere. Eine zweite Migration wuerde die Historie mit einem Fehler und seiner Korrektur belasten, den nie jemand gesehen hat. Kosten falls falsch: keine, solange vor dem ersten Deployment korrigiert wird — danach waere es unzulaessig.

### 19. Zusaetzlich zu den Wichtig-Befunden werden mehrere Klein-Befunde in dieselbe Runde gezogen, weil sie das Rueckgrat betreffen und einzeln je eine Zeile kosten: Constraint-Namen in den Ablehnungstests pruefen, drei fehlende Grenzfalltests, MutableList fuer `antworten`, benannter Unique-Constraint auf `slug`, CHECK auf `position >= 0`. Grund: Ein spaeterer Fix am Datenmodell kostet eine Migration; jetzt kostet er nichts. Kosten falls falsch: etwas mehr Aufwand in dieser Runde.

### 20. Frage des Reviewers, ob eine Flashcard eine Erklaerung tragen koennen soll — nein, wie gebaut korrekt. Die Spec legt in Abschnitt 4 ausdruecklich fest, dass bei `art = 'flashcard'` die Felder `antworten`, `richtige_index` und `erklaerung` leer sind; die Erklaerung gehoert zur Aufloesung einer Frage. Kosten falls falsch: eine Migration, falls die Lehrerin es spaeter doch braucht.

### 21. Reviewer-Vorschlag `alembic check` gegen Modell-Migration-Drift wird nicht hier, sondern in Task 9 (GitHub-CI) umgesetzt. Grund: Dort gehoert es hin und laeuft bei jedem Push, statt einmalig lokal. Kosten falls falsch: gering, bis Task 9 bleibt die Pruefung manuell.

### 22. Die Nachpruefung hat gemeldet, dass der Plan selbst (Zeile 817) weiterhin `config.set_main_option("sqlalchemy.url", ...)` vorschreibt — also genau den behobenen Fehler. Ich habe den Plan korrigiert und die Begruendung dazugeschrieben. Grund: Ein Plan, der einen behobenen Fehler weiter vorschreibt, baut ihn beim naechsten woertlichen Befolgen wieder ein; der Fix im Code allein reicht nicht. Kosten falls falsch: keine.

### 23. Der Befund wird behoben, aber ueber eine Laengengrenze (MAX_LAENGE = 5000 Zeichen) mit eigener Ausnahme `MarkdownZuLang`, nicht ueber ein Tiefenlimit oder einen Timeout. Grund: Die Laenge ist die eine Groesse, die der Agent der Lehrerin versteht und beeinflussen kann, und sie begrenzt die Verschachtelungstiefe gleich mit. Eine Ausnahme statt stillem Abschneiden, weil abgeschnittener Lernstoff schlimmer ist als eine klare Meldung — die MCP-Schicht in Plan 2 legt sie dem Agenten vor. Kosten falls falsch: gering, die Grenze ist eine Konstante.

### 24. Nicht behoben wird die Frage, ob pro Aufruf oder einmalig beim Speichern gerendert wird. Grund: Die Spec legt Rendern beim Ausliefern fest, und die Laengengrenze macht die Kosten pro Aufruf vernachlaessigbar. Falls sich in Plan 3 zeigt, dass es doch teuer ist, ist das dort zu entscheiden. Kosten falls falsch: gering, betrifft nur Rechenzeit.

### 25. Die Laengengrenze von 5000 bleibt trotz der ungueltigen Messung des Implementierers. Grund: Der Reviewer hat unabhaengig nachgemessen — pathologischer Fall `"[" * 4990` braucht rund 35 ms, linear mit der Laenge, also deutlich unter der Zehntelsekunde. Die Grenze ist sachlich richtig, nur der Beleg fehlte. Kosten falls falsch: gering, die Grenze ist eine Konstante.

### 26. Das wird sofort behoben, vor Task 7, in einem eigenen kleinen Dispatch. Grund: Die Suite ist damit rot, sobald man sie mit gesetzter Umgebung laufen laesst — und genau so laeuft sie in Task 7, Task 8 und spaeter in der CI. Ein roter Test, den alle als "vorbestehend" abhaken, ist der Anfang einer Suite, der niemand mehr glaubt. Kosten falls falsch: gering, betrifft einen Test.

### 27. Alle sieben werden behoben, dazu drei Klein-Befunde (dockerignore-Muster, ungepinntes uv-Image, Passwort-Drift-Kommentar). Grund: Es sind Betriebsfehler, die alle erst im Feld auffallen wuerden, und der Task existiert genau, um Datenverlust zu verhindern. Kosten falls falsch: eine laengere Fix-Runde.

### 28. Der Reviewer hat einen Widerspruch in den Testzahlen des Reports gefunden ("2 passed in 40.68s" fuer die Container-Tests vs. "52 passed in 16.03s" fuer die Gesamtsuite auf derselben Maschine). Das ist der zweite Fall in diesem Projekt, in dem ein Beleg nicht traegt. Anordnung: ungekuerzte Ausgabe der Gesamtsuite nach dem Fix. Ich pruefe die Zahl anschliessend selbst nach. Kosten falls falsch: keine, Nachpruefen ist billig.

### 29. Damit entfallen Kritisch 1 und Wichtig 2 aus der Task-7-Review ersatzlos. Die uebrigen fuenf Wichtig-Befunde und die drei Klein-Befunde bleiben zu beheben, weil es echte Fehler sind und kein Ausbau.

### 30. Der Failfast-Eventlistener (docker/failfast-listener.py, 60 Zeilen Supervisor-Eventprotokoll) wird entfernt, der HEALTHCHECK bleibt. Grund: Der Nutzer will keine Automatisierung, sondern die App fertig. Der Listener baut Protokollmechanik nach, um einen Fall zu behandeln, den der Healthcheck sichtbar macht — und der Implementierer berichtet selbst, dass dieser Pfad nie gegen einen echt kaputten App-Prozess durchlaufen wurde. Ungepruefte Mechanik, deren einzige Aufgabe das Beenden des Containers ist, ist ein groesseres Risiko als der Zustand, den sie verhindern soll. Kosten falls falsch: Ein dauerhaft gescheiterter App-Prozess laesst den Container als "unhealthy" stehen, statt ihn zu beenden — sichtbar, aber nicht selbstheilend.

### 31. Der offene Punkt "docker stop endete mit Exit 137 trotz sauberem Postgres-Shutdown im Log" bleibt offen und dokumentiert. Grund: Postgres hat laut eigenem Log sauber heruntergefahren; das genuegt fuer diesen Stand, und die Ursache liegt vermutlich in der Testumgebung. Kosten falls falsch: Bei jedem Deployment eine Crash-Recovery beim Start — laut, aber ohne Datenverlust dank WAL.

### 32. Der Plan enthielt noch Backup-Reste (docker/backup.sh, /data/backups, [program:backup] und einen README-Abschnitt im Template von Task 8). Ich habe sie selbst aus dem Plandokument entfernt. Grund: Der README-Abschnitt waere in Task 8 unveraendert in die Auslieferung gewandert — ein Plan, der eine gestrichene Anforderung weiter vorschreibt, baut sie beim naechsten woertlichen Befolgen wieder ein. Kosten falls falsch: keine.

### 33. Entgegen der Regel "keine zweite Fix-Welle" habe ich die zwei offenen Punkte noch beheben lassen. Grund: Beide tragen fuer Plan 2 und kosteten je eine Zeile. Der jsonpath lief im lax-Modus und liess verschachtelte Arrays durch - Plan 2 sucht in genau dieser Liste den Antworttext und haette eine Liste statt eines Strings bekommen. Und die Laengengrenze in der Migration hatte keinen Waechter, weil das Testschema aus den Modellen gebaut wird und `alembic check` nur Constraint-Namen vergleicht, nicht deren Ausdruecke. Kosten falls falsch: eine zusaetzliche Runde, die sich in Plan 2 als Fehlersuche geracht haette.

### 34. Wortlisten bleiben bei 30 Eintraegen, die Spec wurde auf diesen Stand korrigiert statt die Listen aufzufuellen. Grund: 27.000 Adressen reichen fuer eine Schule bei weitem; die Spec war hier ungenau, nicht der Code.
