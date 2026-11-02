# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Decision lifecycle API."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, BinaryIO, cast

from flask import Blueprint, Response, g, jsonify, make_response, redirect, request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.decisions.authority import current_authority_level, user_can_create_decision_type
from reasonbook.decisions.manager import (
    DecisionAuthorityError,
    DecisionStateError,
    add_attachment,
    claim_decision,
    create_decision,
    defer_decision,
    edit_stage,
    escalate_decision,
    finalize_decision,
    get_attachment,
    get_decision,
    get_events,
    list_attachments,
    post_comment,
    record_action,
    record_outcome,
    supersede_attachment,
)
from reasonbook.decisions.scope import (
    AT_RISK_CATEGORY_BY_WORKFLOW,
    apply_archetype_filter,
    apply_density,
    apply_paginate,
    apply_scope,
    apply_sort,
    apply_stage,
    apply_tier_scope,
    apply_workflow_filter,
    at_risk_filter,
    open_filter,
)
from reasonbook.models import Decision, DecisionEvent, User
from reasonbook.storage.attachments import get_storage

log = logging.getLogger(__name__)

bp = Blueprint("decisions", __name__)

# Workflows the queue endpoint never returns. Oversight decisions have
# their own surface; the operational queue is what an agency reviewer
# is looking at here.
_QUEUE_EXCLUDED_WORKFLOWS = ("10-oversight",)


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


_OVERSIGHT_WORKFLOW_ID = "10-oversight"
# Activity codes that count as committee endorsement. New writes use the
# committee-flavored values; ratified_by_board / ratified_by_committee
# stay in the predicate so the historical audit reads continue to work.
_COMMITTEE_ENDORSEMENT_ACTIONS = (
    "endorsed_by_committee",
    "noted_by_committee",
    "ratified_by_committee",
    "ratified_by_board",  # legacy carryover from banking era
)


def _compute_awaiting_committee(session: Session, decisions: list[Decision]) -> set[uuid.UUID]:
    """Return the subset of oversight `decided` decision ids that have
    NOT yet been endorsed by the committee. Batch query — one round-trip
    regardless of page size."""
    oversight_decided_ids = [
        d.id for d in decisions if d.workflow_id == _OVERSIGHT_WORKFLOW_ID and d.status == "decided"
    ]
    if not oversight_decided_ids:
        return set()
    endorsed = {
        row[0]
        for row in session.query(DecisionEvent.decision_id)
        .filter(DecisionEvent.action.in_(_COMMITTEE_ENDORSEMENT_ACTIONS))
        .filter(DecisionEvent.decision_id.in_(oversight_decided_ids))
        .distinct()
        .all()
    }
    return set(oversight_decided_ids) - endorsed


def _is_awaiting_committee_endorsement(d: Decision, session: Session) -> bool:
    """Single-decision variant of ``_compute_awaiting_committee``. True
    iff this is an oversight `decided` decision with no endorsement event yet."""
    if d.workflow_id != _OVERSIGHT_WORKFLOW_ID or d.status != "decided":
        return False
    row = (
        session.query(DecisionEvent.id)
        .filter(
            DecisionEvent.decision_id == d.id,
            DecisionEvent.action.in_(_COMMITTEE_ENDORSEMENT_ACTIONS),
        )
        .first()
    )
    return row is None


def _decision_dict(d: Decision, *, awaiting_committee_endorsement: bool = False) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "decision_number": d.decision_number,
        "tenant_id": d.tenant_id,
        "workflow_id": d.workflow_id,
        "decision_type": d.decision_type,
        "title": d.title,
        "description": d.description,
        "priority": d.priority,
        "severity": d.severity,
        "status": d.status,
        "sla_hours": d.sla_hours,
        "sla_deadline": d.sla_deadline.isoformat() if d.sla_deadline else None,
        "sla_status": d.sla_status,
        # Signal
        "signal_captured_at": d.signal_captured_at.isoformat() if d.signal_captured_at else None,
        "signal_source": d.signal_source,
        "signal_summary": d.signal_summary,
        "trigger_data": d.trigger_data,
        # Owner
        "owner_id": str(d.owner_id) if d.owner_id else None,
        "created_by": str(d.created_by) if d.created_by else None,
        "assigned_at": d.assigned_at.isoformat() if d.assigned_at else None,
        "acknowledged_at": d.acknowledged_at.isoformat() if d.acknowledged_at else None,
        "owner_authority_level": d.owner_authority_level,
        "escalation_path": d.escalation_path,
        # Decision
        "decided_at": d.decided_at.isoformat() if d.decided_at else None,
        "selected_option": d.selected_option,
        "alternatives": d.alternatives,
        "evidence_refs": d.evidence_refs,
        "rationale": d.rationale,
        # Action
        "action_started_at": d.action_started_at.isoformat() if d.action_started_at else None,
        "action_completed_at": d.action_completed_at.isoformat() if d.action_completed_at else None,
        "action_artifacts": d.action_artifacts,
        # Outcome
        "outcome_recorded_at": d.outcome_recorded_at.isoformat() if d.outcome_recorded_at else None,
        "outcome_text": d.outcome_text,
        "outcome_impact": d.outcome_impact,
        "outcome_metrics": d.outcome_metrics,
        "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        # Side states
        "defer_reason": d.defer_reason,
        "defer_reopen_at": d.defer_reopen_at.isoformat() if d.defer_reopen_at else None,
        "escalated_to": str(d.escalated_to) if d.escalated_to else None,
        "escalation_reason": d.escalation_reason,
        # Commitment fields (spec §6) — populated when the Decision was
        # written via the recipient/state response endpoint. NULL / False
        # on internally-authored decisions.
        "is_commitment": d.is_commitment,
        "originating_party_name": d.originating_party_name,
        "response_shape": d.response_shape,
        "in_response_to": d.in_response_to,
        # Misc
        "decision_payload": d.decision_payload,
        "tags": d.tags,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
        # Tenancy / matter membership (TENANCY-MODEL §11). NULL on
        # legacy / pre-matter decisions; populated once the matter
        # service mints the Decision through create_matter.
        "matter_id": str(d.matter_id) if d.matter_id else None,
        "matter_node_id": str(d.matter_node_id) if d.matter_node_id else None,
        "fund_flow_path": [str(p) for p in (d.fund_flow_path or [])],
        # Oversight extensions (NULL on operational decisions)
        "oversight_cycle_id": str(d.oversight_cycle_id) if d.oversight_cycle_id else None,
        "target_outcome": d.target_outcome,
        "actual_outcome": d.actual_outcome,
        "outcome_captured_by": str(d.outcome_captured_by) if d.outcome_captured_by else None,
        # True only for oversight decisions in `decided` that haven't yet
        # been endorsed by the committee. Drives Inbox grouping + the
        # dashboard cycle card "still in flight" semantics.
        "awaiting_committee_endorsement": awaiting_committee_endorsement,
    }


def _event_dict(
    e: DecisionEvent,
    user_lookup: dict[uuid.UUID, User] | None = None,
) -> dict[str, Any]:
    user = user_lookup.get(e.user_id) if (user_lookup and e.user_id) else None
    return {
        "id": str(e.id),
        "decision_id": str(e.decision_id),
        "tenant_id": e.tenant_id,
        "workflow_id": e.workflow_id,
        "user_id": str(e.user_id) if e.user_id else None,
        "user_name": user.name if user else None,
        "user_username": user.username if user else None,
        "action": e.action,
        "old_status": e.old_status,
        "new_status": e.new_status,
        "comment": e.comment,
        "metadata": e.event_metadata,
        "created_at": e.created_at.isoformat(),
    }


def _user_lookup_for_events(events: list[DecisionEvent], session: Any) -> dict[uuid.UUID, User]:
    """Bulk-fetch User rows for the user_ids referenced by ``events``.

    One query, used to enrich event responses with author display names so
    the comments thread can render real names instead of falling back to a
    generic placeholder.
    """
    user_ids = {e.user_id for e in events if e.user_id is not None}
    if not user_ids:
        return {}
    rows = session.query(User).filter(User.id.in_(user_ids)).all()
    return {u.id: u for u in rows}


def _resolve_id(decision_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(decision_id)
    except (ValueError, TypeError):
        return None


def _enforce_visibility(d: Decision) -> tuple[Response, int] | None:
    """Return a (Response, status) tuple if the caller must NOT see this decision."""
    auth = g.auth
    if d.tenant_id != auth.tenant:
        return jsonify({"error": "not found"}), 404  # don't leak existence
    return None


# ---------------------------------------------------------------------------
# List + create
# ---------------------------------------------------------------------------


@bp.get("/decisions")
@require_auth
def list_decisions() -> tuple[Response, int]:
    auth = g.auth
    args = request.args
    scope = args.get("scope", "all_entitled")
    density = args.get("density", "active")
    stage = args.get("stage")
    workflow_id = args.get("workflow_id")
    archetype_id = args.get("archetype")
    # Default sort omitted → apply_sort's due-date-forward branch runs
    # (sla_deadline asc, nulls last, created_at desc tiebreak). Callers
    # can still opt back into "newest" / "oldest" / "priority" / etc.
    sort = args.get("sort")
    limit = int(args.get("limit", "50"))
    offset = int(args.get("offset", "0"))

    with session_scope() as session:
        q = session.query(Decision)
        q = apply_scope(
            q,
            scope=scope,
            user_id=uuid.UUID(auth.sub),
            tenant_id=auth.tenant,
            session=session,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
            primary_agency_id=(
                uuid.UUID(auth.agency_id) if auth.agency_id else None
            ),
        )
        q = apply_workflow_filter(q, workflow_id)
        q = apply_archetype_filter(q, archetype_id)
        q = apply_stage(q, stage)
        q = apply_density(q, density)
        q = apply_sort(q, sort)

        total = q.count()
        rows = apply_paginate(q, limit=limit, offset=offset).all()
        awaiting_committee_ids = _compute_awaiting_committee(session, rows)
        items = [
            _decision_dict(
                r,
                awaiting_committee_endorsement=r.id in awaiting_committee_ids,
            )
            for r in rows
        ]

    return (
        jsonify(
            {
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
                "scope": scope,
                "density": density,
                "stage": stage,
                "workflow_id": workflow_id,
                "archetype": archetype_id,
                "sort": sort,
            }
        ),
        200,
    )


@bp.get("/decisions/queue")
@require_auth
def queue() -> tuple[Response, int]:
    """P17 — decision-queue endpoint backing the dashboard drawer.

    A narrower, faster-to-serialise sibling of ``GET /decisions``. The drawer
    needs only the columns its row renders (decision number, category, title,
    SLA, assignee initials), not the full anatomy payload — and the SLA-window
    cutoffs here are inclusive of past-due decisions where the inbox might
    exclude them.

    Query params:
      - ``status`` (required): ``at_risk`` | ``open``. ``at_risk`` reuses
        ``at_risk_filter()`` from ``reasonbook.decisions.scope`` so the count tied
        to the dashboard's top-rail tile and the count rendered in the
        drawer never drift.
      - ``category`` (optional): ``credit`` | ``compliance`` | ``ops``. Maps
        to a set of workflows via ``AT_RISK_CATEGORY_BY_WORKFLOW``.
      - ``limit`` (default 50) / ``offset`` (default 0).

    Scope: implicit ``all_entitled`` — the queue is institutional, not
    per-owner. Apex is excluded; its decisions surface under ``/apex/...``.

    Sort: SLA deadline ASC nulls-last, created_at DESC tiebreak — most
    urgent first.

    Response shape: ``{decisions, total_count, filtered_count, next_cursor,
    posture_context?}``. ``posture_context`` is only present when the
    request asked for at-risk decisions and the filtered list is empty —
    powering the "All clear" empty state with three context stats.
    """
    auth = g.auth
    args = request.args
    status = args.get("status", "at_risk")
    if status not in ("at_risk", "open"):
        return jsonify({"error": "status must be 'at_risk' or 'open'"}), 400

    category = args.get("category")
    if category is not None and category not in {"credit", "compliance", "ops"}:
        return jsonify({"error": "category must be one of credit, compliance, ops"}), 400

    try:
        limit = int(args.get("limit", "50"))
        offset = int(args.get("offset", "0"))
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400
    limit = max(1, min(200, limit))
    offset = max(0, offset)

    category_workflows: list[str] | None = None
    if category is not None:
        category_workflows = [
            wid
            for wid, cat in AT_RISK_CATEGORY_BY_WORKFLOW.items()
            if cat == category
        ]

    with session_scope() as session:
        # Row-level tenancy scope: federal sees all; state/recipient see
        # only their slice of fund_flow_path. Single chokepoint per
        # TENANCY-MODEL.md §3.
        base_q = apply_tier_scope(
            session.query(Decision),
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
        ).filter(
            Decision.tenant_id == auth.tenant,
            Decision.workflow_id.notin_(_QUEUE_EXCLUDED_WORKFLOWS),
        )
        status_filter = at_risk_filter() if status == "at_risk" else open_filter()
        base_q = base_q.filter(status_filter)

        total_count = base_q.count()

        filtered_q = base_q
        if category_workflows is not None:
            filtered_q = filtered_q.filter(Decision.workflow_id.in_(category_workflows or [""]))

        filtered_count = filtered_q.count()

        rows = (
            filtered_q.order_by(
                Decision.sla_deadline.asc().nullslast(),
                Decision.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
            .all()
        )

        # Bulk-fetch owner User rows for the page's owner_ids in one query
        # so we can stamp assignee {name, initials} on each row.
        owner_ids = {r.owner_id for r in rows if r.owner_id is not None}
        owner_lookup: dict[uuid.UUID, User] = {}
        if owner_ids:
            for u in session.query(User).filter(User.id.in_(owner_ids)).all():
                owner_lookup[u.id] = u

        decisions = [_queue_row(r, owner_lookup) for r in rows]

        body: dict[str, Any] = {
            "decisions": decisions,
            "total_count": int(total_count),
            "filtered_count": int(filtered_count),
            "next_cursor": None,
            "status": status,
            "category": category,
        }

        # Empty-state posture context: only relevant for at-risk + empty.
        # Powers the drawer's "All clear" stats block; calling sites that
        # show the open-population queue don't need it.
        if status == "at_risk" and filtered_count == 0:
            body["posture_context"] = _queue_posture_context(session, auth.tenant)

    return jsonify(body), 200


def _queue_row(d: Decision, owners: dict[uuid.UUID, User]) -> dict[str, Any]:
    """Slim row shape per D1 (real fields). Drops anatomy + JSONB blobs
    the inbox list endpoint returns — the drawer doesn't render them."""
    category = AT_RISK_CATEGORY_BY_WORKFLOW.get(d.workflow_id)
    assignee: dict[str, Any] | None = None
    if d.owner_id is not None:
        owner = owners.get(d.owner_id)
        if owner is not None:
            assignee = {
                "id": str(owner.id),
                "name": owner.name or owner.username,
                "initials": _initials(owner.name or owner.username),
            }
    return {
        "id": str(d.id),
        "decision_number": d.decision_number,
        "workflow_id": d.workflow_id,
        "category": category,
        "title": d.title,
        # Surfaced for the row's hover popover. May be null on bare-bones
        # decisions; the popover degrades to title-only in that case.
        "description": d.description,
        "sla_deadline": d.sla_deadline.isoformat() if d.sla_deadline else None,
        "sla_status": d.sla_status,
        "status": d.status,
        "assignee": assignee,
    }


def _initials(name: str) -> str:
    """Two-letter monogram for the assignee badge. Falls back to the
    first two letters of the source string when there's only one token."""
    parts = [p for p in name.replace(",", " ").split() if p]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _queue_posture_context(session: Session, tenant_id: str) -> dict[str, Any]:
    """Three stats for the drawer's "All clear" empty state:

    - open_count: total decisions in the open population (agency-wide,
      minus the queue-excluded workflows). Anchors the "65 open"
      reassurance.
    - avg_cycle_days: mean (decided_at - created_at) in days for the
      trailing 30 days. None when there's no decided population. Same
      window the dashboard's DECIDED tile uses, so the framing reads
      consistently between surfaces.
    - upcoming_count_48h: open decisions whose SLA deadline is in the
      (now+24h, now+48h] window — i.e., NOT currently at-risk but the
      next batch to watch.
    """
    now = datetime.now(UTC)
    window_24h = now + timedelta(hours=24)
    window_48h = now + timedelta(hours=48)
    window_30d_ago = now - timedelta(days=30)

    open_count = session.execute(
        select(func.count(Decision.id))
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.notin_(_QUEUE_EXCLUDED_WORKFLOWS))
        .where(open_filter())
    ).scalar_one()

    cycle_seconds = session.execute(
        select(
            func.avg(
                func.extract("epoch", Decision.decided_at)
                - func.extract("epoch", Decision.created_at)
            )
        )
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.notin_(_QUEUE_EXCLUDED_WORKFLOWS))
        .where(Decision.decided_at.isnot(None))
        .where(Decision.decided_at >= window_30d_ago)
    ).scalar_one()
    avg_cycle_days = round(float(cycle_seconds) / 86400.0, 1) if cycle_seconds is not None else None

    upcoming = session.execute(
        select(func.count(Decision.id))
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.notin_(_QUEUE_EXCLUDED_WORKFLOWS))
        .where(open_filter())
        .where(Decision.sla_deadline.isnot(None))
        .where(Decision.sla_deadline > window_24h)
        .where(Decision.sla_deadline <= window_48h)
    ).scalar_one()

    return {
        "open_count": int(open_count),
        "avg_cycle_days": avg_cycle_days,
        "upcoming_count_48h": int(upcoming),
    }


@bp.post("/decisions")
@require_auth
def create() -> tuple[Response, int]:
    """Manual decision creation per Phase 7.5 Gate 4.

    Always treated as a manual-creation request — the ingestion job
    path goes through ``manager.create_decision`` directly, never this HTTP
    endpoint. The server therefore:

      - overrides whatever ``signal_source`` the body provides with
        ``f"manual.{user_id}.{uuid7}"`` (uniqueness + audit-trail discipline),
      - gates via ``user_can_create_decision_type`` so a user can't manually
        originate a decision type that's auto-only or above their authority.
    """
    auth = g.auth
    body = request.get_json(silent=True) or {}

    workflow_id = body.get("workflow_id")
    if not workflow_id:
        return jsonify({"error": "workflow_id required"}), 400

    decision_type_id = body.get("decision_type")
    if not decision_type_id:
        return jsonify({"error": "missing field: decision_type"}), 400

    user_id = uuid.UUID(auth.sub)

    with session_scope() as authz_session:
        allowed, reason = user_can_create_decision_type(
            session=authz_session,
            user_id=user_id,
            workflow_id=workflow_id,
            decision_type_id=decision_type_id,
        )
    if not allowed:
        return jsonify({"error": reason or "not allowed"}), 403

    # Server overrides signal_source regardless of body input. The `manual.`
    # prefix is the dedup discipline — it's how `runner._has_open_decision_for_signal`
    # knows to skip the dedup query for human-originated decisions. The
    # amendment spec calls for a uuid7 here; stdlib uuid7 isn't available in
    # 3.13 yet, so we use uuid4 — the value's only job is uniqueness for the
    # dedup invariant, which uuid4 satisfies.
    signal_source = f"manual.{user_id}.{uuid.uuid4()}"

    try:
        d = create_decision(
            tenant_id=auth.tenant,
            workflow_id=workflow_id,
            decision_type=decision_type_id,
            title=body["title"],
            created_by=user_id,
            description=body.get("description"),
            priority=body.get("priority", "medium"),
            sla_hours=body.get("sla_hours"),
            owner_id=uuid.UUID(body["owner_id"]) if body.get("owner_id") else None,
            trigger_data=body.get("trigger_data"),
            signal_source=signal_source,
            signal_summary=body.get("signal_summary"),
            decision_payload=body.get("decision_payload"),
            tags=body.get("tags"),
        )
    except KeyError as exc:
        return jsonify({"error": f"missing field: {exc.args[0]}"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_decision_dict(d)), 201


# ---------------------------------------------------------------------------
# Single decision read
# ---------------------------------------------------------------------------


@bp.get("/decisions/<decision_id>")
@require_auth
def detail(decision_id: str) -> tuple[Response, int]:
    did = _resolve_id(decision_id)
    if did is None:
        return jsonify({"error": "invalid decision id"}), 400

    with session_scope() as session:
        d = session.get(Decision, did)
        if d is None:
            return jsonify({"error": "not found"}), 404
        forbidden = _enforce_visibility(d)
        if forbidden is not None:
            return forbidden
        body = _decision_dict(
            d,
            awaiting_committee_endorsement=_is_awaiting_committee_endorsement(d, session),
        )

    return jsonify(body), 200


@bp.get("/decisions/<decision_id>/export")
@require_auth
def export_pdf(decision_id: str) -> Response:
    """Stream the decision-record PDF as a download.

    Format query param is currently ignored; PDF is the only supported
    format. Future: ?format=html for inline previews, ?format=md for
    machine-readable export.
    """
    did = _resolve_id(decision_id)
    if did is None:
        resp = jsonify({"error": "invalid decision id"})
        resp.status_code = 400
        return resp

    with session_scope() as session:
        d = session.get(Decision, did)
        if d is None:
            resp = jsonify({"error": "not found"})
            resp.status_code = 404
            return resp
        forbidden = _enforce_visibility(d)
        if forbidden is not None:
            inner_resp, status = forbidden
            inner_resp.status_code = status
            return inner_resp
        decision_number = d.decision_number

    from reasonbook.reports import generate_decision_record_pdf

    pdf_bytes = generate_decision_record_pdf(did)
    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="decision-record-{decision_number}.pdf"'
    )
    return resp


@bp.get("/decisions/<decision_id>/events")
@require_auth
def events(decision_id: str) -> tuple[Response, int]:
    """Phase 7.5 Gate 7: ``include=audit|comments|all`` filters by the
    comment convention. Default is ``audit`` so the audit-log surface that
    existed before Gate 7 keeps its shape — comments live alongside
    transitions on the same table but are excluded by default.
    """
    did = _resolve_id(decision_id)
    if did is None:
        return jsonify({"error": "invalid decision id"}), 400

    include = request.args.get("include", "audit")
    if include not in {"audit", "comments", "all"}:
        return jsonify({"error": "include must be one of: audit, comments, all"}), 400

    with session_scope() as session:
        d = session.get(Decision, did)
        if d is None:
            return jsonify({"error": "not found"}), 404
        forbidden = _enforce_visibility(d)
        if forbidden is not None:
            return forbidden
        rows = get_events(did, include=include, session=session)  # type: ignore[arg-type]
        users = _user_lookup_for_events(rows, session)
        body = [_event_dict(r, users) for r in rows]

    return jsonify({"items": body}), 200


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


def _require_visible_decision(
    decision_id: str,
) -> tuple[uuid.UUID | None, tuple[Response, int] | None]:
    did = _resolve_id(decision_id)
    if did is None:
        return None, (jsonify({"error": "invalid decision id"}), 400)
    with session_scope() as session:
        d = session.get(Decision, did)
        if d is None:
            return None, (jsonify({"error": "not found"}), 404)
        forbidden = _enforce_visibility(d)
        if forbidden is not None:
            return None, forbidden
    return did, None


@bp.post("/decisions/<decision_id>/claim")
@require_auth
def claim(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    try:
        d = claim_decision(decision_id=did, user_id=uuid.UUID(g.auth.sub))
    except DecisionStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except DecisionAuthorityError as exc:
        return jsonify({"error": str(exc)}), 403
    return jsonify(_decision_dict(d)), 200


@bp.post("/decisions/<decision_id>/finalize")
@require_auth
def finalize(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    body = request.get_json(silent=True) or {}
    selected = body.get("selected_option")
    rationale = body.get("rationale")
    if not selected or not rationale:
        return jsonify({"error": "selected_option and rationale required"}), 400

    try:
        d = finalize_decision(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            selected_option=selected,
            rationale=rationale,
            evidence_refs=body.get("evidence_refs"),
            alternatives=body.get("alternatives"),
        )
    except DecisionStateError as exc:
        return jsonify({"error": str(exc)}), 409
    except DecisionAuthorityError as exc:
        return jsonify({"error": str(exc)}), 403

    # Post-finalize hook: when a designated_respondent_change decision is
    # declined by the receiving respondent, drop a follow-up decision in
    # the original designator's Inbox prompting reassignment, per
    # decision-governance-self-assessment-platform-variant-v1_0.md §3.1.
    # The FK does NOT auto-revert; the institution stays in an
    # acknowledged-declined state until the admin reassigns.
    followup_id = _maybe_drop_decline_followup(d, selected)
    body_dict = _decision_dict(d)
    if followup_id is not None:
        body_dict["followup_decision_id"] = str(followup_id)
    return jsonify(body_dict), 200


def _maybe_drop_decline_followup(d: Any, selected_option: str) -> uuid.UUID | None:
    """If a designated_respondent_change decision was just declined, create a
    follow-up decision in the original designator's Inbox prompting them to
    pick a new respondent. Returns the follow-up decision id (or None).

    Self-attested declines have no designator to receive the follow-up —
    we skip the create and log a warning. The FK still points at the
    declining user; an admin needs to intervene.
    """
    if d.workflow_id != "user-configuration":
        return None
    if d.decision_type != "designated_respondent_change":
        return None
    if selected_option != "decline":
        return None

    payload = d.decision_payload or {}
    designator_raw = payload.get("designated_by_user_id")
    if not designator_raw:
        log.warning(
            "designated_respondent_change declined with no designator "
            "(self-attestation path); FK left pointing at declining user — "
            "tenant=%s decision=%s",
            d.tenant_id,
            d.id,
        )
        return None

    try:
        designator_id = uuid.UUID(designator_raw)
    except (TypeError, ValueError):
        log.warning("invalid designated_by_user_id on declined decision %s", d.id)
        return None

    followup = create_decision(
        tenant_id=d.tenant_id,
        workflow_id="user-configuration",
        decision_type="designated_respondent_change",
        title="Designation declined — reassign senior governance leader",
        priority="high",
        sla_hours=336,
        owner_id=designator_id,
        created_by=designator_id,
        decision_payload={
            "follow_up_to_decision_id": str(d.id),
            "declined_by_user_id": str(d.owner_id) if d.owner_id else None,
            "reason": "Previous designation declined; please pick another respondent or self-attest.",
        },
    )
    return followup.id


@bp.post("/decisions/<decision_id>/defer")
@require_auth
def defer(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    body = request.get_json(silent=True) or {}
    reason = body.get("reason")
    if not reason:
        return jsonify({"error": "reason required"}), 400

    from datetime import datetime as dt

    reopen = body.get("reopen_at")
    reopen_dt = dt.fromisoformat(reopen) if reopen else None

    try:
        d = defer_decision(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            reason=reason,
            reopen_at=reopen_dt,
        )
    except DecisionStateError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(_decision_dict(d)), 200


@bp.post("/decisions/<decision_id>/escalate")
@require_auth
def escalate(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    body = request.get_json(silent=True) or {}
    reason = body.get("reason")
    if not reason:
        return jsonify({"error": "reason required"}), 400
    target_raw = body.get("escalated_to")
    target = uuid.UUID(target_raw) if target_raw else None

    try:
        d = escalate_decision(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            reason=reason,
            escalated_to=target,
        )
    except DecisionStateError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(_decision_dict(d)), 200


@bp.post("/decisions/<decision_id>/action")
@require_auth
def action(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    body = request.get_json(silent=True) or {}
    from datetime import datetime as dt

    started = body.get("started_at")
    completed = body.get("completed_at")
    started_dt = dt.fromisoformat(started) if started else None
    completed_dt = dt.fromisoformat(completed) if completed else None

    try:
        d = record_action(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            started_at=started_dt,
            completed_at=completed_dt,
            artifacts=body.get("artifacts"),
        )
    except DecisionStateError as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(_decision_dict(d)), 200


@bp.post("/decisions/<decision_id>/outcome")
@require_auth
def outcome(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    body = request.get_json(silent=True) or {}
    text = body.get("outcome_text")
    if not text:
        return jsonify({"error": "outcome_text required"}), 400

    try:
        d = record_outcome(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            outcome_text=text,
            outcome_impact=body.get("outcome_impact"),
            outcome_metrics=body.get("outcome_metrics"),
        )
    except (ValueError, DecisionStateError) as exc:
        return jsonify({"error": str(exc)}), 409
    return jsonify(_decision_dict(d)), 200


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 5 — PATCH stage edits
#
# Parallel to the POST transition endpoints (claim / finalize / action /
# outcome) but never advances status. Each endpoint maps to one anatomy
# stage; the manager validates stage-readiness, computes a diff, and writes
# an ``action='stage_edit'`` decision event with the diff in event_metadata.
#
# `signal_source` is immutable post-creation (audit-trail integrity) — it
# isn't in the editable-fields list and the manager rejects it explicitly.
# ---------------------------------------------------------------------------


def _patch_stage(decision_id: str, stage: str, body: dict[str, Any]) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    try:
        d = edit_stage(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            stage=stage,
            updates=body,
        )
    except DecisionAuthorityError as exc:
        return jsonify({"error": str(exc)}), 403
    except DecisionStateError as exc:
        # DecisionStateError subclasses ValueError, so it must come first.
        return jsonify({"error": str(exc)}), 409
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_decision_dict(d)), 200


def _stage_payload_from_body(body: dict[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
    """Pick only allowed keys; ISO-decode datetime strings for action stage."""
    payload: dict[str, Any] = {}
    for key in allowed:
        if key not in body:
            continue
        value = body[key]
        if key in {"action_started_at", "action_completed_at"} and isinstance(value, str):
            from datetime import datetime as _dt

            try:
                value = _dt.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{key} must be ISO 8601") from exc
        payload[key] = value
    return payload


@bp.patch("/decisions/<decision_id>/signal")
@require_auth
def patch_signal(decision_id: str) -> tuple[Response, int]:
    body = request.get_json(silent=True) or {}
    if "signal_source" in body:
        return jsonify({"error": "signal_source is immutable after creation"}), 400
    try:
        payload = _stage_payload_from_body(body, ("signal_summary", "trigger_data"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _patch_stage(decision_id, "signal", payload)


@bp.patch("/decisions/<decision_id>/decision")
@require_auth
def patch_decision(decision_id: str) -> tuple[Response, int]:
    body = request.get_json(silent=True) or {}
    try:
        payload = _stage_payload_from_body(
            body, ("selected_option", "alternatives", "evidence_refs", "rationale")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _patch_stage(decision_id, "decision", payload)


@bp.patch("/decisions/<decision_id>/action")
@require_auth
def patch_action(decision_id: str) -> tuple[Response, int]:
    body = request.get_json(silent=True) or {}
    try:
        payload = _stage_payload_from_body(
            body, ("action_started_at", "action_completed_at", "action_artifacts")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _patch_stage(decision_id, "action", payload)


@bp.patch("/decisions/<decision_id>/outcome")
@require_auth
def patch_outcome(decision_id: str) -> tuple[Response, int]:
    body = request.get_json(silent=True) or {}
    try:
        payload = _stage_payload_from_body(
            body, ("outcome_text", "outcome_impact", "outcome_metrics")
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _patch_stage(decision_id, "outcome", payload)


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 7 — attachments + comments
#
# Attachments are stored via the storage protocol (Gate 3) with metadata in
# platform.decision_attachments. Comments are stored on platform.decision_events
# with action='comment' per the §3.2 convention — no DDL change. Both
# require any active workflow authority on the decision's workflow.
# ---------------------------------------------------------------------------


def _require_workflow_authority(decision: Decision) -> tuple[Response, int] | None:
    """Returns a 403 response if the caller has no active authority on the
    decision's workflow. Pairs with _enforce_visibility (which checks tenant
    + entitlement) for the stricter Gate 7 surfaces — comments / attachments
    must come from someone with skin in the workflow."""
    user_id = uuid.UUID(g.auth.sub)
    with session_scope() as session:
        level = current_authority_level(
            session=session, user_id=user_id, workflow_id=decision.workflow_id
        )
    if level is None:
        return (
            jsonify({"error": f"no active authority for workflow '{decision.workflow_id}'"}),
            403,
        )
    return None


@bp.post("/decisions/<decision_id>/attachments")
@require_auth
def attachments_create(decision_id: str) -> tuple[Response, int]:
    """Multipart upload — file in ``file`` form field; ``stage`` (signal /
    decision / action / outcome / evidence) and optional ``description`` as
    form fields."""
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None

    with session_scope() as session:
        d = session.get(Decision, did)
        assert d is not None
        forbidden = _require_workflow_authority(d)
    if forbidden is not None:
        return forbidden

    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400
    upload = request.files["file"]
    if not upload.filename:
        return jsonify({"error": "missing filename"}), 400

    stage = request.form.get("stage", "evidence")
    description = request.form.get("description")

    # Need the size to record it; werkzeug's FileStorage exposes content_length
    # only when the client sets it. Fall back to seeking the stream.
    upload.stream.seek(0, 2)  # SEEK_END
    size_bytes = upload.stream.tell()
    upload.stream.seek(0)

    try:
        att = add_attachment(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            stage=stage,
            filename=upload.filename,
            content_type=upload.mimetype or "application/octet-stream",
            size_bytes=size_bytes,
            content=cast(BinaryIO, upload.stream),
            description=description,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_attachment_dict(att)), 201


@bp.get("/decisions/<decision_id>/attachments")
@require_auth
def attachments_list(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None
    rows = list_attachments(did)
    return jsonify({"items": [_attachment_dict(a) for a in rows]}), 200


@bp.delete("/decisions/<decision_id>/attachments/<attachment_id>")
@require_auth
def attachments_delete(decision_id: str, attachment_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None

    aid = _resolve_id(attachment_id)
    if aid is None:
        return jsonify({"error": "invalid attachment id"}), 400

    with session_scope() as session:
        d = session.get(Decision, did)
        assert d is not None
        forbidden = _require_workflow_authority(d)
    if forbidden is not None:
        return forbidden

    try:
        supersede_attachment(
            decision_id=did,
            attachment_id=aid,
            user_id=uuid.UUID(g.auth.sub),
        )
    except LookupError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify({"superseded": True, "attachment_id": str(aid)}), 200


@bp.get("/decisions/<decision_id>/attachments/<attachment_id>/download")
@require_auth
def attachments_download(decision_id: str, attachment_id: str) -> Response | tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None

    aid = _resolve_id(attachment_id)
    if aid is None:
        return jsonify({"error": "invalid attachment id"}), 400

    att = get_attachment(aid)
    if att is None or att.decision_id != did or att.superseded_at is not None:
        return jsonify({"error": "not found"}), 404

    storage = get_storage()
    from reasonbook.decisions.manager import _parse_storage_uri

    ref = _parse_storage_uri(att.storage_uri, att.storage_backend)
    signed = storage.signed_url(ref, expiry_seconds=300)
    if signed is not None:
        # 302 redirect — the browser follows automatically and renders the
        # PDF in the new tab (the frontend uses <a target="_blank"> on this
        # endpoint). Returning JSON instead would leave the JSON visible
        # in the tab; consumers that want the URL programmatically can
        # parse the Location header off a non-following client.
        return make_response(redirect(signed, code=302))

    # Backend can't mint a URL — stream the bytes through.
    fh = storage.get(ref)
    response = make_response(fh.read())
    response.headers["Content-Type"] = att.content_type
    response.headers["Content-Disposition"] = f'attachment; filename="{att.filename}"'
    response.headers["Content-Length"] = str(att.size_bytes)
    return response


def _attachment_dict(att: Any) -> dict[str, Any]:
    return {
        "id": str(att.id),
        "decision_id": str(att.decision_id),
        "stage": att.stage,
        "filename": att.filename,
        "content_type": att.content_type,
        "size_bytes": att.size_bytes,
        "storage_backend": att.storage_backend,
        "uploaded_by": str(att.uploaded_by),
        "uploaded_at": att.uploaded_at.isoformat() if att.uploaded_at else None,
        "description": att.description,
        "superseded_at": att.superseded_at.isoformat() if att.superseded_at else None,
    }


@bp.post("/decisions/<decision_id>/comments")
@require_auth
def comments_create(decision_id: str) -> tuple[Response, int]:
    did, err = _require_visible_decision(decision_id)
    if err is not None:
        return err
    assert did is not None

    with session_scope() as session:
        d = session.get(Decision, did)
        assert d is not None
        forbidden = _require_workflow_authority(d)
    if forbidden is not None:
        return forbidden

    body_json = request.get_json(silent=True) or {}
    body_text = body_json.get("body")
    if not body_text:
        return jsonify({"error": "body required"}), 400

    raw_mentions = body_json.get("mentions") or []
    if not isinstance(raw_mentions, list):
        return jsonify({"error": "mentions must be a list of user ids"}), 400
    try:
        mentions = [uuid.UUID(str(m)) for m in raw_mentions]
    except ValueError:
        return jsonify({"error": "mentions must be valid user ids"}), 400

    try:
        event = post_comment(
            decision_id=did,
            user_id=uuid.UUID(g.auth.sub),
            body=body_text,
            stage_context=body_json.get("stage_context", "general"),
            mentions=mentions,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Build the response payload while the session is still open — the
    # `users` dict holds User instances bound to `session`, and accessing
    # `user.name` / `user.username` after the session commits would hit
    # `DetachedInstanceError` (expire_on_commit=True is SQLAlchemy's
    # default, which we don't override in session_scope). The sibling
    # endpoint at events_list calls _event_dict inside its with block
    # for the same reason.
    with session_scope() as session:
        users = _user_lookup_for_events([event], session)
        body = _event_dict(event, users)
    return jsonify(body), 201


# ---------------------------------------------------------------------------
# Phase 8.5 — bulk decision operations
#
# Each request gets a single ``bulk_operation_id`` (uuid). It threads into
# every event the request creates so audit can later reconstruct the
# affected decisions via ``WHERE event_metadata->>'bulk_operation_id' = '<uuid>'``.
#
# Authority is enforced per-decision; partial success is the norm. The
# response shape (``results: [{decision_id, ok, error?}, ...]``) makes the
# frontend's "5 of 6 succeeded" surface trivial.
# ---------------------------------------------------------------------------


def _parse_bulk_decision_ids(body: dict[str, Any]) -> tuple[list[uuid.UUID] | None, str | None]:
    """Return (parsed_ids, error_message). Caller dispatches on which is set."""
    raw = body.get("decision_ids")
    if not isinstance(raw, list) or not raw:
        return None, "decision_ids must be a non-empty list"
    try:
        ids = [uuid.UUID(str(d)) for d in raw]
    except ValueError:
        return None, "decision_ids must all be valid UUIDs"
    if len(ids) > 200:
        # Soft cap — keep the request synchronous and bounded. Async / paginated
        # bulk is a backlog item.
        return None, "max 200 decision_ids per bulk request"
    return ids, None


def _enforce_visibility_for_bulk(decision: Decision) -> str | None:
    """Mirror of ``_enforce_visibility`` but returns a string for use in
    the per-id result list rather than aborting the request."""
    auth = g.auth
    if decision.tenant_id != auth.tenant:
        return "decision is in another tenant"
    return None


@bp.post("/decisions/bulk/claim")
@require_auth
def bulk_claim() -> tuple[Response, int]:
    """Claim ownership of every visible, unclaimed decision in the list.

    Idempotent for decisions already claimed by this user (the manager
    short-circuits). Per-id failures (visibility, state, authority) come
    back in the ``results`` list, not as a request-level error.
    """
    body = request.get_json(silent=True) or {}
    ids, err = _parse_bulk_decision_ids(body)
    if err is not None:
        return jsonify({"error": err}), 400
    assert ids is not None

    bulk_op_id = uuid.uuid4()
    user_id = uuid.UUID(g.auth.sub)
    results: list[dict[str, Any]] = []
    succeeded = 0

    with session_scope() as session:
        for did in ids:
            d = session.get(Decision, did)
            if d is None:
                results.append({"decision_id": str(did), "ok": False, "error": "not found"})
                continue
            visibility_err = _enforce_visibility_for_bulk(d)
            if visibility_err is not None:
                results.append({"decision_id": str(did), "ok": False, "error": visibility_err})
                continue
            try:
                claim_decision(
                    decision_id=did,
                    user_id=user_id,
                    bulk_operation_id=bulk_op_id,
                    session=session,
                )
            except DecisionStateError as exc:
                results.append({"decision_id": str(did), "ok": False, "error": str(exc)})
                continue
            except DecisionAuthorityError as exc:
                results.append({"decision_id": str(did), "ok": False, "error": str(exc)})
                continue
            results.append({"decision_id": str(did), "ok": True})
            succeeded += 1

    return (
        jsonify(
            {
                "bulk_operation_id": str(bulk_op_id),
                "results": results,
                "succeeded": succeeded,
                "failed": len(ids) - succeeded,
            }
        ),
        200,
    )


@bp.post("/decisions/bulk/comment")
@require_auth
def bulk_comment() -> tuple[Response, int]:
    """Post the same comment body on every visible decision in the list.

    Stage context is fixed at ``general`` for bulk comments — bulk-posting
    a comment under a specific stage doesn't have a clear use case, and
    bulk creators are usually saying "reviewing batch" / "see ticket X" /
    "deferred to next cycle" which are decision-level not stage-level.
    """
    body = request.get_json(silent=True) or {}
    ids, err = _parse_bulk_decision_ids(body)
    if err is not None:
        return jsonify({"error": err}), 400
    assert ids is not None

    body_text = body.get("body")
    if not body_text or not str(body_text).strip():
        return jsonify({"error": "body required"}), 400

    bulk_op_id = uuid.uuid4()
    user_id = uuid.UUID(g.auth.sub)
    results: list[dict[str, Any]] = []
    succeeded = 0

    with session_scope() as session:
        for did in ids:
            d = session.get(Decision, did)
            if d is None:
                results.append({"decision_id": str(did), "ok": False, "error": "not found"})
                continue
            visibility_err = _enforce_visibility_for_bulk(d)
            if visibility_err is not None:
                results.append({"decision_id": str(did), "ok": False, "error": visibility_err})
                continue
            # The non-bulk comment endpoint also requires active workflow
            # authority (not just entitlement). Mirror that here.
            level = current_authority_level(
                session=session, user_id=user_id, workflow_id=d.workflow_id
            )
            if level is None:
                results.append(
                    {
                        "decision_id": str(did),
                        "ok": False,
                        "error": f"no active authority for workflow '{d.workflow_id}'",
                    }
                )
                continue
            try:
                post_comment(
                    decision_id=did,
                    user_id=user_id,
                    body=str(body_text),
                    stage_context="general",
                    bulk_operation_id=bulk_op_id,
                    session=session,
                )
            except ValueError as exc:
                results.append({"decision_id": str(did), "ok": False, "error": str(exc)})
                continue
            results.append({"decision_id": str(did), "ok": True})
            succeeded += 1

    return (
        jsonify(
            {
                "bulk_operation_id": str(bulk_op_id),
                "results": results,
                "succeeded": succeeded,
                "failed": len(ids) - succeeded,
            }
        ),
        200,
    )


# Convenience for tests / phase 5 review.
__all__ = ["bp", "get_decision"]
