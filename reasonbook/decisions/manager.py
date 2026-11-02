# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""DecisionManager — full lifecycle for platform.decisions.

Ports legacy ``cu-saas/decisions/models.py`` rewritten in SQLAlchemy ORM
style and updated for Reasonbook vocabulary (tenant_id / workflow_id) and the §3.4
five-stage anatomy fields.

Public surface:
    create_decision         — insert new row
    claim_decision          — open/assigned → in_progress, snapshot authority
                              level, compute escalation_path
    finalize_decision       — record selected_option + rationale + evidence
                              (authority gate enforced)
    record_action           — stage 4 (action_started_at, completed_at,
                              artifacts)
    record_outcome          — stage 5 (outcome_text, impact, metrics, closes
                              the decision)
    defer_decision          — sets status='deferred' with reason + reopen_at
    escalate_decision       — sets status='escalated' with reason + target

Every transition writes a ``platform.decision_events`` row, with workflow_id
denormalised so time-series queries stay cheap.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO, Literal

from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.decisions.authority import (
    compute_escalation_path,
    current_authority_level,
    user_can_approve_action,
)
from reasonbook.models import Decision, DecisionAttachment, DecisionEvent, User
from reasonbook.storage.attachments import AttachmentStorage, StorageRef, get_storage

log = logging.getLogger(__name__)

VALID_STATUSES = (
    "open",
    "assigned",
    "in_progress",
    "decided",
    "closed",
    "deferred",
    "escalated",
)
VALID_PRIORITIES = ("critical", "urgent", "high", "medium", "low")
# Outcome taxonomy — two layers per ARCHITECTURE_MASTER §6.5.
#  - GENERIC_OUTCOMES: original sentiment classifier, valid for any archetype.
#  - LEGAL_OUTCOMES: IG enforcement / DOJ referral language; the "natural
#    Outcome types DP records" for adverse_action and oversight matters,
#    speaking the language oversight buyers (agency IGs, DOJ) use.
GENERIC_OUTCOMES = ("positive", "neutral", "negative")
LEGAL_OUTCOMES = (
    "debarment",
    "administrative_recovery",
    "civil_referral",
    "criminal_referral",
)
VALID_OUTCOMES = GENERIC_OUTCOMES + LEGAL_OUTCOMES

# from_status → set of allowed to_statuses
TRANSITIONS: dict[str, set[str]] = {
    "open": {"assigned", "in_progress", "deferred", "escalated"},
    "assigned": {"in_progress", "deferred", "escalated"},
    "in_progress": {"decided", "deferred", "escalated"},
    "decided": {"closed", "deferred", "escalated"},
    "deferred": {"open", "assigned", "in_progress"},
    "escalated": {"assigned", "in_progress"},
}


class DecisionStateError(ValueError):
    """Raised when a state transition is not allowed."""


class DecisionAuthorityError(PermissionError):
    """Raised when the actor lacks authority for the requested action."""


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_decision(decision_id: uuid.UUID, *, session: Session | None = None) -> Decision | None:
    if session is not None:
        return session.get(Decision, decision_id)
    with session_scope() as managed:
        d = managed.get(Decision, decision_id)
        if d is not None:
            managed.expunge(d)
        return d


EventInclude = Literal["audit", "comments", "all"]


def get_events(
    decision_id: uuid.UUID,
    *,
    include: EventInclude = "audit",
    session: Session | None = None,
) -> list[DecisionEvent]:
    """Return decision events. ``include`` filters by the comment convention:

    - ``audit`` (default): every event except ``action='comment'`` rows. The
      audit log surface that existed before Phase 7.5 Gate 7.
    - ``comments``: only ``action='comment'`` rows.
    - ``all``: everything.
    """

    def _q(s: Session) -> list[DecisionEvent]:
        q = s.query(DecisionEvent).filter(DecisionEvent.decision_id == decision_id)
        if include == "audit":
            q = q.filter(DecisionEvent.action != "comment")
        elif include == "comments":
            q = q.filter(DecisionEvent.action == "comment")
        # "all" → no extra filter
        return q.order_by(DecisionEvent.created_at.asc()).all()

    if session is not None:
        return _q(session)
    with session_scope() as managed:
        rows = _q(managed)
        for r in rows:
            managed.expunge(r)
        return rows


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _next_decision_number(session: Session, tenant_id: str) -> str:
    # MAX(int_part)+1 rather than count+1: count is fragile when the table
    # has rows from seeders that pick numbers directly, deleted rows, or any
    # other non-contiguous insertion order. Looking at the existing 'DEC-####'
    # range and adding one keeps the sequence monotonic in those cases too.
    max_n = (
        session.query(func.max(func.cast(func.substring(Decision.decision_number, 5), Integer)))
        .filter(Decision.tenant_id == tenant_id)
        .filter(Decision.decision_number.like("DEC-%"))
        .scalar()
        or 0
    )
    return f"DEC-{max_n + 1:04d}"


def _log_event(
    session: Session,
    *,
    decision: Decision,
    user_id: uuid.UUID | None,
    action: str,
    old_status: str | None,
    new_status: str | None,
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        DecisionEvent(
            id=uuid.uuid4(),
            decision_id=decision.id,
            tenant_id=decision.tenant_id,
            workflow_id=decision.workflow_id,
            user_id=user_id,
            action=action,
            old_status=old_status,
            new_status=new_status,
            comment=comment,
            event_metadata=metadata,
        )
    )


def _check_transition(decision: Decision, to_status: str) -> None:
    allowed = TRANSITIONS.get(decision.status, set())
    if to_status not in allowed:
        raise DecisionStateError(
            f"cannot transition {decision.status!r} → {to_status!r} (allowed: {sorted(allowed)})"
        )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def create_decision(
    *,
    tenant_id: str,
    workflow_id: str,
    decision_type: str,
    title: str,
    created_by: uuid.UUID | None = None,
    description: str | None = None,
    priority: str = "medium",
    sla_hours: int | None = None,
    owner_id: uuid.UUID | None = None,
    trigger_data: dict[str, Any] | None = None,
    signal_source: str | None = None,
    signal_summary: str | None = None,
    decision_payload: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    decision_class: str = "operational",
    governance: dict[str, Any] | None = None,
    # Tenancy / matter membership (TENANCY-MODEL §11.1, §12). Optional so
    # legacy callers continue to work; the matter service always supplies
    # the full triple. fund_flow_path is denormalised from the matter
    # node's ancestor walk at create time.
    matter_id: uuid.UUID | None = None,
    matter_node_id: uuid.UUID | None = None,
    fund_flow_path: list[uuid.UUID] | None = None,
    # DP tenancy substrate — owning agency for federal-tier decisions.
    # Nullable so pre-agency-substrate callers keep working; the
    # matter service + demo seed always supply it.
    agency_id: uuid.UUID | None = None,
    session: Session | None = None,
) -> Decision:
    """Insert a new decision and write the 'created' (and optional 'assigned') events.

    ``decision_class`` is the operational classifier; only ``operational``
    is supported now that the governance-improvement (roadmap)
    surface has been retired.
    """
    if priority not in VALID_PRIORITIES:
        raise ValueError(f"invalid priority: {priority}")
    if decision_class != "operational":
        raise ValueError(f"invalid decision_class: {decision_class}")

    def _do(s: Session) -> Decision:
        now = datetime.now(UTC)
        sla_deadline = now + timedelta(hours=sla_hours) if sla_hours else None
        initial_status = "assigned" if owner_id else "open"

        decision_number = _next_decision_number(s, tenant_id)

        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agency_id=agency_id,
            decision_number=decision_number,
            workflow_id=workflow_id,
            decision_type=decision_type,
            title=title,
            description=description,
            priority=priority,
            status=initial_status,
            sla_hours=sla_hours,
            sla_deadline=sla_deadline,
            sla_status="on_track",
            signal_captured_at=now,
            signal_source=signal_source,
            signal_summary=signal_summary,
            trigger_data=trigger_data,
            owner_id=owner_id,
            created_by=created_by,
            assigned_at=now if owner_id else None,
            decision_payload=decision_payload,
            tags=tags,
            decision_class=decision_class,
            governance=governance,
            matter_id=matter_id,
            matter_node_id=matter_node_id,
            fund_flow_path=fund_flow_path or [],
        )
        s.add(decision)
        s.flush()

        _log_event(
            s,
            decision=decision,
            user_id=created_by,
            action="created",
            old_status=None,
            new_status=initial_status,
        )
        if owner_id:
            _log_event(
                s,
                decision=decision,
                user_id=created_by,
                action="assigned",
                old_status="open",
                new_status="assigned",
                comment="Assigned at creation",
            )
        return decision

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Commitment (external-party response)
# ---------------------------------------------------------------------------


def create_commitment_decision(
    *,
    tenant_id: str,
    matter_id: uuid.UUID,
    workflow_id: str,
    title: str,
    originating_party_name: str,
    response_shape: dict[str, Any],
    in_response_to: str | None,
    submitted_by_user_id: uuid.UUID,
    matter_node_id: uuid.UUID | None = None,
    fund_flow_path: list[uuid.UUID] | None = None,
    agency_id: uuid.UUID | None = None,
    signal_summary: str | None = None,
    session: Session | None = None,
) -> Decision:
    """Write an append-only commitment Decision from an external-party response.

    Distinct from ``create_decision`` + ``finalize_decision`` because a
    commitment has response-is-a-decision semantics (spec §6): the party's
    submit IS the decision, so we skip the authority check (the recipient's
    identity + attestation carry the authorization), skip upstream dispatch
    (the commitment is the outcome, not a promotion), and land the row
    at status='decided' with ``is_commitment=True`` in a single write.

    Federal-proxy path (spec §7.3, backlog A0): ``submitted_by_user_id``
    is the internal PM taking the action on the party's behalf. Real
    recipient auth (Phase B) replaces this with the party's own session.
    """

    def _do(s: Session) -> Decision:
        now = datetime.now(UTC)
        decision_number = _next_decision_number(s, tenant_id)
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agency_id=agency_id,
            decision_number=decision_number,
            workflow_id=workflow_id,
            decision_type="recipient_response",
            title=title,
            priority="medium",
            status="decided",
            signal_captured_at=now,
            signal_source="recipient_response",
            signal_summary=signal_summary,
            created_by=submitted_by_user_id,
            decided_at=now,
            selected_option=(response_shape.get("accepted") or "as_issued"),
            rationale="Party response captured as append-only commitment (spec §6).",
            matter_id=matter_id,
            matter_node_id=matter_node_id,
            fund_flow_path=fund_flow_path or [],
            is_commitment=True,
            originating_party_name=originating_party_name,
            response_shape=response_shape,
            in_response_to=in_response_to,
        )
        s.add(decision)
        s.flush()

        _log_event(
            s,
            decision=decision,
            user_id=submitted_by_user_id,
            action="created",
            old_status=None,
            new_status="decided",
            comment="commitment",
            metadata={
                "is_commitment": True,
                "originating_party_name": originating_party_name,
                "in_response_to": in_response_to,
            },
        )
        return decision

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------


def claim_decision(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    bulk_operation_id: uuid.UUID | None = None,
    session: Session | None = None,
) -> Decision:
    """Claim ownership: status → in_progress, snapshot authority + escalation.

    ``bulk_operation_id`` (Phase 8.5) — when set, it's added to the
    event's metadata so audit can later reconstruct every decision touched
    by a single bulk action via
    ``WHERE event_metadata->>'bulk_operation_id' = '<uuid>'``.
    """

    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")

        old_status = d.status
        if old_status == "in_progress" and d.owner_id == user_id:
            return d  # idempotent: already claimed by this user
        _check_transition(d, "in_progress")

        user = s.get(User, user_id)
        if user is None or user.tenant_id != d.tenant_id:
            raise DecisionAuthorityError("user not in decision's tenant")

        d.owner_id = user_id
        d.status = "in_progress"
        now = datetime.now(UTC)
        d.assigned_at = d.assigned_at or now
        d.acknowledged_at = now
        d.owner_authority_level = current_authority_level(
            session=s, user_id=user_id, workflow_id=d.workflow_id
        )
        d.escalation_path = compute_escalation_path(
            session=s,
            user_id=user_id,
            tenant_id=d.tenant_id,
            workflow_id=d.workflow_id,
        )

        metadata: dict[str, Any] | None = None
        if bulk_operation_id is not None:
            metadata = {"bulk_operation_id": str(bulk_operation_id)}

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="claimed",
            old_status=old_status,
            new_status="in_progress",
            metadata=metadata,
        )
        s.flush()
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Finalize
# ---------------------------------------------------------------------------


def finalize_decision(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    selected_option: str,
    rationale: str,
    evidence_refs: list[Any] | None = None,
    alternatives: list[Any] | None = None,
    session: Session | None = None,
) -> Decision:
    """Record the chosen action with rationale; gated by authority check."""

    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")
        _check_transition(d, "decided")

        ok, err = user_can_approve_action(
            session=s,
            user_id=user_id,
            workflow_id=d.workflow_id,
            action_id=selected_option,
        )
        if not ok:
            raise DecisionAuthorityError(err or "authority denied")

        old_status = d.status
        now = datetime.now(UTC)
        d.status = "decided"
        d.decided_at = now
        d.selected_option = selected_option
        d.rationale = rationale
        d.evidence_refs = evidence_refs
        d.alternatives = alternatives

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="finalized",
            old_status=old_status,
            new_status="decided",
            comment=selected_option,
            metadata={"rationale_len": len(rationale)},
        )
        s.flush()

        # Upstream review per TENANCY-MODEL §5: emit a 'promote' signal
        # to the parent matter node. Default behavior on_promote=notify
        # (all archetypes in v1) writes one decision_events row on the
        # source Decision and stops; if any archetype later declares
        # on_promote=gate, an upstream Decision is minted automatically.
        # No-op when the Decision isn't matter-bound.
        from reasonbook.upstream.dispatch import dispatch_upstream

        dispatch_upstream(
            source_decision=d,
            action_kind="promote",
            user_id=user_id,
            session=s,
        )

        # Control points (ADR-11): clear the matching pending CP at this
        # node. The trigger event depends on the finalizing decision's
        # archetype — `modification` clears on_modification, `adverse_action`
        # clears on_adverse_action, the matter's federal_archetype itself
        # clears on_promote, etc. Best-effort: legacy decisions without
        # matter context or matters whose CPs haven't been materialized
        # yet skip silently.
        from reasonbook.control_points import (
            clear as cp_clear,
        )
        from reasonbook.control_points import (
            find_pending_for_decision,
            trigger_event_for_decision,
        )
        from reasonbook.models import Matter

        if d.matter_id is not None:
            matter = s.get(Matter, d.matter_id)
            if matter is not None:
                trigger = trigger_event_for_decision(d, matter.federal_archetype)
                cp = find_pending_for_decision(d, trigger, session=s)
                if cp is not None:
                    cp_clear(cp.id, decision=d, user_id=user_id, session=s)
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Action stage
# ---------------------------------------------------------------------------


def record_action(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    artifacts: list[Any] | None = None,
    session: Session | None = None,
) -> Decision:
    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")
        if d.status != "decided":
            raise DecisionStateError("action can only be recorded on a decided decision")

        if started_at is not None:
            d.action_started_at = started_at
        if completed_at is not None:
            d.action_completed_at = completed_at
        if artifacts is not None:
            d.action_artifacts = artifacts

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="action_recorded",
            old_status="decided",
            new_status="decided",
        )
        s.flush()
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Outcome stage  (closes the decision)
# ---------------------------------------------------------------------------


def record_outcome(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    outcome_text: str,
    outcome_impact: str | None = None,
    outcome_metrics: dict[str, Any] | None = None,
    session: Session | None = None,
) -> Decision:
    if outcome_impact is not None and outcome_impact not in VALID_OUTCOMES:
        raise ValueError(f"invalid outcome_impact: {outcome_impact}")

    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")
        _check_transition(d, "closed")

        old_status = d.status
        now = datetime.now(UTC)
        d.outcome_text = outcome_text
        d.outcome_impact = outcome_impact
        d.outcome_metrics = outcome_metrics
        d.outcome_recorded_at = now
        d.closed_at = now
        d.status = "closed"

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="outcome_recorded",
            old_status=old_status,
            new_status="closed",
        )
        s.flush()

        # Upstream review (TENANCY-MODEL §5). action_kind='outcome'
        # defaults to notify across all archetypes today. Closeout
        # signals are emitted separately by callers that explicitly
        # record a closeout — outcome alone is not closeout.
        from reasonbook.upstream.dispatch import dispatch_upstream

        dispatch_upstream(
            source_decision=d,
            action_kind="outcome",
            user_id=user_id,
            session=s,
        )
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 5 — stage edits
#
# PATCH-style updates to anatomy-stage fields. Distinct from the POST
# transition endpoints (claim / finalize / record_action / record_outcome)
# which both set fields *and* advance status. Stage edits never advance
# status — they capture mid-stage corrections and post-stage tweaks.
#
# Authority rule (per amendment §4 task 2): edit stage N when stage N is
# the active or previous stage; not yet editable when stage N+1 fields
# are active. The uniform rule is encoded in EDITABLE_STAGES; per-decision-
# type overrides are noted as a v1.3 follow-up in amendment §8 watch list.
#
# signal_source is explicitly immutable (audit-trail integrity) — it's
# omitted from EDITABLE_STAGES["signal"]["fields"].
# ---------------------------------------------------------------------------


EDITABLE_STAGES: dict[str, dict[str, Any]] = {
    "signal": {
        "fields": ("signal_summary", "trigger_data"),
        # Stage 1 is reached at creation; editable in any reached state.
        "allowed_statuses": {
            "open",
            "assigned",
            "in_progress",
            "decided",
            "closed",
            "deferred",
            "escalated",
        },
    },
    "decision": {
        "fields": (
            "selected_option",
            "alternatives",
            "evidence_refs",
            "rationale",
        ),
        # Reached on claim (in_progress); previous-stage editable thereafter.
        "allowed_statuses": {"in_progress", "decided", "closed"},
    },
    "action": {
        "fields": (
            "action_started_at",
            "action_completed_at",
            "action_artifacts",
        ),
        # Reached after finalize.
        "allowed_statuses": {"decided", "closed"},
    },
    "outcome": {
        "fields": ("outcome_text", "outcome_impact", "outcome_metrics"),
        # Reached when outcome was recorded (status closed).
        "allowed_statuses": {"closed"},
    },
}


def _serialise_for_diff(value: Any) -> Any:
    """Coerce a field value into something JSON-storable for event_metadata."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def edit_stage(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    stage: str,
    updates: dict[str, Any],
    session: Session | None = None,
) -> Decision:
    """Apply a partial update to one anatomy stage's fields.

    Validates the requested ``stage`` is one of {signal, decision, action,
    outcome}, that every key in ``updates`` is editable for that stage, that
    the decision's current status has reached the stage, and that the user
    has any active authority on the workflow. Computes a diff of changed
    fields and writes a ``decision_events`` row with ``action='stage_edit'``
    carrying ``stage`` plus per-field old/new values in ``event_metadata``.

    Returns the updated decision. Status is never modified by this function —
    use the dedicated transition methods (claim / finalize / record_action /
    record_outcome) to advance the lifecycle.
    """
    if stage not in EDITABLE_STAGES:
        raise ValueError(f"unknown stage '{stage}' (allowed: {sorted(EDITABLE_STAGES)})")

    spec = EDITABLE_STAGES[stage]
    allowed_fields: tuple[str, ...] = spec["fields"]
    allowed_statuses: set[str] = spec["allowed_statuses"]

    rejected = [k for k in updates if k not in allowed_fields]
    if rejected:
        raise ValueError(
            f"fields {sorted(rejected)} are not editable on stage '{stage}' "
            f"(allowed: {list(allowed_fields)})"
        )
    if "signal_source" in updates:
        # Defensive — signal_source isn't in EDITABLE_STAGES so it'd already
        # raise above, but call out the audit-integrity reason explicitly.
        raise ValueError("signal_source is immutable after creation")

    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")

        if d.status not in allowed_statuses:
            raise DecisionStateError(
                f"stage '{stage}' is not yet editable on a decision in "
                f"status '{d.status}' (need one of: {sorted(allowed_statuses)})"
            )

        # Authority: any active authority on the workflow gates editing.
        # Per-decision-type overrides are a v1.3 follow-up per amendment §8.
        user_level = current_authority_level(session=s, user_id=user_id, workflow_id=d.workflow_id)
        if user_level is None:
            raise DecisionAuthorityError(f"no active authority for workflow '{d.workflow_id}'")

        diff: dict[str, dict[str, Any]] = {}
        for field, new_value in updates.items():
            old_value = getattr(d, field)
            if old_value == new_value:
                continue
            diff[field] = {
                "old": _serialise_for_diff(old_value),
                "new": _serialise_for_diff(new_value),
            }
            setattr(d, field, new_value)

        if not diff:
            # Nothing changed — silent no-op, no event row.
            return d

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="stage_edit",
            old_status=d.status,
            new_status=d.status,
            metadata={"stage": stage, "diff": diff},
        )
        s.flush()
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 7 — attachments
#
# Bridges the DecisionAttachment table (metadata) with the AttachmentStorage
# protocol (bytes). Append-only: soft-delete sets superseded_at on the row
# and asks the storage backend to drop the underlying bytes (idempotent).
# ---------------------------------------------------------------------------

VALID_ATTACHMENT_STAGES = {"signal", "decision", "action", "outcome", "evidence"}


def add_attachment(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    stage: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    content: BinaryIO,
    description: str | None = None,
    storage: AttachmentStorage | None = None,
    session: Session | None = None,
) -> DecisionAttachment:
    """Store the bytes via the storage backend, insert the metadata row,
    write an ``attachment_added`` event. Authority is gated by the API
    layer (any active workflow authority); this helper assumes that gate
    has already passed.
    """
    if stage not in VALID_ATTACHMENT_STAGES:
        raise ValueError(
            f"invalid attachment stage '{stage}' (allowed: {sorted(VALID_ATTACHMENT_STAGES)})"
        )

    backend: AttachmentStorage = storage if storage is not None else get_storage()

    def _do(s: Session) -> DecisionAttachment:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")

        ref: StorageRef = backend.put(decision_id, filename, content)

        att = DecisionAttachment(
            id=uuid.uuid4(),
            decision_id=decision_id,
            stage=stage,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            storage_uri=str(ref),
            storage_backend=ref.backend,
            uploaded_by=user_id,
            description=description,
        )
        s.add(att)
        s.flush()

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="attachment_added",
            old_status=d.status,
            new_status=d.status,
            metadata={
                "attachment_id": str(att.id),
                "stage": stage,
                "filename": filename,
                "size_bytes": size_bytes,
            },
        )
        return att

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        att = _do(managed)
        managed.expunge(att)
        return att


def list_attachments(
    decision_id: uuid.UUID, *, session: Session | None = None
) -> list[DecisionAttachment]:
    """Active (not superseded) attachments for a decision, oldest first."""

    def _q(s: Session) -> list[DecisionAttachment]:
        return (
            s.query(DecisionAttachment)
            .filter(DecisionAttachment.decision_id == decision_id)
            .filter(DecisionAttachment.superseded_at.is_(None))
            .order_by(DecisionAttachment.uploaded_at.asc())
            .all()
        )

    if session is not None:
        return _q(session)
    with session_scope() as managed:
        rows = _q(managed)
        for r in rows:
            managed.expunge(r)
        return rows


def get_attachment(
    attachment_id: uuid.UUID, *, session: Session | None = None
) -> DecisionAttachment | None:
    if session is not None:
        return session.get(DecisionAttachment, attachment_id)
    with session_scope() as managed:
        att = managed.get(DecisionAttachment, attachment_id)
        if att is not None:
            managed.expunge(att)
        return att


def supersede_attachment(
    *,
    decision_id: uuid.UUID,
    attachment_id: uuid.UUID,
    user_id: uuid.UUID,
    storage: AttachmentStorage | None = None,
    session: Session | None = None,
) -> DecisionAttachment:
    """Soft-delete an attachment: set ``superseded_at``, ask storage to drop
    the bytes (idempotent), write an ``attachment_removed`` event.
    """
    backend: AttachmentStorage = storage if storage is not None else get_storage()

    def _do(s: Session) -> DecisionAttachment:
        att = s.get(DecisionAttachment, attachment_id)
        if att is None or att.decision_id != decision_id:
            raise LookupError(f"attachment {attachment_id} not found on decision {decision_id}")
        if att.superseded_at is not None:
            return att  # idempotent

        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")

        # Reconstruct the StorageRef from the persisted URI.
        ref = _parse_storage_uri(att.storage_uri, att.storage_backend)
        backend.delete(ref)

        now = datetime.now(UTC)
        att.superseded_at = now

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="attachment_removed",
            old_status=d.status,
            new_status=d.status,
            metadata={
                "attachment_id": str(att.id),
                "stage": att.stage,
                "filename": att.filename,
            },
        )
        s.flush()
        return att

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        att = _do(managed)
        managed.expunge(att)
        return att


def _parse_storage_uri(uri: str, backend_name: str) -> StorageRef:
    """Inverse of ``StorageRef.__str__`` — reconstruct from the persisted URI."""
    if backend_name == "local":
        # "local://{path}"
        return StorageRef(backend="local", path=uri.removeprefix("local://"))
    if backend_name == "do_spaces":
        # "do_spaces://{bucket}/{path}"
        rest = uri.removeprefix("do_spaces://")
        bucket, _, path = rest.partition("/")
        return StorageRef(backend="do_spaces", bucket=bucket, path=path)
    if backend_name == "pg_lo":
        oid_str = uri.removeprefix("pg_lo://")
        return StorageRef(backend="pg_lo", path="", oid=int(oid_str))
    return StorageRef(backend=backend_name, path=uri)


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 7 — comments
#
# Comments are events on the decision_events table per amendment §3.2 — no
# DDL change. action='comment', body in the existing `comment` column,
# {stage_context, mentions} in event_metadata. The audit-default of
# get_events excludes them so the existing audit-log surface stays clean.
# ---------------------------------------------------------------------------


VALID_COMMENT_STAGES = {"signal", "decision", "action", "outcome", "general"}


def post_comment(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    body: str,
    stage_context: str = "general",
    mentions: list[uuid.UUID] | None = None,
    bulk_operation_id: uuid.UUID | None = None,
    session: Session | None = None,
) -> DecisionEvent:
    """Append a comment event. Stored as ``action='comment'`` with the body
    in the existing ``comment`` Text column and ``{stage_context, mentions}``
    in ``event_metadata`` per amendment §3.2.

    ``bulk_operation_id`` (Phase 8.5) — when set, it's added to the event's
    metadata for bulk-action audit reconstruction.
    """
    if not body or not body.strip():
        raise ValueError("comment body is empty")
    if stage_context not in VALID_COMMENT_STAGES:
        raise ValueError(
            f"invalid stage_context '{stage_context}' (allowed: {sorted(VALID_COMMENT_STAGES)})"
        )
    mention_strs = [str(m) for m in (mentions or [])]

    metadata: dict[str, Any] = {
        "stage_context": stage_context,
        "mentions": mention_strs,
    }
    if bulk_operation_id is not None:
        metadata["bulk_operation_id"] = str(bulk_operation_id)

    def _do(s: Session) -> DecisionEvent:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")

        event = DecisionEvent(
            id=uuid.uuid4(),
            decision_id=decision_id,
            tenant_id=d.tenant_id,
            workflow_id=d.workflow_id,
            user_id=user_id,
            action="comment",
            old_status=d.status,
            new_status=d.status,
            comment=body,
            event_metadata=metadata,
        )
        s.add(event)
        s.flush()
        return event

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        e = _do(managed)
        managed.expunge(e)
        return e


# ---------------------------------------------------------------------------
# Side states
# ---------------------------------------------------------------------------


def defer_decision(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    reopen_at: datetime | None = None,
    session: Session | None = None,
) -> Decision:
    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")
        _check_transition(d, "deferred")

        old_status = d.status
        d.status = "deferred"
        d.defer_reason = reason
        d.defer_reopen_at = reopen_at

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="deferred",
            old_status=old_status,
            new_status="deferred",
            comment=reason,
        )
        s.flush()
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d


def escalate_decision(
    *,
    decision_id: uuid.UUID,
    user_id: uuid.UUID,
    reason: str,
    escalated_to: uuid.UUID | None = None,
    session: Session | None = None,
) -> Decision:
    def _do(s: Session) -> Decision:
        d = s.get(Decision, decision_id)
        if d is None:
            raise LookupError(f"decision {decision_id} not found")
        _check_transition(d, "escalated")

        old_status = d.status
        d.status = "escalated"
        d.escalation_reason = reason
        if escalated_to is not None:
            d.escalated_to = escalated_to

        _log_event(
            s,
            decision=d,
            user_id=user_id,
            action="escalated",
            old_status=old_status,
            new_status="escalated",
            comment=reason,
        )
        s.flush()
        return d

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        d = _do(managed)
        managed.expunge(d)
        return d
