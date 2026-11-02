# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Register tree — non-matter matter types.

Per docs/architecture/SURFACE-USER-STORIES.md, the Register lists ALL
matters of record, not just matters. Matters live behind /api/matters;
this module surfaces the other branches:

  GET /api/registry/cases       promoted alerts → resulting Decisions
  GET /api/registry/decisions   open Decisions not anchored to a matter
                                and not promoted from an alert

Both endpoints return a flat list shaped for the Register tree's leaf
renderer. Tier scope mirrors the Decisions API — federal sees all,
state/recipient see only what their fund_flow_path tier check resolves.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import select

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.decisions.manager import create_decision
from reasonbook.decisions.scope import apply_tier_scope
from reasonbook.models import Alert, AlertDisposition, Decision, Dispute

bp = Blueprint("registry", __name__)


def _decision_summary(d: Decision, *, alert: Alert | None = None) -> dict[str, Any]:
    """Compact Register-leaf shape — only what the tree row renders.

    Includes the originating alert's severity + source when the row is
    a promoted case, so the Cases branch can colour and group correctly.
    """
    return {
        "id": str(d.id),
        "decision_number": d.decision_number,
        "title": d.title,
        "status": d.status,
        "priority": d.priority,
        "workflow_id": d.workflow_id,
        "decision_type": d.decision_type,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "decided_at": d.decided_at.isoformat() if d.decided_at else None,
        "owner_id": str(d.owner_id) if d.owner_id else None,
        # Promotion provenance — only set on cases.
        "alert": (
            {
                "id": str(alert.id),
                "severity": alert.severity,
                "source": alert.source,
                "title": alert.title,
                "matter_id": str(alert.matter_id) if alert.matter_id else None,
            }
            if alert is not None
            else None
        ),
    }


@bp.get("/registry/cases")
@require_auth
def list_cases() -> tuple[Response, int]:
    """Cases — Decisions that were promoted from an Alert disposition.

    A "case" in DP is an Alert that crossed the triage threshold and
    became a tracked Decision. The Register's Cases branch lists those
    Decisions alongside the originating alert metadata (severity,
    source, optional matter link).
    """
    auth = g.auth
    with session_scope() as session:
        # All promote dispositions; join to Decision + Alert.
        promote_rows = session.execute(
            select(AlertDisposition.resulting_decision_id, AlertDisposition.alert_id)
            .where(AlertDisposition.action == "promote")
            .where(AlertDisposition.resulting_decision_id.isnot(None))
        ).all()
        if not promote_rows:
            return jsonify({"items": [], "total": 0}), 200

        decision_ids = [r[0] for r in promote_rows if r[0] is not None]
        alert_by_decision: dict[uuid.UUID, uuid.UUID] = {
            r[0]: r[1] for r in promote_rows if r[0] is not None
        }

        q = session.query(Decision).filter(Decision.id.in_(decision_ids))
        q = apply_tier_scope(
            q,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id)
                if auth.participant_org_id
                else None
            ),
        )
        q = q.filter(Decision.tenant_id == auth.tenant)
        decisions = q.order_by(Decision.created_at.desc()).all()

        alert_ids = {alert_by_decision[d.id] for d in decisions if d.id in alert_by_decision}
        alerts_by_id: dict[uuid.UUID, Alert] = {}
        if alert_ids:
            alerts_by_id = {
                a.id: a
                for a in session.query(Alert).filter(Alert.id.in_(alert_ids)).all()
            }

        items = [
            _decision_summary(
                d,
                alert=alerts_by_id.get(alert_by_decision.get(d.id)),  # type: ignore[arg-type]
            )
            for d in decisions
        ]
        return jsonify({"items": items, "total": len(items)}), 200


def _dispute_summary(d: Dispute) -> dict[str, Any]:
    """Compact Register-leaf shape for a Dispute."""
    return {
        "id": str(d.id),
        "subject_name": d.subject_name,
        "status": d.status,
        "resolution": d.resolution,
        "resolution_rationale": d.resolution_rationale,
        "candidate_a": d.candidate_a,
        "candidate_b": d.candidate_b,
        "notes": d.notes,
        "opened_at": d.opened_at.isoformat() if d.opened_at else None,
        "resolved_at": d.resolved_at.isoformat() if d.resolved_at else None,
        "related_matter_id": (
            str(d.related_matter_id) if d.related_matter_id else None
        ),
        "related_alert_id": (
            str(d.related_alert_id) if d.related_alert_id else None
        ),
    }


@bp.get("/registry/disputes")
@require_auth
def list_disputes() -> tuple[Response, int]:
    """Disputes — identity-resolution disagreements.

    Third Register branch alongside Matters (matters) and Reviews
    (promoted-alert Decisions). Each row captures a "who is this?"
    disagreement between two candidate identities.

    Sort: open first (newest first inside status), then resolved
    (newest first). Gives the analyst the actionable rows at the top
    of the list without a filter.
    """
    auth = g.auth
    with session_scope() as session:
        q = session.query(Dispute).filter(Dispute.tenant_id == auth.tenant)
        rows = q.order_by(
            Dispute.status.asc(),  # 'open' sorts before 'resolved_*'
            Dispute.opened_at.desc(),
        ).all()
        items = [_dispute_summary(d) for d in rows]
        return jsonify({"items": items, "total": len(items)}), 200


_DISPUTE_RESOLUTION_TO_STATUS: dict[str, str] = {
    "same_entity": "resolved_same",
    "different_entities": "resolved_different",
    "manual_override": "manual_override",
}


@bp.post("/registry/disputes/<dispute_id>/resolve")
@require_auth
def resolve_dispute(dispute_id: str) -> tuple[Response, int]:
    """Resolve a dispute — creates a decided Decision and closes the row.

    Under the unified Signal → Review → Decision arrow, answering the
    dispute question IS the decision. Clicking Same / Different /
    Manual override records a Decision with:

      * workflow_id = "identity-review"
      * decision_type = "identity_resolution"
      * selected_option = the resolution action chosen
      * trigger_data = both candidate blobs so the record has the
        evidence pair inline
      * status transitions straight to `decided` (skips claim/finalize
        — the analyst made the call by pressing the button)

    Also updates the Dispute row: sets ``resolution`` +
    ``resolution_rationale`` + ``resolved_by`` / ``resolved_at`` +
    ``linked_decision_id`` + ``status`` (resolved_same /
    resolved_different / manual_override).

    Body:
        {"resolution": "same_entity" | "different_entities" |
                       "manual_override",
         "rationale": "brief note on the record"}
    """
    auth = g.auth
    try:
        did = uuid.UUID(dispute_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid dispute id"}), 400

    body = request.get_json(silent=True) or {}
    resolution = body.get("resolution")
    if resolution not in _DISPUTE_RESOLUTION_TO_STATUS:
        return (
            jsonify(
                {
                    "error": "resolution must be one of "
                    "same_entity, different_entities, manual_override"
                }
            ),
            400,
        )
    rationale = (body.get("rationale") or "").strip()

    with session_scope() as session:
        dispute = session.get(Dispute, did)
        if dispute is None or dispute.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        if dispute.status not in ("open", "in_review"):
            return jsonify({"error": "dispute already resolved"}), 409

        actor_id = uuid.UUID(auth.sub)
        now = datetime.now(UTC)

        # Mint the Decision record for the resolution. It's owner-set to
        # the resolving user, decided_at is now, and the trigger_data
        # carries both candidate blobs so the record reads self-contained.
        # When the dispute is linked to a matter, thread matter_id
        # onto the decision too so the resulting record surfaces on the
        # matter's case-file (§4 Decision records) instead of floating
        # as a matter-less orphan.
        decision = create_decision(
            tenant_id=auth.tenant,
            workflow_id="identity-review",
            decision_type="identity_resolution",
            title=f"Identity review — {dispute.subject_name}",
            created_by=actor_id,
            owner_id=actor_id,
            priority="high",
            signal_source="dispute",
            signal_summary=f"Dispute {dispute.subject_name}",
            trigger_data={
                "subject_name": dispute.subject_name,
                "candidate_a": dispute.candidate_a,
                "candidate_b": dispute.candidate_b,
                "dispute_id": str(dispute.id),
            },
            agency_id=dispute.agency_id,
            matter_id=dispute.related_matter_id,
            session=session,
        )
        # Skip the whole claim → in_progress → decided → closed walk;
        # the button-press IS the decision AND the closure. Identity
        # resolution has no downstream Action or Outcome stage — once
        # the analyst picks Same / Different / Manual override the
        # question is settled. Terminal state = closed so the composite
        # card doesn't invite a stage-4 Action that doesn't exist.
        decision.selected_option = resolution
        decision.rationale = rationale or "Recorded via dispute resolve."
        decision.decided_at = now
        decision.closed_at = now
        decision.status = "closed"

        # Close the dispute + link back.
        dispute.status = _DISPUTE_RESOLUTION_TO_STATUS[resolution]
        dispute.resolution = resolution
        dispute.resolution_rationale = rationale or None
        dispute.resolved_by = actor_id
        dispute.resolved_at = now
        dispute.linked_decision_id = decision.id
        session.flush()

        return (
            jsonify(
                {
                    "dispute": _dispute_summary(dispute),
                    "decision_id": str(decision.id),
                    "decision_workflow_id": decision.workflow_id,
                    "decision_matter_id": (
                        str(decision.matter_id)
                        if decision.matter_id
                        else None
                    ),
                }
            ),
            200,
        )


@bp.get("/registry/disputes/<dispute_id>")
@require_auth
def get_dispute(dispute_id: str) -> tuple[Response, int]:
    """Fetch a single dispute by id."""
    auth = g.auth
    try:
        did = uuid.UUID(dispute_id)
    except (TypeError, ValueError):
        return jsonify({"error": "invalid dispute id"}), 400
    with session_scope() as session:
        row = session.get(Dispute, did)
        if row is None or row.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        return jsonify(_dispute_summary(row)), 200


@bp.get("/registry/decisions")
@require_auth
def list_orphan_decisions() -> tuple[Response, int]:
    """Decisions awaiting review — open lifecycle items not matter-anchored.

    Filters:
      * ``matter_id IS NULL`` — matter-anchored Decisions belong
        under the Federal awards branch.
      * status ∈ {open, assigned} — closed / decided rows aren't
        "awaiting" anything.
      * Not promoted from an Alert — those live under the Cases branch
        so a Decision shows up in exactly one Register place.
    """
    auth = g.auth
    with session_scope() as session:
        promoted_ids_q = select(AlertDisposition.resulting_decision_id).where(
            AlertDisposition.action == "promote",
            AlertDisposition.resulting_decision_id.isnot(None),
        )
        q = session.query(Decision).filter(
            Decision.matter_id.is_(None),
            Decision.status.in_(("open", "assigned")),
            Decision.tenant_id == auth.tenant,
            Decision.id.notin_(promoted_ids_q),
        )
        q = apply_tier_scope(
            q,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id)
                if auth.participant_org_id
                else None
            ),
        )
        decisions = q.order_by(Decision.created_at.desc()).all()
        items = [_decision_summary(d) for d in decisions]
        return jsonify({"items": items, "total": len(items)}), 200
