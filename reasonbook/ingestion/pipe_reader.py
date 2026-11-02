# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Read access to the local ``pipe_<workflow>`` staging tables.

Reasonbook's ingestion job only needs the most recent period row per
(tenant, workflow) for trigger evaluation. The table name maps directly
from ``workflow_id`` via ``PIPE_TABLE_NAMES``. These tables are populated
locally by the CSV upload path (``reasonbook.uploads.writer``) — there is
no external producer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.models.pipe import PIPE_MODELS_BY_TABLE, PIPE_TABLE_NAMES

__all__ = ["PIPE_TABLE_NAMES", "PipeReading", "latest_reading"]


@dataclass(frozen=True)
class PipeReading:
    """The latest period of pipe data for a (tenant, workflow)."""

    tenant_id: str
    workflow_id: str
    period_date: date
    period_type: str
    data: dict[str, Any]
    source: str


def latest_reading(
    *,
    session: Session,
    tenant_id: str,
    workflow_id: str,
) -> PipeReading | None:
    """Return the most recent pipe row for this tenant + workflow, or None."""
    table_name = PIPE_TABLE_NAMES.get(workflow_id)
    if table_name is None:
        return None
    model = PIPE_MODELS_BY_TABLE.get(table_name)
    if model is None:
        return None

    row = (
        session.query(model)
        .filter(model.tenant_id == tenant_id)
        .order_by(model.period_date.desc())
        .first()
    )
    if row is None:
        return None
    return PipeReading(
        tenant_id=tenant_id,
        workflow_id=workflow_id,
        period_date=row.period_date,
        period_type=row.period_type,
        data=dict(row.data or {}),
        source=row.source or "local",
    )
