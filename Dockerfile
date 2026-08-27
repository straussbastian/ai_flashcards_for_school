FROM python:3.13-slim-trixie

ENV PYTHONUNBUFFERED=1 \
    PGDATA=/data/pgdata \
    PATH="/usr/lib/postgresql/17/bin:/app/.venv/bin:$PATH" \
    TZ=Europe/Berlin

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-17 \
        postgresql-client-17 \
        supervisor \
        tini \
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

# Nur der App-Prozess (uvicorn) muss unprivilegiert laufen - er ist der
# einzige von aussen erreichbare Prozess und verarbeitet Markdown und
# sonstige Nutzereingaben (siehe supervisord.conf, user=app). Dafuer muss
# /app fuer den Benutzer app lesbar sein (Code + venv); Schreibzugriff
# braucht er zur Laufzeit dort nicht.
RUN chmod -R a+rX /app

EXPOSE 8000

# Ergaenzt die Faelle, die supervisord/der Eventlistener selbst nicht nach
# aussen sichtbar machen: Docker/Coolify markieren den Container als
# "unhealthy", wenn /healthz nicht mehr antwortet.
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=3 \
    CMD python3 -c "import sys, urllib.request; \
sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/docker/entrypoint.sh"]
