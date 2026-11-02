# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tenant model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[str | None] = mapped_column(String(30))
    regulator: Mapped[str | None] = mapped_column(String(30))
    asset_size_band: Mapped[str | None] = mapped_column(String(20))
    # Unstructured tenant context — peer group, board cadence, examiner
    # contacts, fiscal year, risk-appetite statement. Edited via the
    # tenant settings PATCH endpoint.
    tenant_profile: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
