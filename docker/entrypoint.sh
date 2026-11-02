#!/bin/sh
# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
set -e

# Run database migrations to head (idempotent; safe on every start).
echo "reasonbook: applying database migrations..."
alembic upgrade head

# Optional first-run admin bootstrap. When REASONBOOK_ADMIN_EMAIL is set, this
# creates the admin user if missing and prints a generated password once.
if [ -n "$REASONBOOK_ADMIN_EMAIL" ]; then
    echo "reasonbook: ensuring bootstrap admin ($REASONBOOK_ADMIN_EMAIL)..."
    python -m scripts.bootstrap_admin || true
fi

# Optional demo seed. Only runs when REASONBOOK_SEED_DEMO=true.
if [ "$REASONBOOK_SEED_DEMO" = "true" ]; then
    echo "reasonbook: seeding NON-PRODUCTION demo accounts..."
    python -m scripts.seed_dev || true
fi

# Single worker: the in-process APScheduler ingestion job must run in exactly
# one process. To scale web workers, run the scheduler as a separate
# --workers 1 process and set REASONBOOK_RUN_SCHEDULER=false on the others.
echo "reasonbook: starting gunicorn on :8000 (--workers 1)"
exec gunicorn "reasonbook.app:create_app()" \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
