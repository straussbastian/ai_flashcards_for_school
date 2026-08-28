# Ein Prozess pro Container. Die Anwendung (Lernseiten + MCP-Server, beides
# derselbe uvicorn - /mcp ist eine Route in app/main.py) laeuft hier; die
# Datenbank ist ein eigener Dienst daneben (siehe compose.yml).
#
# Frueher steckte PostgreSQL mit im Abbild, verwaltet von supervisord. Das ist
# fort: kein Prozessverwalter, kein initdb, kein Aufraeumen verwaister
# Sperrdateien, kein su postgres. Die Datenbank kommt jetzt unveraendert aus
# dem offiziellen postgres-Abbild.
FROM python:3.13-slim-trixie AS betrieb

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Europe/Berlin

# tini reicht Signale sauber an uvicorn durch und sammelt Zombies ein - das
# uebernahm vorher supervisord. tzdata, weil TZ sonst ins Leere zeigt: Das
# schlanke Python-Abbild bringt keine Zeitzonendatenbank mit (vorher kam sie
# als Beifang mit den PostgreSQL-Paketen).
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini \
        tzdata \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --no-create-home --shell /usr/sbin/nologin app

# Gepinnt auf einen Digest statt :latest, damit der Build reproduzierbar
# bleibt und sich nicht unbemerkt unter uns aendert.
COPY --from=ghcr.io/astral-sh/uv@sha256:88bc6eb1ccd4b82efd0e1b530caffabddf50dc2bf612e66c14ea25b8ee8a4d3d /uv /usr/local/bin/uv

WORKDIR /app

# Erst nur die Abhaengigkeiten installieren: Diese Schicht bleibt im Cache,
# solange sich pyproject.toml/uv.lock nicht aendern. --no-install-project
# ist noetig, weil app/ hier noch nicht kopiert ist - hatchling braucht das
# Paketverzeichnis, um das Projekt selbst zu bauen (siehe unten).
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
COPY docker ./docker
RUN chmod +x docker/*.sh

# Jetzt, wo app/ vorhanden ist, auch das Projekt selbst installieren.
RUN uv sync --frozen --no-dev

# Der ganze Container laeuft unprivilegiert. Das ging vorher nicht: initdb
# und PostgreSQL brauchten root bzw. den Benutzer postgres, weshalb nur der
# App-Prozess unter supervisord auf "app" heruntergestuft war. Ohne
# Datenbank im Abbild faellt dieser Grund weg.
RUN chmod -R a+rX /app
USER app

EXPOSE 8000

# Macht einen dauerhaft gescheiterten App-Prozess sichtbar: Docker/Coolify
# markieren den Container als "unhealthy", wenn /healthz nicht mehr
# antwortet. Der Container wird dadurch nicht beendet - darauf reagiert die
# Betriebsebene, nicht die Anwendung.
#
# --start-period 60s statt der frueheren 180s: Es gibt kein initdb und keinen
# Anlauf eines Datenbankservers mehr im Container. Hier laeuft nur noch die
# Wartezeit auf den db-Dienst (FRIST_SEKUNDEN in docker/app-start.sh, 90s)
# und "alembic upgrade head". Bleibt die Datenbank ganz weg, beendet sich
# app-start.sh nach 90 Sekunden mit Klartext - der Healthcheck ist dann gar
# nicht mehr die Instanz, die das meldet.
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD python3 -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/docker/app-start.sh"]


# ============================================================================
# Die Teststufe: dasselbe Abbild, nur zusaetzlich mit Testwerkzeug.
# ============================================================================
#
# Bewusst FROM betrieb und keine eigene Basis: Getestet werden soll das, was
# spaeter auch laeuft - dieselbe Python-Version, dieselben Abhaengigkeiten,
# derselbe Startweg. Ein eigenes Testabbild waere ein zweites System, das
# unbemerkt auseinanderlaufen kann.
#
# Gebaut wird sie nur, wenn jemand ausdruecklich danach fragt
# (compose.test.yml, target: test). Das Betriebsabbild traegt kein pytest,
# keinen Chromium und keine Testdateien.
FROM betrieb AS test

USER root

# Ausserhalb von /app und an einer festen Stelle: Der Standardort haengt am
# HOME des installierenden Benutzers (hier root), und getestet wird spaeter
# als "app". Ohne diese Variable suchte Playwright den Browser im falschen
# Verzeichnis.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Jetzt MIT den dev-Abhaengigkeiten (pytest, pytest-asyncio, httpx2,
# playwright). Oben lief dasselbe Kommando mit --no-dev.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen

COPY tests ./tests

# --with-deps holt die Systembibliotheken mit, die Chromium auf einem nackten
# Debian braucht. Ohne sie startet der Browser mit einem Fehler ueber eine
# fehlende .so-Datei, und das sieht nach einem kaputten Test aus statt nach
# einem fehlenden Paket. Danach a+rX, damit "app" den Browser auch lesen darf.
RUN uv run playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

# Anders als im Betrieb braucht die Suite Schreibrechte in /app: pytest legt
# .pytest_cache an, Python schreibt __pycache__.
#
# Und sie laeuft als "app" und nicht als root - nicht aus Vorsicht, sondern
# weil Chromium sich weigert, als root ohne --no-sandbox zu starten.
# tests/browser/conftest.py ruft p.chromium.launch() ohne Argumente; als root
# waeren die Browsertests damit tot.
RUN chown -R app:app /app
USER app

# Das Startskript gehoert in den ENTRYPOINT und nicht ins CMD: Sonst ersetzt
# "docker compose run --rm test -k oauth" das Kommando komplett, statt die
# Argumente an pytest durchzureichen.
ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/test-start.sh"]
CMD []
