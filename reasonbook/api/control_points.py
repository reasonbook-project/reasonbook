# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Control points API — adherence list + named-gap write.

Per ADR-11 (Spine/ADR-11-accountability-spine.md). Two endpoints:

  * GET  /api/matters/<matter_id>/control-points  → list with status
  * POST /api/control-points/<id>/mark-gap         → record a named gap

Clear-on-finalize happens inside ``reasonbook.decisions.manager.finalize_decision``;
there is no clear endpoint — clearance is a side-effect of finalize.
"""

from __future__ import annotations

import uuid

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import select

from reasonbook.auth.decorators import require_auth
from reasonbook.control_points import ControlPointError, mark_gap
from reasonbook.db import session_scope
from reasonbook.models import ControlPoint, Decision, Matter


def _matter_tenant_id(session, matter: Matter) -> str | None:
    """Matter has no tenant_id column; inherit from its originating
    Decision. Returns None if the matter has no originating Decision
    (legacy / partial seed rows)."""
    if matter.originating_decision_id is None:
        return None
    originating = session.get(Decision, matter.originating_decision_id)
    return originating.tenant_id if originating else None

bp = Blueprint("control_points", __name__)


_TIER_ORDER = {"federal": 0, "state": 1, "recipient": 2}
_TRIGGER_ORDER = {
    "on_promote": 0,
    "on_outcome": 1,
    "on_modification": 2,
    "on_adverse_action": 3,
    "on_closeout": 4,
}


def _cp_dict(cp: ControlPoint) -> dict[str, object]:
    return {
        "id": str(cp.id),
        "tenant_id": cp.tenant_id,
        "matter_id": str(cp.matter_id),
        "node_id": str(cp.node_id),
        "tier": cp.tier,
        "archetype_id": cp.archetype_id,
        "trigger_event": cp.trigger_event,
        "gate_type": cp.gate_type,
        "required_authority_role": cp.required_authority_role,
        "status": cp.status,
        "cleared_by_decision_id": (
            str(cp.cleared_by_decision_id) if cp.cleared_by_decision_id else None
        ),
        "cleared_by_user_id": (
            str(cp.cleared_by_user_id) if cp.cleared_by_user_id else None
        ),
        "cleared_at": cp.cleared_at.isoformat() if cp.cleared_at else None,
        "named_gap_reason": cp.named_gap_reason,
        "created_at": cp.created_at.isoformat(),
        "updated_at": cp.updated_at.isoformat(),
    }


@bp.get("/matters/<matter_id>/control-points")
@require_auth
def list_for_matter(matter_id: str) -> tuple[Response, int]:
    """List control points for a matter, ordered by tier then trigger event."""
    try:
        matter_uuid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "bad matter id"}), 400

    auth = g.auth
    with session_scope() as session:
        matter = session.get(Matter, matter_uuid)
        if matter is None or _matter_tenant_id(session, matter) != auth.tenant:
            return jsonify({"error": "not found"}), 404

        rows = (
            session.execute(
                select(ControlPoint).where(ControlPoint.matter_id == matter_uuid)
            )
            .scalars()
            .all()
        )
        items = sorted(
            (_cp_dict(cp) for cp in rows),
            key=lambda d: (
                _TIER_ORDER.get(d["tier"], 99),  # type: ignore[arg-type]
                _TRIGGER_ORDER.get(d["trigger_event"], 99),  # type: ignore[arg-type]
                d["archetype_id"],
            ),
        )

        counts = {
            "pending": sum(1 for cp in rows if cp.status == "pending"),
            "cleared": sum(1 for cp in rows if cp.status == "cleared"),
            "skipped": sum(1 for cp in rows if cp.status == "skipped"),
            "missed": sum(1 for cp in rows if cp.status == "missed"),
            "total": len(rows),
        }
    return jsonify({"items": items, "counts": counts}), 200


@bp.post("/control-points/<cp_id>/mark-gap")
@require_auth
def post_mark_gap(cp_id: str) -> tuple[Response, int]:
    """Record a named gap on this control point.

    Body:
      {
        "reason": str (required, >= 8 chars after strip),
        "decision_id": uuid (required — the Decision in whose ledger the
                             ``control_point_skipped`` event lands; typically
                             the matter's federal-root Decision).
      }
    """
    try:
        cp_uuid = uuid.UUID(cp_id)
    except ValueError:
        return jsonify({"error": "bad control point id"}), 400

    body = request.get_json(silent=True) or {}
    reason = (body.get("reason") or "").strip()
    decision_id_raw = body.get("decision_id")

    if len(reason) < 8:
        return jsonify({"error": "reason must be at least 8 characters"}), 400
    if not decision_id_raw:
        return jsonify({"error": "decision_id is required"}), 400
    try:
        decision_uuid = uuid.UUID(decision_id_raw)
    except ValueError:
        return jsonify({"error": "bad decision_id"}), 400

    auth = g.auth
    with session_scope() as session:
        cp = session.get(ControlPoint, cp_uuid)
        if cp is None or cp.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404

        decision = session.get(Decision, decision_uuid)
        if decision is None or decision.tenant_id != auth.tenant:
            return jsonify({"error": "decision not found"}), 404

        try:
            updated = mark_gap(
                cp_uuid,
                decision=decision,
                user_id=uuid.UUID(auth.sub),
                reason=reason,
                session=session,
            )
        except ControlPointError as exc:
            return jsonify({"error": str(exc)}), 400

        # Serialize inside the session scope — the ORM instance detaches
        # the moment session_scope() exits and any further attribute
        # access raises DetachedInstanceError.
        payload = _cp_dict(updated)

    return jsonify({"control_point": payload}), 200
