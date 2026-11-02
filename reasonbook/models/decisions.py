# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Decision and decision-event models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tenants.tenant_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Owning agency. Nullable in this migration so existing rows stay
    # valid before the seed backfill; seed_dev sets it to the
    # appropriate agency (NIH-OER for the current corpus). Follow-up
    # migration adds NOT NULL once backfill is verified.
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision_number: Mapped[str] = mapped_column(String(20), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default=text("'medium'"))
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="medium", server_default=text("'medium'"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", server_default=text("'open'"))
    sla_hours: Mapped[int | None] = mapped_column(Integer)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_status: Mapped[str | None] = mapped_column(String(20), default="on_track")

    # Signal stage
    signal_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signal_source: Mapped[str | None] = mapped_column(Text)
    signal_summary: Mapped[str | None] = mapped_column(Text)
    trigger_data: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Owner stage
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_authority_level: Mapped[int | None] = mapped_column(Integer)
    escalation_path: Mapped[list[Any] | None] = mapped_column(JSON)

    # Decision stage
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_text: Mapped[str | None] = mapped_column(Text)
    selected_option: Mapped[str | None] = mapped_column(Text)
    alternatives: Mapped[list[Any] | None] = mapped_column(JSON)
    evidence_refs: Mapped[list[Any] | None] = mapped_column(JSON)
    rationale: Mapped[str | None] = mapped_column(Text)

    # Action stage
    action_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    action_artifacts: Mapped[list[Any] | None] = mapped_column(JSON)

    # Outcome stage
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome_text: Mapped[str | None] = mapped_column(Text)
    outcome_impact: Mapped[str | None] = mapped_column(String(40))
    outcome_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    # Side states
    defer_reason: Mapped[str | None] = mapped_column(Text)
    defer_reopen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    escalated_to: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    escalation_reason: Mapped[str | None] = mapped_column(Text)

    decision_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    tags: Mapped[list[str] | None] = mapped_column(JSON)

    # Tenancy model (migration 0039). matter_id is matter membership
    # — a decision belongs to exactly one matter (or none, for legacy /
    # pre-matter rows). matter_node_id pins it to a specific tier-node
    # inside the matter's fund-flow tree. fund_flow_path is the
    # write-time denormalization of the node's ancestor walk: an array
    # of participant_org_ids from federal-down (federal root excluded).
    # GIN-indexed for one-comparison row-level filtering in
    # apply_tier_scope (step 3).
    matter_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("matters.id")
    )
    matter_node_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("matter_nodes.id")
    )
    fund_flow_path: Mapped[list[uuid.UUID]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )

    # Governance Roadmap extensions per Prompt 1. ``decision_class`` is the
    # filterable discriminator separating ``operational`` (default) from
    # ``governance_improvement`` decisions promoted out of the Governance
    # Profile. ``governance`` carries the back-reference to the parent
    # initiative + milestone (None on operational rows). ``slip_notes`` is
    # an append-only audit trail written by Prompt 3's slip-detection job.
    decision_class: Mapped[str] = mapped_column(String(40), nullable=False, default="operational", server_default=text("'operational'"))
    governance: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    slip_notes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list, server_default=text("'[]'"))

    # Oversight extensions. oversight_cycle_id is set for oversight
    # decisions tied to a specific oversight cycle (IG audit, audit
    # committee meeting, appropriations cycle, etc.). target_outcome
    # captures the executive's stated expected outcome at decision time;
    # actual_outcome is captured 90+ days post-decision.
    oversight_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("oversight_cycles.id", ondelete="SET NULL")
    )
    target_outcome: Mapped[str | None] = mapped_column(Text)
    actual_outcome: Mapped[str | None] = mapped_column(Text)
    outcome_captured_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id", ondelete="SET NULL")
    )

    # External-party response (spec §6, migration 0054). Present on
    # Decisions written via the recipient/state response endpoints.
    # See docs/architecture/backlog/awaiting-recipient-stage-band.md
    # for the Phase-A path that promotes the two text stand-ins to
    # real FKs (parties.id, requests_for_response.id).
    is_commitment: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    originating_party_name: Mapped[str | None] = mapped_column(Text)
    response_shape: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    in_response_to: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class DecisionEvent(Base):
    __tablename__ = "decision_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id")
    )
    # Freeform action label. Existing values: 'created', 'assigned', 'claim',
    # 'finalize', 'defer', 'escalate', 'action', 'outcome', 'attachment_added',
    # 'attachment_removed', 'stage_edit', 'comment'. The 'comment' value is the
    # convention extension per reasonbook-authoring-and-config-amendment-v1_2.md §3.2:
    # body in `comment`, `{stage_context, mentions}` in `event_metadata`.
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20))
    new_status: Mapped[str | None] = mapped_column(String(20))
    comment: Mapped[str | None] = mapped_column(Text)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # SEC-1 hash chain (P09; see reasonbook/integrity/hash_chain.py + migration 0040).
    # Set by the before_insert hook in reasonbook/integrity/hooks.py — callers do
    # not populate these directly. The unique index on `hash` will trip on
    # accidental raw inserts that bypass the hook.
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # Unique: an accidental raw insert that reuses a hash (replay) trips this.
    hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", unique=True)


class DecisionAttachment(Base):
    """File attached to a decision at any stage.

    Per reasonbook-authoring-and-config-amendment-v1_2.md §3.1. Append-only —
    soft-delete sets `superseded_at` rather than removing the row.
    Storage of the file bytes themselves is abstracted via
    `reasonbook/storage/attachments.py` (ships in Phase 7.5 Gate 3); this table
    only records the metadata and a backend-resolvable `storage_uri`.
    """

    __tablename__ = "decision_attachments"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 'signal' / 'decision' / 'action' / 'outcome' / 'evidence' (stage-agnostic).
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    # 'do_spaces' / 'pg_lo' / 'local' / future, per amendment §3.3.
    storage_backend: Mapped[str] = mapped_column(Text, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    description: Mapped[str | None] = mapped_column(Text)
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
