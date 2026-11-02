# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0

# ---------------------------------------------------------------------------
# Stage 1 — build the React/TypeScript SPA (Node; build-time only).
# ---------------------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
# corepack ships with Node 20 and pins pnpm per the project's packageManager.
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm build                       # -> /web/dist

# ---------------------------------------------------------------------------
# Stage 2 — Python runtime. No Node, no tests, no .git, no .env in this layer.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS app

# Non-root user and a writable data dir for the SQLite file + attachments.
RUN useradd --create-home --uid 10001 reasonbook \
    && mkdir -p /data /data/attachments \
    && chown -R reasonbook:reasonbook /data
# curl is used by the container HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the Python package (with the PostgreSQL driver available so an
# operator can switch to PostgreSQL via REASONBOOK_DATABASE_URL without a
# rebuild). Copy only what pip needs first for better layer caching.
COPY pyproject.toml README.md ./
COPY reasonbook/ ./reasonbook/
RUN pip install --no-cache-dir ".[postgres]"

# App code: migrations, alembic config, entrypoint. (web/ source is NOT
# copied — only the built bundle from stage 1.)
COPY migrations/ ./migrations/
COPY alembic.ini ./alembic.ini
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY docker/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

# The built SPA, served as static files by Flask. Gitignored in the repo;
# produced by stage 1.
COPY --from=web /web/dist ./reasonbook/static/web

ENV REASONBOOK_DATABASE_URL="sqlite:////data/reasonbook.db" \
    REASONBOOK_ATTACHMENT_LOCAL_ROOT="/data/attachments" \
    REASONBOOK_FLASK_ENV="production" \
    PYTHONUNBUFFERED=1

USER reasonbook
EXPOSE 8000

# Healthcheck hits the API health route from inside the container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# The entrypoint runs `alembic upgrade head`, then gunicorn with a single
# worker so the in-process ingestion scheduler runs in exactly one process.
ENTRYPOINT ["./entrypoint.sh"]
