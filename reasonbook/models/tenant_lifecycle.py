# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tenant-level audit-log model.

``user_audit`` cascades on user deletion, so it can't carry
tenant-deletion records — the audit row would be wiped along with the
users it FKs to. ``tenant_lifecycle_events`` has no FK back to
``tenants``, so the audit trail survives the cascade. Tenant-level
lifecycle events (manual deletion, account merge, suspension, restore,
future Phase 3 ATO / continuous-monitoring events) write rows here by
adding new ``event_type`` values.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class TenantLifecycleEvent(Base):
    __tablename__ = "tenant_lifecycle_events"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(100))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["TenantLifecycleEvent"]
