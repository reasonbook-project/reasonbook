# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""In-process ingestion scheduler (APScheduler).

Reasonbook runs its single ingestion job in-process on an APScheduler
``BackgroundScheduler`` started by the application factory — no separate worker or broker process. The job fires every
``REASONBOOK_INGESTION_INTERVAL_MINUTES`` (default 5) and calls
:func:`reasonbook.ingestion.runner.run_ingestion`.

**One-process requirement.** The scheduler must run in exactly one
process. Under gunicorn with N workers, N schedulers would each fire the
job. Keep the default ``--workers 1``, or set
``REASONBOOK_RUN_SCHEDULER=false`` on the extra workers so only one
starts it. ``max_instances=1`` + ``coalesce=True`` further guarantee a
slow run never overlaps itself or stacks up missed runs.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.exc import OperationalError

from reasonbook.config import get_settings
from reasonbook.ingestion.runner import IngestionStats, run_ingestion

log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def run_ingestion_once(*, max_retries: int = 3) -> IngestionStats:
    """Run one ingestion pass, retrying on SQLite "database is locked".

    The semantic engine is ensured-loaded first (the scheduler thread may
    reach this before any request has triggered a boot). On SQLite a brief
    write-lock contention raises ``OperationalError``; we back off and
    retry rather than dropping the batch.
    """
    from reasonbook.semantic.engine import get_engine, init_engine
    from reasonbook.semantic.loader import WorkflowConfigError

    try:
        get_engine()
    except WorkflowConfigError:
        init_engine()

    backoff = 0.5
    last_exc: OperationalError | None = None
    for attempt in range(1, max_retries + 1):
        try:
            stats = run_ingestion()
            break
        except OperationalError as exc:  # noqa: PERF203
            if "database is locked" not in str(exc).lower():
                raise
            last_exc = exc
            log.warning("ingestion: database locked (attempt %d/%d), backing off", attempt, max_retries)
            time.sleep(backoff)
            backoff *= 2
    else:  # pragma: no cover - only when every retry is locked
        assert last_exc is not None
        raise last_exc

    log.info(
        "ingestion: tenants=%d workflows=%d triggers=%d fired=%d created=%d skipped=%d errors=%d",
        stats.tenants_evaluated,
        stats.workflows_evaluated,
        stats.triggers_evaluated,
        stats.triggers_fired,
        stats.decisions_created,
        stats.decisions_skipped_dedup,
        len(stats.errors),
    )
    return stats


def _job() -> dict[str, Any]:
    stats = run_ingestion_once()
    return {
        "tenants_evaluated": stats.tenants_evaluated,
        "workflows_evaluated": stats.workflows_evaluated,
        "triggers_evaluated": stats.triggers_evaluated,
        "triggers_fired": stats.triggers_fired,
        "decisions_created": stats.decisions_created,
        "decisions_skipped_dedup": stats.decisions_skipped_dedup,
        "errors": stats.errors,
    }


def start_scheduler() -> BackgroundScheduler | None:
    """Start the background ingestion scheduler (idempotent).

    Returns the live scheduler, or ``None`` when disabled via
    ``REASONBOOK_RUN_SCHEDULER=false`` or in testing.
    """
    global _scheduler
    settings = get_settings()
    if not settings.run_scheduler or settings.testing:
        log.info("ingestion scheduler disabled (run_scheduler=%s testing=%s)", settings.run_scheduler, settings.testing)
        return None
    if _scheduler is not None:
        return _scheduler

    interval = max(1, settings.ingestion_interval_minutes)
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        _job,
        trigger="interval",
        minutes=interval,
        id="reasonbook-ingestion",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    _scheduler = scheduler
    log.info("ingestion scheduler started (every %d min, in-process)", interval)
    return scheduler
