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
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

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

EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/app/docker/entrypoint.sh"]
