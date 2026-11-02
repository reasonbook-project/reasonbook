# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ORM model for control_points.

See migration 0044_control_points.py for column-level documentation and
docs/architecture/_archive/Spine/ADR-11-accountability-spine.md (decision #2 and
the ATC map) for the design rationale.

A control point is one gate that must be cleared — or named-gap'd —
before a downstream lifecycle event advances. One row per
(matter_node × archetype × trigger_event) where the archetype's
``upstream_review`` declares an obligation.

Status transitions write append-only ``decision_events`` rows
(``control_point_cleared`` / ``control_point_skipped``) so the hash
chain covers control-point activity.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class ControlPoint(Base):
    __tablename__ = "control_points"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    matter_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("matters.id", ondelete="CASCADE"),
        nullable=False,
    )
    node_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("matter_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    archetype_id: Mapped[str] = mapped_column(String(80), nullable=False)
    trigger_event: Mapped[str] = mapped_column(String(40), nullable=False)
    gate_type: Mapped[str] = mapped_column(String(20), nullable=False)
    required_authority_role: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    cleared_by_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id"),
    )
    cleared_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id"),
    )
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    named_gap_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


__all__ = ["ControlPoint"]
