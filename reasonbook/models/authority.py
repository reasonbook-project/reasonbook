# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""User-workflow authority and supervisor models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class UserWorkflowAuthority(Base):
    __tablename__ = "user_workflow_authority"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    limits: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Oversight extensions. NULL for users without oversight access.
    # oversight_role matches a persona id in 10-oversight/config.yaml
    # (agency_head, cfo, cpio, cco, coo, gc, inspector_general,
    # audit_committee_chair, oversight_liaison); oversight_domains_owned
    # lists which decision domains the user can own oversight decisions in;
    # oversight_can_record_committee_action gates the
    # "noted_by_committee" / "endorsed_by_committee" activity types.
    oversight_role: Mapped[str | None] = mapped_column(String(40))
    oversight_domains_owned: Mapped[list[str] | None] = mapped_column(JSON)
    oversight_can_record_committee_action: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class UserSupervisor(Base):
    __tablename__ = "user_supervisors"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    supervisor_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    workflow_id: Mapped[str | None] = mapped_column(String(50))
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
