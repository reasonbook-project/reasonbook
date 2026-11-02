# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Decision-type registry model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class DecisionType(Base):
    __tablename__ = "decision_types"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False)
    type_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    domain: Mapped[str | None] = mapped_column(String(50))
    default_priority: Mapped[str | None] = mapped_column(String(20), default="medium")
    sla_hours: Mapped[int | None] = mapped_column(Integer, default=72)
    default_owner_role: Mapped[str | None] = mapped_column(String(50))
    trigger_metric: Mapped[str | None] = mapped_column(String(100))
    trigger_threshold: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    payload_schema: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    oversight_evidence_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    workflow_version: Mapped[str | None] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
