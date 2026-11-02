# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Local ingestion staging tables (``pipe_*``).

These tables are Reasonbook's local ingestion substrate. The CSV upload
path (``reasonbook.uploads.writer``) writes one row per period into them;
the ingestion job (``reasonbook.ingestion.pipe_reader``) reads the latest
period per (tenant, workflow) to evaluate triggers. There is no external
producer — the data path is entirely local (see DEPLOY.md, "the local
ingestion staging tables").

One table per workflow that has an upload path. Add a new ``Pipe*`` model
here and an entry in ``PIPE_TABLE_NAMES`` / ``PIPE_MODELS_BY_TABLE`` when
a new upload workflow ships.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class PipeRegulatoryCompliance(Base):
    __tablename__ = "pipe_regulatory_compliance"
    __table_args__ = (
        # Re-uploading the same period replaces that period's data (the
        # writer deletes any matching row first). This unique key is the
        # dedup key.
        UniqueConstraint(
            "tenant_id", "period_date", "period_type",
            name="uq_pipe_regulatory_compliance_tenant_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    period_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly", server_default=text("'monthly'"))
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    source: Mapped[str | None] = mapped_column(String(50), default="local")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# workflow_id -> pipe table name (consumed by pipe_reader + uploads.writer).
PIPE_TABLE_NAMES: dict[str, str] = {
    "01-regulatory-compliance": "pipe_regulatory_compliance",
}

# table name -> ORM model, so the writer/reader can resolve a model from the
# validated schema's pipe_table string without a dialect-specific raw INSERT.
PIPE_MODELS_BY_TABLE: dict[str, type[Base]] = {
    "pipe_regulatory_compliance": PipeRegulatoryCompliance,
}


__all__ = ["PIPE_MODELS_BY_TABLE", "PIPE_TABLE_NAMES", "PipeRegulatoryCompliance"]
