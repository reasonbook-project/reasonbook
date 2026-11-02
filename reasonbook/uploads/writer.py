# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Direct writer — inserts validated upload rows into the local ``pipe_*`` tables.

Reasonbook ingests a CSV upload by writing one row per period into the
local ingestion staging table for the workflow (``pipe_<workflow>``). The
period column becomes ``period_date``; the rest of the row becomes the
``data`` JSON blob. Re-uploading the same period replaces that period's
data (the writer deletes any matching ``(tenant, period, period_type)``
row first), so uploads are idempotent per period.

There is no remote producer — the data path is entirely local. The writer
never re-validates; it trusts the validator and returns a ``WriteResult``
so the API layer can report row counts.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.models.pipe import PIPE_MODELS_BY_TABLE
from reasonbook.semantic.schema import UploadSchema

log = logging.getLogger(__name__)


@dataclass
class WriteResult:
    rows_written: int
    pipe_table: str | None = None


class WriterError(Exception):
    """Raised when the database write fails."""


def _parse_period(period_value: Any) -> date:
    """Coerce the period column to a date for the pipe row.

    Accepts ``YYYY-MM`` (assumes day=01) and full ISO dates. Anything else
    is the validator's problem — the writer asserts the validator already
    ran by raising loudly here.
    """
    if isinstance(period_value, date) and not isinstance(period_value, datetime):
        return period_value
    if isinstance(period_value, datetime):
        return period_value.date()
    s = str(period_value)
    if len(s) == 7 and s[4] == "-":  # YYYY-MM
        return date.fromisoformat(f"{s}-01")
    return date.fromisoformat(s)


def write_rows(
    *,
    session: Session,
    rows: list[dict[str, Any]],
    schema: UploadSchema,
    tenant_id: str,
) -> WriteResult:
    """Insert validated rows into the local ``pipe_<workflow>`` table.

    Uses the ORM model for the pipe table so JSON serialization is handled
    per-dialect (works on SQLite and PostgreSQL). Existing rows for the
    same ``(tenant, period, period_type)`` are replaced.
    """
    pipe_table = schema.pipe_table
    model = PIPE_MODELS_BY_TABLE.get(pipe_table)
    if model is None:
        raise WriterError(f"no pipe table registered for '{pipe_table}'")

    period_col = next(c for c in schema.columns if c.primary_key)
    period_type = schema.period_type

    try:
        for row in rows:
            period = _parse_period(row[period_col.name])
            # data blob = everything except the period column. Coerce date
            # values to ISO strings so JSON serialisation is stable.
            blob = {
                k: (v.isoformat() if isinstance(v, date) else v)
                for k, v in row.items()
                if k != period_col.name
            }
            # Replace any existing row for this period (idempotent upsert).
            session.query(model).filter_by(
                tenant_id=tenant_id, period_date=period, period_type=period_type
            ).delete()
            session.add(
                model(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    period_date=period,
                    period_type=period_type,
                    data=blob,
                    source="manual-upload",
                )
            )
        session.flush()
    except Exception as exc:  # noqa: BLE001
        raise WriterError(f"pipe write failed: {exc}") from exc

    log.info(
        "upload: wrote %d row(s) to %s for tenant=%s", len(rows), pipe_table, tenant_id
    )
    return WriteResult(rows_written=len(rows), pipe_table=pipe_table)
