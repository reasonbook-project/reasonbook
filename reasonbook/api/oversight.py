# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight API — evidence linkage, oversight cycles, committee actions, dossier export.

Endpoints:

- GET    /api/oversight/decisions                       — list oversight decisions, cycle/domain filters
- POST   /api/oversight/decisions/:id/evidence          — link evidence
- GET    /api/oversight/decisions/:id/evidence          — list evidence
- POST   /api/oversight/evidence/:id/supersede          — supersede an evidence link
- POST   /api/oversight/decisions/:id/committee-action  — record noted/endorsed/deferred
- GET    /api/oversight/cycles                          — list oversight cycles
- POST   /api/oversight/cycles                          — create a cycle
- GET    /api/oversight/cycles/:id/dossier              — fetch generated dossier PDF
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from flask import Blueprint, Response, g, jsonify, make_response, request

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.decisions.scope import apply_tier_scope
from reasonbook.models import (
    Decision,
    DecisionEvent,
    OversightCycle,
    OversightEvidenceLink,
    OversightFinding,
)
from reasonbook.oversight import OVERSIGHT_WORKFLOW_ID
from reasonbook.oversight.authority import (
    can_record_committee_action,
    resolve_oversight_capabilities,
)
from reasonbook.oversight.cycles import CycleError, create_cycle, list_cycles
from reasonbook.oversight.dossier import render_cycle_dossier
from reasonbook.oversight.evidence import (
    EvidenceError,
    evidence_diversity,
    link_evidence,
    list_active_evidence,
    supersede_evidence,
)

bp = Blueprint("oversight", __name__)


def _write_event(
    session: Any,
    *,
    decision_id: uuid.UUID,
    tenant_id: str,
    workflow_id: str,
    user_id: uuid.UUID | None,
    action: str,
    comment: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    session.add(
        DecisionEvent(
            id=uuid.uuid4(),
            decision_id=decision_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            user_id=user_id,
            action=action,
            comment=comment,
            event_metadata=metadata,
        )
    )


# ---------------------------------------------------------------------------
# Oversight-tier guard
# ---------------------------------------------------------------------------


def _require_oversight(auth: Any) -> tuple[Response, int] | None:
    # Historically gated on Tenant.has_oversight (DG-era tier flag). DP
    # is single-tenant federal — oversight is always available and the
    # gate is a no-op. Kept as a call site so the multi-agency future
    # has a single place to reintroduce a per-agency capability check.
    # Also: not reading the JWT claim any more — the claim goes stale
    # when tenant flags flip mid-session, and the demo doesn't need it.
    _ = auth
    return None


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


@bp.get("/oversight/decisions")
@require_auth
def list_oversight_decisions() -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err

    cycle_id = request.args.get("cycle_id")
    domain = request.args.get("domain")
    needs_endorsement = request.args.get("needs_endorsement") == "true"

    with session_scope() as session:
        # Row-level tenancy scope per TENANCY-MODEL.md §3. Oversight
        # decisions still have tier scope — a state IG must not see
        # another state's oversight queue.
        q = apply_tier_scope(
            session.query(Decision),
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
        ).filter(
            Decision.tenant_id == auth.tenant,
            Decision.workflow_id == OVERSIGHT_WORKFLOW_ID,
        )
        if cycle_id:
            try:
                q = q.filter(Decision.oversight_cycle_id == uuid.UUID(cycle_id))
            except ValueError:
                return jsonify({"error": "invalid cycle_id"}), 400
        if domain:
            q = q.filter(Decision.decision_payload["domain"].astext == domain)
        if needs_endorsement:
            q = q.filter(
                Decision.decided_at.isnot(None),
                Decision.closed_at.is_(None),
            )
        rows = q.order_by(Decision.created_at.desc()).limit(200).all()

        items = []
        for d in rows:
            count, distinct_workflows = evidence_diversity(session, oversight_decision_id=d.id)
            items.append(
                {
                    "id": str(d.id),
                    "decision_number": d.decision_number,
                    "title": d.title,
                    "decision_type": d.decision_type,
                    "priority": d.priority,
                    "status": d.status,
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                    "sla_deadline": d.sla_deadline.isoformat() if d.sla_deadline else None,
                    "oversight_cycle_id": (
                        str(d.oversight_cycle_id) if d.oversight_cycle_id else None
                    ),
                    "target_outcome": d.target_outcome,
                    "actual_outcome": d.actual_outcome,
                    "evidence_count": count,
                    "distinct_evidence_workflows": distinct_workflows,
                }
            )

    return jsonify({"items": items, "total": len(items)}), 200


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


def _evidence_dict(
    link: OversightEvidenceLink,
    operational: Decision | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": str(link.id),
        "oversight_decision_id": str(link.oversight_decision_id),
        "operational_decision_id": str(link.operational_decision_id),
        "evidence_role": link.evidence_role,
        "link_rationale": link.link_rationale,
        "linked_at": link.linked_at.isoformat() if link.linked_at else None,
        "linked_by": str(link.linked_by),
        "superseded_at": link.superseded_at.isoformat() if link.superseded_at else None,
        "superseded_by_link_id": (
            str(link.superseded_by_link_id) if link.superseded_by_link_id else None
        ),
    }
    if operational is not None:
        base["operational"] = {
            "id": str(operational.id),
            "decision_number": operational.decision_number,
            "title": operational.title,
            "workflow_id": operational.workflow_id,
            "status": operational.status,
            "decided_at": (operational.decided_at.isoformat() if operational.decided_at else None),
        }
    return base


@bp.get("/oversight/decisions/<decision_id>/evidence")
@require_auth
def list_evidence(decision_id: str) -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        oversight_id = uuid.UUID(decision_id)
    except ValueError:
        return jsonify({"error": "invalid decision_id"}), 400

    with session_scope() as session:
        oversight = session.get(Decision, oversight_id)
        if oversight is None or oversight.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        if oversight.workflow_id != OVERSIGHT_WORKFLOW_ID:
            return jsonify({"error": "not an oversight decision"}), 400
        active = list_active_evidence(session, oversight_decision_id=oversight_id)

        op_ids = [link.operational_decision_id for link in active]
        op_map: dict[uuid.UUID, Decision] = {}
        if op_ids:
            op_rows = session.query(Decision).filter(Decision.id.in_(op_ids)).all()
            op_map = {row.id: row for row in op_rows}

        items = [_evidence_dict(link, op_map.get(link.operational_decision_id)) for link in active]
        return jsonify({"items": items}), 200


@bp.post("/oversight/decisions/<decision_id>/evidence")
@require_auth
def create_evidence(decision_id: str) -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        oversight_id = uuid.UUID(decision_id)
    except ValueError:
        return jsonify({"error": "invalid decision_id"}), 400

    body = request.get_json(silent=True) or {}
    operational_id_raw = body.get("operational_decision_id")
    role = body.get("evidence_role", "primary_evidence")
    rationale = body.get("rationale")
    if not operational_id_raw:
        return jsonify({"error": "operational_decision_id required"}), 400
    try:
        operational_id = uuid.UUID(operational_id_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid operational_decision_id"}), 400

    with session_scope() as session:
        try:
            link = link_evidence(
                session,
                oversight_decision_id=oversight_id,
                operational_decision_id=operational_id,
                evidence_role=role,
                linked_by=uuid.UUID(auth.sub),
                rationale=rationale,
            )
        except EvidenceError as exc:
            return jsonify({"error": str(exc)}), 400

        _write_event(
            session,
            decision_id=oversight_id,
            tenant_id=auth.tenant,
            workflow_id=OVERSIGHT_WORKFLOW_ID,
            user_id=uuid.UUID(auth.sub),
            action="evidence_linked",
            metadata={
                "operational_decision_id": str(operational_id),
                "evidence_role": role,
                "rationale": rationale,
            },
        )
        return jsonify(_evidence_dict(link)), 201


@bp.post("/oversight/evidence/<link_id>/supersede")
@require_auth
def supersede(link_id: str) -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        link_uuid = uuid.UUID(link_id)
    except ValueError:
        return jsonify({"error": "invalid link_id"}), 400

    body = request.get_json(silent=True) or {}
    replacement_op_id = body.get("replacement_operational_decision_id")
    replacement_role = body.get("replacement_evidence_role")
    rationale = body.get("rationale")

    with session_scope() as session:
        original = session.get(OversightEvidenceLink, link_uuid)
        if original is None or original.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404

        replacement = None
        if replacement_op_id and replacement_role:
            try:
                replacement = link_evidence(
                    session,
                    oversight_decision_id=original.oversight_decision_id,
                    operational_decision_id=uuid.UUID(replacement_op_id),
                    evidence_role=replacement_role,
                    linked_by=uuid.UUID(auth.sub),
                    rationale=rationale,
                )
            except (EvidenceError, ValueError) as exc:
                return jsonify({"error": str(exc)}), 400
        try:
            supersede_evidence(session, link_id=link_uuid, replacement=replacement)
        except EvidenceError as exc:
            return jsonify({"error": str(exc)}), 400

        _write_event(
            session,
            decision_id=original.oversight_decision_id,
            tenant_id=auth.tenant,
            workflow_id=OVERSIGHT_WORKFLOW_ID,
            user_id=uuid.UUID(auth.sub),
            action="evidence_superseded",
            metadata={
                "link_id": str(link_uuid),
                "rationale": rationale,
                "replacement_link_id": str(replacement.id) if replacement else None,
            },
        )

        return jsonify(
            {
                "superseded": _evidence_dict(original),
                "replacement": _evidence_dict(replacement) if replacement else None,
            }
        ), 200


# ---------------------------------------------------------------------------
# Committee action
# ---------------------------------------------------------------------------


# Activity codes preserved across the rename for audit-log continuity:
# 'noted_by_board' / 'ratified_by_board' / 'ratified_by_committee' /
# 'deferred_to_next_cycle' continue to be accepted. The first two are
# legacy banking-era codes that may appear in existing audit trails;
# new submissions should use the committee variants.
COMMITTEE_ACTIONS = {
    "noted_by_committee",
    "endorsed_by_committee",
    "noted_by_board",          # legacy carry-over for historical audit reads
    "ratified_by_board",       # legacy carry-over for historical audit reads
    "ratified_by_committee",
    "deferred_to_next_cycle",
}


@bp.post("/oversight/decisions/<decision_id>/committee-action")
@require_auth
def record_committee_action(decision_id: str) -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        oversight_id = uuid.UUID(decision_id)
    except ValueError:
        return jsonify({"error": "invalid decision_id"}), 400

    body = request.get_json(silent=True) or {}
    action = body.get("action")
    committee = body.get("committee")
    note = body.get("note")
    if action not in COMMITTEE_ACTIONS:
        return jsonify({"error": f"action must be one of {sorted(COMMITTEE_ACTIONS)}"}), 400

    with session_scope() as session:
        caps = resolve_oversight_capabilities(session, user_id=uuid.UUID(auth.sub))
        if not can_record_committee_action(caps):
            return jsonify({"error": "user cannot record committee action"}), 403

        oversight = session.get(Decision, oversight_id)
        if oversight is None or oversight.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        if oversight.workflow_id != OVERSIGHT_WORKFLOW_ID:
            return jsonify({"error": "not an oversight decision"}), 400

        _write_event(
            session,
            decision_id=oversight_id,
            tenant_id=auth.tenant,
            workflow_id=OVERSIGHT_WORKFLOW_ID,
            user_id=uuid.UUID(auth.sub),
            action=action,
            comment=note,
            metadata={"committee": committee} if committee else None,
        )
        return jsonify({"ok": True, "action": action}), 200


# ---------------------------------------------------------------------------
# Cycles
# ---------------------------------------------------------------------------


def _cycle_dict(c: OversightCycle, decision_count: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(c.id),
        "tenant_id": c.tenant_id,
        "name": c.name,
        "cycle_type": c.cycle_type,
        "committee": c.committee,
        "cycle_start": c.cycle_start.isoformat(),
        "cycle_end": c.cycle_end.isoformat(),
        "status": c.status,
        "meeting_date": c.meeting_date.isoformat() if c.meeting_date else None,
        "notes": c.notes,
        "created_at": c.created_at.isoformat(),
        "created_by": str(c.created_by),
    }
    if decision_count is not None:
        out["decision_count"] = decision_count
    return out


@bp.get("/oversight/cycles")
@require_auth
def cycles() -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    status = request.args.get("status")
    with session_scope() as session:
        rows = list_cycles(session, tenant_id=auth.tenant, status=status)
        # Batch the per-cycle decision count so the dossier-list view can
        # render rows without a second round-trip per cycle.
        counts: dict[uuid.UUID, int] = {}
        if rows:
            from sqlalchemy import func

            # Aggregate query — tier scope applied so cardinality
            # doesn't leak across states (TENANCY-MODEL.md §3).
            count_q = apply_tier_scope(
                session.query(Decision.oversight_cycle_id, func.count(Decision.id)),
                tier=auth.tier,
                participant_org_id=(
                    uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
                ),
            ).filter(
                Decision.tenant_id == auth.tenant,
                Decision.workflow_id == OVERSIGHT_WORKFLOW_ID,
                Decision.oversight_cycle_id.in_([c.id for c in rows]),
            ).group_by(Decision.oversight_cycle_id)
            for cycle_id, n in count_q.all():
                if cycle_id is not None:
                    counts[cycle_id] = n
        items = [_cycle_dict(c, decision_count=counts.get(c.id, 0)) for c in rows]
        return jsonify({"items": items}), 200


@bp.post("/oversight/cycles")
@require_auth
def create_cycle_route() -> tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err

    body = request.get_json(silent=True) or {}
    name = body.get("name")
    cycle_type = body.get("cycle_type")
    cycle_start_raw = body.get("cycle_start")
    cycle_end_raw = body.get("cycle_end")
    if not (name and cycle_type and cycle_start_raw and cycle_end_raw):
        return jsonify({"error": "name, cycle_type, cycle_start, cycle_end required"}), 400

    try:
        cycle_start = date.fromisoformat(cycle_start_raw)
        cycle_end = date.fromisoformat(cycle_end_raw)
    except (ValueError, TypeError):
        return jsonify({"error": "invalid date format"}), 400

    meeting_date_raw = body.get("meeting_date")
    meeting_date = date.fromisoformat(meeting_date_raw) if meeting_date_raw else None

    with session_scope() as session:
        try:
            cycle = create_cycle(
                session,
                tenant_id=auth.tenant,
                name=name,
                cycle_type=cycle_type,
                cycle_start=cycle_start,
                cycle_end=cycle_end,
                created_by=uuid.UUID(auth.sub),
                committee=body.get("committee"),
                meeting_date=meeting_date,
                notes=body.get("notes"),
            )
        except CycleError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(_cycle_dict(cycle)), 201


@bp.get("/oversight/cycles/<cycle_id>/dossier")
@require_auth
def dossier(cycle_id: str) -> Response | tuple[Response, int]:
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        cycle_uuid = uuid.UUID(cycle_id)
    except ValueError:
        return jsonify({"error": "invalid cycle_id"}), 400

    with session_scope() as session:
        cycle = session.get(OversightCycle, cycle_uuid)
        if cycle is None or cycle.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        cycle_name = cycle.name

    pdf_bytes = render_cycle_dossier(cycle_uuid)
    response = make_response(pdf_bytes)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="dossier-{cycle_name.replace(" ", "_")}.pdf"'
    )
    return response


# ─── Findings ─────────────────────────────────────────────────────────────


def _finding_dict(f: OversightFinding) -> dict[str, Any]:
    return {
        "id": str(f.id),
        "cycle_id": str(f.cycle_id),
        "finding_number": f.finding_number,
        "title": f.title,
        "observation": f.observation,
        "source": f.source,
        "severity": f.severity,
        "status": f.status,
        "cited_matter_ids": [str(m) for m in (f.cited_matter_ids or [])],
        "citations": list(f.citations or []),
        "disposition": f.disposition,
        "opened_at": f.opened_at.isoformat(),
        "opened_by": str(f.opened_by),
        "closed_at": f.closed_at.isoformat() if f.closed_at else None,
        "closed_by": str(f.closed_by) if f.closed_by else None,
    }


@bp.get("/oversight/cycles/<cycle_id>/findings")
@require_auth
def list_findings(cycle_id: str) -> tuple[Response, int]:
    """Findings on a specific oversight cycle.

    Returns every finding attached to the cycle in severity order
    (critical → low), then opened_at desc. No pagination for v1 —
    finding counts per cycle are small (single-digit to low-tens).
    """
    auth = g.auth
    if (err := _require_oversight(auth)) is not None:
        return err
    try:
        cycle_uuid = uuid.UUID(cycle_id)
    except ValueError:
        return jsonify({"error": "invalid cycle_id"}), 400

    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    with session_scope() as session:
        cycle = session.get(OversightCycle, cycle_uuid)
        if cycle is None or cycle.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        rows = (
            session.query(OversightFinding)
            .filter(
                OversightFinding.tenant_id == auth.tenant,
                OversightFinding.cycle_id == cycle_uuid,
            )
            .order_by(OversightFinding.opened_at.desc())
            .all()
        )
        rows.sort(key=lambda f: (severity_rank.get(f.severity, 99), f.opened_at.timestamp() * -1))
        items = [_finding_dict(f) for f in rows]
        counts = {
            "total": len(items),
            "open": sum(1 for r in rows if r.status == "open"),
            "closed": sum(1 for r in rows if r.status == "closed"),
            "under_appeal": sum(1 for r in rows if r.status == "under_appeal"),
        }
        return jsonify({"items": items, "counts": counts}), 200
