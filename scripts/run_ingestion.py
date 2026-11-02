# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Run one pass of signal ingestion for every tenant.

Useful in dev / demos:

    DATABASE_URL='...' uv run python -m scripts.run_ingestion

In production this is invoked by the in-process APScheduler registered in
``reasonbook.ingestion.scheduler``.
"""

from __future__ import annotations

import logging

from reasonbook.ingestion import run_ingestion
from reasonbook.semantic.engine import init_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def main() -> None:
    init_engine()
    stats = run_ingestion()
    print(
        f"ingestion: tenants={stats.tenants_evaluated} workflows={stats.workflows_evaluated} triggers={stats.triggers_evaluated} fired={stats.triggers_fired} "
        f"created={stats.decisions_created} skipped={stats.decisions_skipped_dedup} errors={len(stats.errors)}"
    )
    for err in stats.errors:
        print(f"  ERROR: {err}")


if __name__ == "__main__":
    main()
