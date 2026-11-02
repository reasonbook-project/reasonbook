# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ORM models for alerts + alert_dispositions.

See migration 0035_alerts.py for column-level documentation and
docs/architecture/fedRAMP/ALERTS-SPEC.md for the design rationale.

The two tables together implement the "no silent close" rule: every
disposition (promote / dismiss / hold / reopen) writes an append-only
row with a mandatory rationale. The alert's ``current_status`` is a
denormalised cache of the latest disposition's resulting_status; the
ledger is the source of truth.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    # Owning agency — nullable in this migration for backfill.
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    signal_ref: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    subject_entity: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    matter_id: Mapped[uuid.UUID | None] = mapped_column(GUID)
    fund_flow_ref: Mapped[list[uuid.UUID]] = mapped_column(
        JSON,
        nullable=False,
        server_default=text("'[]'"),
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    target_program_id: Mapped[str] = mapped_column(String(100), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    current_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'new'")
    )


class AlertDisposition(Base):
    __tablename__ = "alert_dispositions"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(40))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_tier: Mapped[str] = mapped_column(String(20), nullable=False)
    resulting_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="SET NULL"),
    )
    resulting_status: Mapped[str] = mapped_column(String(20), nullable=False)
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        server_default=text("'{}'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


__all__ = ["Alert", "AlertDisposition"]
