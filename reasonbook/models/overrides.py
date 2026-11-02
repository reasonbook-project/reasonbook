# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Agency semantic-override model (append-only).

Renamed from ``TenantSemanticOverride`` in migration 0046 alongside the
underlying table rename ``tenant_semantic_overrides`` →
``agency_semantic_overrides``. Per-agency semantic overrides make more
sense in the DP model than per-tenant: each federal agency can override
default thresholds on the workflows it owns without affecting other
agencies. ``tenant_id`` stays temporarily for backfill compatibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class AgencySemanticOverride(Base):
    __tablename__ = "agency_semantic_overrides"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False)
    config_key: Mapped[str] = mapped_column(String(255), nullable=False)
    config_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    modified_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_note: Mapped[str | None] = mapped_column(Text)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Backward-compat alias. Old imports from `reasonbook.models.overrides` and
# `reasonbook.models` still resolve. Remove after downstream code has moved.
