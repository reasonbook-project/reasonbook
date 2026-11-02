# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight-tier ORM models — evidence links and oversight cycles.

Renamed from apex per migration 0036. The user-facing concept is
oversight (federal agency leadership + IG + internal audit committee +
external oversight response surface); the legacy ``apex`` / ``board``
naming is retired.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class OversightEvidenceLink(Base):
    __tablename__ = "oversight_evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    oversight_decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    operational_decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # 10-oversight/config.yaml §evidence_roles — primary | supporting |
    # risk_concentration | regulatory_alignment | outcome | counter
    evidence_role: Mapped[str] = mapped_column(
        String(40), nullable=False, default="primary_evidence"
    )
    link_rationale: Mapped[str | None] = mapped_column(Text)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    linked_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Append-only supersession — superseded rows stay, ``superseded_by_link_id``
    # points at the row that replaced them.
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_link_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("oversight_evidence_links.id", ondelete="SET NULL"),
    )


class OversightCycle(Base):
    """Oversight cycle — IG audit window, internal audit committee
    meeting, OMB reporting cycle, appropriations cycle, or Congressional
    inquiry response window — that contains a set of oversight decisions."""

    __tablename__ = "oversight_cycles"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    cycle_type: Mapped[str] = mapped_column(String(40), nullable=False)
    committee: Mapped[str | None] = mapped_column(String(80))
    cycle_start: Mapped[date] = mapped_column(Date, nullable=False)
    cycle_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned", server_default=text("'planned'"))
    meeting_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class OversightFinding(Base):
    """One finding on an oversight cycle — OIG / GAO / Single Audit / internal.

    Append-only: transitions from ``open`` to ``closed`` (or
    ``under_appeal``) don't rewrite the row's history; the disposition
    is stamped at close time and preserved. Migration 0052.
    """

    __tablename__ = "oversight_findings"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("oversight_cycles.id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_number: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    # 'oig' | 'gao' | 'single_audit' | 'internal_audit'
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    # 'critical' | 'high' | 'medium' | 'low'
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    # 'open' | 'closed' | 'under_appeal'
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default=text("'open'"))
    cited_matter_ids: Mapped[list[uuid.UUID]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    citations: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    disposition: Mapped[str | None] = mapped_column(Text)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    opened_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
