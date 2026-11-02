# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Signal ingestion — read local pipe_* rows, evaluate triggers, surface decisions."""

from reasonbook.ingestion.runner import IngestionStats, run_ingestion

__all__ = ["IngestionStats", "run_ingestion"]
