# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Alerts API — list + disposition endpoints.

Backs the /alerts surface in the SPA. Three endpoints:

  * GET  /api/alerts                       list, status + source filters
  * POST /api/alerts/<id>/dispositions     write a disposition
  * GET  /api/alerts/<id>/lifecycle        full audit reconstruction

Tier-scoping is a no-op until the tenancy migration lands; federal
users see every alert in their tenant. When tier scope arrives, all
read paths route through ``apply_alert_tier_scope`` (parallel to
``apply_tier_scope`` for decisions).
"""

from __future__ import annotations

import uuid
from typing import Any

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import desc, select

from reasonbook.alerts import DispositionError, record_disposition
from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.models import Alert, AlertDisposition, User

bp = Blueprint("alerts", __name__)


# ----------------------------------------------------------------------
# List
# ----------------------------------------------------------------------


@bp.get("/alerts")
@require_auth
def list_alerts() -> tuple[Response, int]:
    """List alerts in the caller's tenant, newest first.

    Query params:
      status       optional — comma-separated subset of
                   {new, triaged, promoted, dismissed, reopened}
      source       optional — comma-separated subset of
                   {fraud_risk_screening, flow_graph, identity}
      matter_link  optional — `attached` | `unattached` — narrows to
                   alerts that already carry a matter_id vs those that
                   don't. Powers the /signals matcher view (unattached)
                   and the Alerts pill count in the top bar.

    No pagination yet; the prototype corpus is small. Add when needed.
    """
    auth = g.auth
    args = request.args
    status_filter = _split_csv(args.get("status"))
    source_filter = _split_csv(args.get("source"))
    matter_link = (args.get("matter_link") or "").strip().lower() or None

    with session_scope() as session:
        q = select(Alert).where(Alert.tenant_id == auth.tenant)
        if status_filter:
            q = q.where(Alert.current_status.in_(status_filter))
        if source_filter:
            q = q.where(Alert.source.in_(source_filter))
        if matter_link == "attached":
            q = q.where(Alert.matter_id.is_not(None))
        elif matter_link == "unattached":
            q = q.where(Alert.matter_id.is_(None))
        q = q.order_by(desc(Alert.detected_at))
        rows = session.execute(q).scalars().all()
        items = [_alert_dict(a) for a in rows]

        # Pre-aggregate counts the rail + the page stats need in one shot
        # so the UI doesn't re-request.
        counts = _counts(session, tenant_id=auth.tenant)

    return jsonify({"items": items, "counts": counts}), 200


# ----------------------------------------------------------------------
# Attach an alert to a matter (the /signals matcher's write path)
# ----------------------------------------------------------------------


@bp.patch("/alerts/<alert_id>")
@require_auth
def patch_alert(alert_id: str) -> tuple[Response, int]:
    """Associate an unattached alert with a matter.

    Body:
      { "matter_id": "<uuid>" }

    Only supports the association step for now — an unattached alert
    (matter_id IS NULL) gets bound to a matter so it surfaces on the
    case-file's SignalActionCard where in-place disposition takes over.
    Re-parenting an already-attached alert is out of scope; callers
    should instead dismiss + reopen against the correct matter.
    """
    from reasonbook.models import Matter

    auth = g.auth
    body = request.get_json(silent=True) or {}
    raw_matter_id = body.get("matter_id")
    if not isinstance(raw_matter_id, str) or not raw_matter_id.strip():
        return (
            jsonify({"error": "matter_id required"}),
            400,
        )
    try:
        matter_uuid = uuid.UUID(raw_matter_id)
    except (ValueError, TypeError):
        return jsonify({"error": "matter_id must be a UUID"}), 400
    try:
        alert_uuid = uuid.UUID(alert_id)
    except (ValueError, TypeError):
        return jsonify({"error": "alert id must be a UUID"}), 400

    with session_scope() as session:
        alert = session.get(Alert, alert_uuid)
        if alert is None or alert.tenant_id != auth.tenant:
            return jsonify({"error": "alert not found"}), 404
        if alert.matter_id is not None:
            return (
                jsonify(
                    {
                        "error": "alert already attached to a matter",
                        "matter_id": str(alert.matter_id),
                    }
                ),
                409,
            )
        matter = session.get(Matter, matter_uuid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404
        alert.matter_id = matter_uuid
        session.flush()
        return jsonify({"alert": _alert_dict(alert)}), 200


# ----------------------------------------------------------------------
# Disposition write
# ----------------------------------------------------------------------


@bp.post("/alerts/<alert_id>/dispositions")
@require_auth
def post_disposition(alert_id: str) -> tuple[Response, int]:
    """Append one disposition. Promote also instantiates a Decision.

    Body:
      {
        "action": "promote" | "dismiss" | "hold" | "reopen",
        "rationale": str (>= 8 chars),
        "reason_code": str (required when action='dismiss'),
        "metadata": object (optional — hold_until, duplicate_of_alert_id, etc.)
      }
    """
    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        return jsonify({"error": "bad alert id"}), 400

    body = request.get_json(silent=True) or {}
    action = body.get("action")
    rationale = body.get("rationale")
    reason_code = body.get("reason_code")
    metadata = body.get("metadata") or {}

    if action not in ("promote", "dismiss", "hold", "reopen"):
        return jsonify({"error": "action must be promote|dismiss|hold|reopen"}), 400

    auth = g.auth
    with session_scope() as session:
        actor = session.get(User, uuid.UUID(auth.sub))
        if actor is None:
            return jsonify({"error": "actor not found"}), 401

        # Tenant scope: alert must belong to caller's tenant. We re-check
        # here so a future producer that writes alerts across tenants
        # can't be dispositioned cross-tenant.
        alert = session.get(Alert, alert_uuid)
        if alert is None or alert.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404

        try:
            disposition = record_disposition(
                alert_id=alert_uuid,
                action=action,
                rationale=rationale or "",
                actor=actor,
                session=session,
                reason_code=reason_code,
                metadata=metadata,
            )
        except DispositionError as exc:
            return jsonify({"error": str(exc)}), 400

        # Refresh the alert state (current_status mutated by the service).
        session.flush()
        body_out = {
            "alert": _alert_dict(alert),
            "disposition": _disposition_dict(disposition),
        }
        # When promote, also surface the resulting Decision so the UI can
        # show "Promoted to case PI-…" with a link.
        if disposition.resulting_decision_id is not None:
            decision_number = session.execute(
                # Avoid a full ORM hydrate for one column.
                _select_decision_number(disposition.resulting_decision_id)
            ).scalar_one_or_none()
            body_out["resulting_decision"] = {
                "id": str(disposition.resulting_decision_id),
                "decision_number": decision_number,
            }

    return jsonify(body_out), 200


# ----------------------------------------------------------------------
# Lifecycle / audit reconstruction
# ----------------------------------------------------------------------


@bp.get("/alerts/<alert_id>/lifecycle")
@require_auth
def get_lifecycle(alert_id: str) -> tuple[Response, int]:
    """Full audit reconstruction for one alert.

    Returns ordered dispositions plus, when the alert was promoted, the
    resulting Decision's events. Mirrors the §4 audit query in
    ALERTS-SPEC.md.
    """
    try:
        alert_uuid = uuid.UUID(alert_id)
    except ValueError:
        return jsonify({"error": "bad alert id"}), 400

    auth = g.auth
    with session_scope() as session:
        alert = session.get(Alert, alert_uuid)
        if alert is None or alert.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404

        dispositions = (
            session.execute(
                select(AlertDisposition)
                .where(AlertDisposition.alert_id == alert_uuid)
                .order_by(AlertDisposition.created_at.asc())
            )
            .scalars()
            .all()
        )

        # Serialize inside the session so attribute loads have a bound
        # session (avoids DetachedInstanceError on session close).
        body_out = {
            "alert": _alert_dict(alert),
            "dispositions": [_disposition_dict(d) for d in dispositions],
        }

    return jsonify(body_out), 200


# ----------------------------------------------------------------------
# Serialization helpers
# ----------------------------------------------------------------------


def _alert_dict(a: Alert) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "tenant_id": a.tenant_id,
        "source": a.source,
        "signal_ref": a.signal_ref,
        "severity": a.severity,
        "subject_entity": a.subject_entity,
        "matter_id": str(a.matter_id) if a.matter_id else None,
        "fund_flow_ref": [str(x) for x in (a.fund_flow_ref or [])],
        "title": a.title,
        "body": a.body,
        "target_program_id": a.target_program_id,
        "detected_at": a.detected_at.isoformat(),
        "current_status": a.current_status,
    }


def _disposition_dict(d: AlertDisposition) -> dict[str, Any]:
    return {
        "id": str(d.id),
        "alert_id": str(d.alert_id),
        "action": d.action,
        "reason_code": d.reason_code,
        "rationale": d.rationale,
        "actor_user_id": str(d.actor_user_id),
        "actor_tier": d.actor_tier,
        "resulting_decision_id": (
            str(d.resulting_decision_id) if d.resulting_decision_id else None
        ),
        "resulting_status": d.resulting_status,
        "metadata": d.event_metadata,
        "created_at": d.created_at.isoformat(),
    }


def _counts(session: Any, *, tenant_id: str) -> dict[str, int]:  # noqa: ANN401
    # session is typed Any because the typed sqlalchemy.orm.Session would
    # force a heavier import surface for one helper.
    """Aggregate counts the stats strip + rail pill consume.

    Single query against the partial index; the prototype corpus is small
    so a GROUP BY scan is cheap. When volume grows, replace with a
    materialized view.
    """
    from sqlalchemy import func

    rows = session.execute(
        select(Alert.current_status, func.count())
        .where(Alert.tenant_id == tenant_id)
        .group_by(Alert.current_status)
    ).all()
    counts: dict[str, int] = {
        s: 0 for s in ("new", "triaged", "promoted", "dismissed", "reopened")
    }
    for status, n in rows:
        counts[status] = n
    # actionable = new + reopened (the rail pill); dismissed counted
    # separately so the stats strip can read them straight.
    counts["actionable"] = counts["new"] + counts["reopened"]
    # `unattached` powers the top-bar Alerts pill — count of alerts that
    # need a matter picked before disposition. Restricted to actionable
    # statuses so dismissed/promoted orphans don't inflate the badge.
    unattached_row = session.execute(
        select(func.count()).where(
            Alert.tenant_id == tenant_id,
            Alert.matter_id.is_(None),
            Alert.current_status.in_(("new", "reopened")),
        )
    ).scalar()
    counts["unattached"] = int(unattached_row or 0)
    return counts


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _select_decision_number(decision_id: uuid.UUID) -> Any:
    """Stub query for the decision number — kept lazy-import friendly."""
    from sqlalchemy import select as _select  # noqa: PLC0415

    from reasonbook.models import Decision  # noqa: PLC0415

    return _select(Decision.decision_number).where(Decision.id == decision_id)
