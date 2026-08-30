# Auf einem eigenen Server betreiben

Diese Anleitung stellt die Lernseiten dauerhaft ins Netz – unter einer
eigenen Adresse, mit gültigem HTTPS, ohne Verwaltungsoberfläche und ohne
dass auf dem Server irgendetwas gebaut wird.

Gebraucht wird **eine Datei**: [`compose.server.yml`](../compose.server.yml).
Sie zieht das fertige Abbild aus der GitHub-Registry, startet PostgreSQL
daneben und stellt einen Caddy davor, der sich das Zertifikat bei Let's
Encrypt selbst besorgt.

| | |
|---|---|
| Einmaliger Aufwand | rund 30 Minuten |
| Laufende Kosten | 4–8 € im Monat für den Server, dazu die Domain |
| Nötige Vorkenntnisse | eine Datei über SSH anlegen und einen Befehl ausführen |

> **Stand dieser Anleitung.** Die Schritte sind aus der laufenden
> Konfiguration hergeleitet, aber noch nicht auf einem frisch gemieteten
> Server durchgespielt worden. Wer sie als Erster geht, möge Abweichungen
> als Issue melden – dann wird der Text nachgezogen.

## Warum HTTPS Pflicht ist

Nicht aus Prinzipienreiterei: Der KI-Agent, der die Lernpakete anlegt,
verbindet sich aus Anthropics Cloud auf den Server. Ohne gültiges
Zertifikat kommt diese Verbindung nicht zustande. Und HTTPS gibt es nur zu
einem Namen, nicht zu einer nackten IP-Adresse – deshalb braucht es eine
Domain oder wenigstens eine Subdomain.

## Schritt 1: Einen Server mieten

Es genügt der kleinste Tarif: zwei Kerne, 4 GB Arbeitsspeicher, 40 GB
Platte sind reichlich für eine Schule.

**Bei Hostinger:** einen VPS bestellen und bei der Einrichtung die Vorlage
**Ubuntu 24.04 with Docker** wählen. Docker und Docker Compose sind dann
schon installiert. ([Anleitung von
Hostinger](https://www.hostinger.com/support/8306612-how-to-use-the-docker-vps-template-at-hostinger/))

**Bei Hetzner:** einen Cloud-Server anlegen und unter *Image → Apps* die
App **Docker CE** wählen. Dasselbe Ergebnis.

> **Kein ARM-Server.** Hetzners CAX-Reihe ist zwar billiger, das
> veröffentlichte Abbild wird aber nur für `linux/amd64` gebaut. Also
> CX/CPX bei Hetzner, bei Hostinger sind ohnehin alle Tarife x86-64.

Am Ende hast du eine IP-Adresse und ein Passwort für `root`.

## Schritt 2: Die Domain auf den Server zeigen lassen

Beim Anbieter der Domain einen **A-Record** anlegen, der auf die IP des
Servers zeigt – zum Beispiel `karten` → `203.0.113.10`, was die Adresse
`karten.deine-schule.de` ergibt.

Bevor es weitergeht, prüfen, ob die Zuordnung angekommen ist. Das dauert je
nach Anbieter Minuten bis Stunden:

```bash
ping -c1 karten.deine-schule.de
```

Kommt hier noch die alte oder gar keine Adresse, **warte**. Caddy würde im
nächsten Schritt sonst vergeblich ein Zertifikat beantragen.

Falls beim Anbieter eine Firewall eingeschaltet ist: **Port 80 und 443
müssen offen sein.** Port 80 wird für die Zertifikatsprüfung gebraucht,
auch wenn die Seite später nur über 443 läuft.

## Schritt 3: Die vier Werte festlegen

Per SSH auf den Server, ein Verzeichnis anlegen und die Compose-Datei holen:

```bash
ssh root@203.0.113.10

mkdir -p /opt/flashcards && cd /opt/flashcards
curl -O https://raw.githubusercontent.com/straussbastian/ai_flashcards_for_school/main/compose.server.yml
```

Daneben eine Datei `.env` mit genau vier Zeilen. Die beiden zufälligen Werte
erzeugt `openssl rand -hex 32` – einmal aufrufen, Ergebnis einsetzen, für den
zweiten Wert noch einmal aufrufen:

```bash
cat > .env <<'ENDE'
DOMAIN=karten.deine-schule.de
POSTGRES_PASSWORD=hier-ein-langes-zufaelliges-passwort
APP_SECRET=hier-ein-zweites-langes-zufaelliges-passwort
TEACHER_PASSWORD=das-passwort-das-die-lehrkraft-eintippt
ENDE

chmod 600 .env
```

Mehr ist es nicht. Die Adresse der Datenbank und die öffentliche Basis-URL
setzt `compose.server.yml` aus diesen Werten selbst zusammen – die frühere
Fehlerquelle, ein Passwort zweimal unterschiedlich einzutragen, gibt es
hier nicht.

**`TEACHER_PASSWORD` ist das eine Passwort, das zählt.** Es ist alles, was
zwischen dem offenen Netz und den Lernpaketen steht. Kein Wort aus dem
Schulalltag, keines, das anderswo schon in Benutzung ist.

## Schritt 4: Starten

```bash
docker compose -f compose.server.yml up -d
```

Der erste Start dauert ein bis zwei Minuten: Abbild laden, Datenbank
anlegen, Migrationen einspielen, Zertifikat beantragen. Zusehen kann man
dabei mit:

```bash
docker compose -f compose.server.yml logs -f
```

## Schritt 5: Nachsehen, ob es steht

```bash
curl -s https://karten.deine-schule.de/healthz
# erwartet: {"status":"ok","datenbank":"ok"}
```

Kommt diese Antwort über **https** zurück, sind Server, Datenbank,
Anwendung und Zertifikat in Ordnung. Im Browser zeigt dieselbe Adresse
einen gelben Zettel mit einem Satz – das ist die Startseite, und sie sagt
absichtlich nichts weiter.

## Schritt 6: Den KI-Agenten verbinden

Als Adresse des Connectors `https://karten.deine-schule.de/mcp` eintragen –
mit `/mcp` am Ende. Beim Verbinden fragt die Zustimmungsseite nach dem
`TEACHER_PASSWORD`.

Die ausführliche Fassung mit allen Zwischenprüfungen steht in
[praxistest-cowork.md](praxistest-cowork.md); dort wird zum Ausprobieren
ein Tunnel statt eines Servers benutzt, ab Schritt 4 ist es dasselbe.

---

## Ohne Kommandozeile: der Docker Manager bei Hostinger

Hostingers Docker-Tarife bringen eine Oberfläche mit, die eine
Compose-Datei direkt von einer URL entgegennimmt – *Compose from URL*, dazu
ein Formular für die Umgebungsvariablen. Die URL ist:

```
https://raw.githubusercontent.com/straussbastian/ai_flashcards_for_school/main/compose.server.yml
```

Die vier Werte aus Schritt 3 dort als Umgebungsvariablen eintragen. Ein
Port-Mapping ist **nicht** einzurichten: Die Datei bringt ihre Ports selbst
mit, und die Datenbank soll bewusst keine haben.

Dieser Weg ist der bequemere, aber ungeprüft – die Anleitung oben ist der
Weg, dem die Konfiguration nachweislich entspricht.

## Im Betrieb

**Auf den neuesten Stand bringen.** Jeder Stand von `main`, der die
Testsuite grün durchlaufen hat, liegt als Abbild bereit:

```bash
cd /opt/flashcards
docker compose -f compose.server.yml pull
docker compose -f compose.server.yml up -d
```

**Sichern.** Die Lernpakete liegen im Volume `pgdata`. Eine Sicherung, die
man auch anderswo wieder einspielen kann:

```bash
docker compose -f compose.server.yml exec -T db \
    pg_dump -U flashcards flashcards | gzip > sicherung-$(date +%F).sql.gz
```

Diese Datei gehört vom Server herunter – eine Sicherung, die neben dem
Original liegt, ist keine.

**Anhalten und wieder starten.**

```bash
docker compose -f compose.server.yml down     # hält an, die Daten bleiben
docker compose -f compose.server.yml down -v  # wirft ALLE Lernpakete weg
```

Der Unterschied ist ein `-v`. Beide Befehle sehen fast gleich aus und tun
etwas grundverschiedenes.

**Das Datenbankpasswort wechseln.** `POSTGRES_PASSWORD` in der `.env` zu
ändern genügt nicht: Das PostgreSQL-Abbild legt die Rolle nur beim
allerersten Start an und rührt sie danach nicht mehr an. Die Anwendung käme
mit dem neuen Passwort nicht mehr an ihre Datenbank. Also zuerst in der
Datenbank ändern, dann in der `.env`:

```bash
docker compose -f compose.server.yml exec db \
    psql -U flashcards -c "alter role flashcards password 'neues-passwort'"
# danach POSTGRES_PASSWORD in der .env angleichen und neu starten
docker compose -f compose.server.yml up -d
```

## Wenn etwas klemmt

| Beobachtung | Wahrscheinliche Ursache |
|---|---|
| `denied` beim ersten `up` | Das Paket auf ghcr.io steht noch auf privat. Siehe unten. |
| Browser meldet ein ungültiges Zertifikat | Der A-Record zeigt nicht (mehr) auf diesen Server, oder Port 80 ist von einer Firewall zugehalten. `docker compose -f compose.server.yml logs caddy` sagt, woran es lag. |
| `{"status":"ok","datenbank":"nicht erreichbar"}` | Der Dienst `db` ist nicht hochgekommen: `logs db`. |
| Die App startet nicht, im Log steht `BASE_URL muss mit http:// oder https:// beginnen` | `DOMAIN` in der `.env` ist leer geblieben. |
| Der Connector verbindet sich nicht | Die eingetragene Adresse muss exakt `https://<DOMAIN>/mcp` sein und `DOMAIN` exakt der Domain entsprechen, unter der der Server läuft. |
| Alles läuft, aber die Links in den Antworten des Agenten zeigen woandershin | `DOMAIN` wurde nach dem ersten Start geändert, ohne neu zu starten. |

**Zum privaten Paket** – das betrifft nur die Betreiberin des Repositories,
und nur einmal: GitHub legt ein neu veröffentlichtes Abbild privat an, auch
in einem öffentlichen Repository. Unter *Repository → Packages → Package
settings → Change visibility* auf `public` stellen. Danach kann jeder
Server es ohne Anmeldung ziehen.

---

## Variante: mit Coolify

Der Weg oben braucht keine Verwaltungsoberfläche. Wer trotzdem eine will –
für mehrere Anwendungen auf einem Server, für Deployment auf Knopfdruck,
für Logs im Browser –, nimmt Coolify. Beide Anbieter haben dafür ein
fertiges Abbild, sodass Coolify selbst nicht installiert werden muss:
Hostinger als VPS-Vorlage *Ubuntu 24.04 with Coolify*, Hetzner als
Marketplace-App *Coolify*. Die Oberfläche liegt danach auf Port 3000.

So läuft der Betriebsserver dieses Projekts. Einzurichten ist dort:

1. Neue Anwendung aus diesem Git-Repository, **Build über `compose.yml`**
   (Docker Compose, nicht das nackte `Dockerfile` – die Anwendung allein
   hat keine Datenbank). Nicht `compose.server.yml`: Der Caddy darin wäre
   ein zweiter Rückwärtsproxy vor dem, den Coolify schon mitbringt.
2. **Persistentes Volume für `pgdata`** – ohne das sind die Lernpakete beim
   nächsten Deployment fort
3. Umgebungsvariablen aus `.env.example` setzen. `DATABASE_URL` zeigt auf
   `db:5432`; Benutzer, Passwort und Datenbankname darin müssen zu
   `POSTGRES_USER`, `POSTGRES_PASSWORD` und `POSTGRES_DB` passen, `BASE_URL`
   auf die echte Domain
4. Domain auf den Dienst `app` zuweisen, HTTPS aktivieren
5. Healthcheck auf `/healthz`
6. **Automatic Deployment ausschalten.** Sonst rollt Coolify bei jedem Push
   selbst aus, auch bei roter Testsuite. Angestoßen wird stattdessen aus
   `.github/workflows/tests.yml`, und zwar erst nach grünem Lauf. Dafür
   liegen in GitHub zwei Secrets: `COOLIFY_WEBHOOK_URL` und
   `COOLIFY_AUTH_TOKEN`.
