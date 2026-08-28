# Praxistest: den MCP-Server mit Claude Cowork verbinden

Diese Anleitung ist für dich zum Ausführen, nicht für einen Agenten. Sie
braucht dein Cowork-Konto und ein paar Minuten an der Tastatur.

## Was dieser Test beweist – und was nicht

**Er beweist:** dass Cowork sich verbinden kann. Also dass die Erkennung der
Endpunkte, der OAuth-Ablauf mit deinem Passwort und der MCP-Handschlag über
eine echte HTTPS-Verbindung aus Anthropics Cloud funktionieren.

**Er beweist nicht,** dass die Werkzeuge richtig rechnen. Das tun die Tests –
301 Stück, und sie decken die Werkzeuge einzeln ab. Wenn dieser Praxistest
scheitert, liegt es fast sicher an der Verbindung, nicht an der Logik.

Warum es überhaupt einen Tunnel braucht: Cowork erreicht MCP-Server aus
Anthropics Cloud (Quellbereich `160.79.104.0/21`), nicht von deinem Rechner.
Ein Container, der nur auf `localhost` lauscht, ist von dort unerreichbar.

## Voraussetzungen

- `cloudflared` installiert (`brew install cloudflared`)
- Docker läuft
- Ein Cowork-Konto

## Die Reihenfolge ist nicht beliebig

**Der Tunnel muss vor dem Server starten.** Der Grund steht in den Global
Constraints des Plans und ist bewusst so gebaut: Alle OAuth-URLs entstehen
ausschließlich aus `BASE_URL` und niemals aus einem Request-Header. Das ist
eine Sicherheitsentscheidung – hinter einem Reverse Proxy sind
`X-Forwarded-Host` und `X-Forwarded-Proto` fälschbar, und die Spec verlangt,
dass das Feld `resource` exakt der Adresse entspricht, die du in Cowork
einträgst.

Die Folge für dich: Der Server muss seine öffentliche Adresse schon beim
Start kennen. Ein Schnelltunnel von Cloudflare vergibt aber einen zufälligen
Namen, den du erst nach dem Start erfährst. Also erst Tunnel, dann Server.

## Schritt 1: Tunnel starten

In einem eigenen Terminalfenster, das offen bleibt:

```bash
cloudflared tunnel --url http://localhost:8000
```

Cloudflare gibt eine Adresse der Form
`https://zufaellige-woerter.trycloudflare.com` aus. Notiere sie – sie wird
im Folgenden `TUNNEL` genannt.

Der Tunnel zeigt jetzt ins Leere; auf Port 8000 läuft noch nichts. Das ist in
Ordnung.

## Schritt 2: Server mit dieser Adresse starten

In einem zweiten Fenster, `TUNNEL` durch die tatsächliche Adresse ersetzen:

```bash
BASE_URL=https://TUNNEL.trycloudflare.com \
TEACHER_PASSWORD=ein-eigenes-passwort \
./run-local.sh
```

Beide Werte überschreiben die Vorgaben des Skripts, das sonst
`http://localhost:8000` und das Entwicklungspasswort setzt. Den alten
Container beendet das Skript selbst.

**Setz das Passwort wirklich.** Solange der Tunnel läuft, ist dieser
Container öffentlich erreichbar, und `TEACHER_PASSWORD` ist das Einzige, was
zwischen dem Netz und deinen Lernseiten steht. Das Entwicklungspasswort aus
`run-local.sh` steht im Repository.

Die Tunneladresse gehört **ohne** Schrägstrich am Ende eingetragen.

## Schritt 3: Von außen gegenprüfen, bevor Cowork ins Spiel kommt

Diese drei Aufrufe sagen dir, ob es an der Verbindung liegt – **bevor** du in
Cowork nach einem Fehler suchst, den du dort nicht siehst.

```bash
curl -s https://TUNNEL.trycloudflare.com/healthz
# erwartet: {"status":"ok","datenbank":"ok"}

curl -s https://TUNNEL.trycloudflare.com/.well-known/oauth-protected-resource/mcp
# erwartet: "resource" ist GENAU https://TUNNEL.trycloudflare.com/mcp

curl -si -X POST https://TUNNEL.trycloudflare.com/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize"}' | head -5
# erwartet: HTTP/2 401 und ein Kopf WWW-Authenticate: Bearer ...
#           resource_metadata="https://TUNNEL.trycloudflare.com/.well-known/..."
```

Die 401 ist **kein Fehler**, sondern der Auslöser des ganzen Ablaufs: Claude
liest daraus, wo die Metadaten stehen.

Stimmt der Hostname in `resource` nicht mit deiner Tunneladresse überein,
brich hier ab. Cowork würde die Verbindung sonst mit einer Meldung ablehnen,
die die Ursache nicht nennt.

## Schritt 4: In Cowork eintragen

1. In Cowork auf **Customize → Connectors**
2. **Custom Connector** hinzufügen
3. Als Adresse `https://TUNNEL.trycloudflare.com/mcp` eintragen – mit `/mcp`
   am Ende und exakt so geschrieben wie in Schritt 3 geprüft
4. **Verbinden** klicken

Es öffnet sich die Zustimmungsseite mit dem gelben Zettel. Dort dein
`TEACHER_PASSWORD` eingeben und auf **Zugriff geben** klicken.

Danach sollte Cowork acht Werkzeuge anzeigen: `bundle_anlegen`,
`bundle_liste`, `bundle_anzeigen`, `bundle_aendern`, `karten_hinzufuegen`,
`karte_aendern`, `karte_loeschen` und `bundle_deaktivieren`.

## Schritt 5: Ausprobieren

Der Satz, für den das Ganze gebaut ist:

> „Bau mir aus diesem Arbeitsblatt ein Lernpaket."

Dazu ein Arbeitsblatt anhängen oder Text einfügen. Erwartet: Der Agent legt
das Paket in einem Aufruf an und gibt dir den fertigen Link zurück. Diesen
Link im Browser öffnen – die Lernseite sollte stehen.

Weitere lohnende Proben:

- „Zeig mir alle Lernpakete" → `bundle_liste`
- „Ändere den Titel auf …" → `bundle_aendern`, und der Link bleibt derselbe
- „Nimm die dritte Karte raus" → `karte_loeschen`
- „Stell das Paket unsichtbar" → `bundle_deaktivieren`, danach zeigt die
  Seite einen Hinweis statt der Karten, und die Karten sind **nicht** weg

## Wenn etwas klemmt

| Beobachtung | Wahrscheinliche Ursache |
|---|---|
| „Couldn't reach the MCP server" | `BASE_URL` stimmt nicht mit der Tunneladresse überein. Schritt 3 wiederholen. |
| Verbindung bricht nach Neustart des Tunnels ab | Ein Schnelltunnel bekommt bei jedem Start einen neuen Namen. Server mit der neuen Adresse neu starten und den Connector in Cowork neu eintragen. |
| Zustimmungsseite erscheint, Passwort wird nicht angenommen | `TEACHER_PASSWORD` im Container weicht von dem ab, was du eintippst. |
| Nach dem Passwort geht es nicht weiter | In der Entwicklerkonsole des Browsers nach einem CSP-Verstoß sehen. Die Zustimmungsseite hat eine eigene Richtlinie, die `claude.ai` als Formularziel erlaubt. |
| Werkzeug meldet einen deutschen Satz | Das ist Absicht. Die Meldungen sagen, was zu tun ist – dem Agenten einfach antworten. |
| `{"status":"ok","datenbank":"fehler"}` | Der Container ist hochgekommen, PostgreSQL darin nicht. `docker logs flashcards-lokal` ansehen. |

## Aufräumen

```bash
docker stop -t 45 flashcards-lokal && docker rm flashcards-lokal
```

`docker stop` statt `docker rm -f`: Der harte Weg schickt PostgreSQL ein
SIGKILL und lässt eine `postmaster.pid` im Volume zurück. Der Containerstart
räumt sie inzwischen weg, aber geordnet herunterfahren ist trotzdem besser.

Dann das Tunnelfenster mit `Ctrl-C` beenden. Danach ist nichts mehr von außen
erreichbar.

**Solange der Tunnel läuft, ist dein Server öffentlich im Netz.** Geschützt
ist er allein durch `TEACHER_PASSWORD` und die Bearer-Tokens. Für einen Test
ist das in Ordnung; als Dauerzustand ist es nicht gedacht – dafür gibt es das
Deployment auf Coolify (siehe README).
