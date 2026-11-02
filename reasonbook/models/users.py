# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""User and audit-log models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("tenants.tenant_id"), nullable=False
    )
    # Primary agency the user belongs to. Nullable for state/recipient-
    # tier users (they scope by participant_org_id instead). Federal
    # users get a required agency assignment via seed / admin invite.
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default=text("'active'"))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    # Lockout columns (migration 0032). Rate limiter slows brute force;
    # consecutive_failures + locked_at close the low-and-slow gap.
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lock_reason: Mapped[str | None] = mapped_column(Text)
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Tenancy model (migration 0039). DP is single-tenant (federal govt is
    # the customer); access is partitioned by tier on the user, not by a
    # SaaS-style tenant boundary. tier ∈ {federal, state, recipient}; a
    # CHECK constraint enforces participant_org_id NULL ↔ tier='federal'.
    tier: Mapped[str] = mapped_column(String(20), nullable=False, default="federal", server_default=text("'federal'"))
    participant_org_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("participant_orgs.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class UserAudit(Base):
    __tablename__ = "user_audit"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(50))
    old_value: Mapped[str | None] = mapped_column(String(255))
    new_value: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# Re-export Text so consumers don't import from sqlalchemy directly here.
__all__ = ["User", "UserAudit", "Text"]
