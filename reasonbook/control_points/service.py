# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Control points service — materialize, clear, mark gap.

See ``dp/control_points/__init__.py`` for module-level rationale and
docs/architecture/_archive/Spine/ADR-11-accountability-spine.md decision #2 for
the design.

The service writes a hash-chained ``DecisionEvent`` on every status
change (``control_point_cleared`` / ``control_point_skipped``). A skip
without a reason is a bug; the DB enforces the rule too.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from reasonbook.decisions.manager import _log_event
from reasonbook.models import (
    ControlPoint,
    Decision,
    Matter,
    MatterNode,
)
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)


class ControlPointError(Exception):
    """Caller-facing failure when a control-point transition is invalid."""


# Trigger events declared on archetype.upstream_review. Source of truth
# is the UpstreamReview pydantic model; this tuple is the iteration order
# for materialization and stays in lock-step.
_TRIGGER_EVENTS: tuple[str, ...] = (
    "on_promote",
    "on_outcome",
    "on_modification",
    "on_adverse_action",
    "on_closeout",
)


def _node_authority_role(node: MatterNode) -> str | None:
    """The role that signs at this node, per MatterNode.authority_role."""
    return node.authority_role


def materialize_for_matter(matter_id: uuid.UUID, *, session: Session) -> int:
    """Seed pending control points for every (node × archetype × trigger).

    Walks the matter's active nodes, their active archetypes, and the
    archetype's ``upstream_review`` declarations. One row per combination.

    Idempotent: if a row already exists for a combination, it is left
    alone (existing status is preserved). Returns the number of NEW rows
    inserted.
    """
    matter = session.get(Matter, matter_id)
    if matter is None:
        raise ControlPointError(f"matter {matter_id} not found")

    # Matter has no tenant_id column; tenant scoping is owned by the
    # originating Decision. Inherit from it.
    if matter.originating_decision_id is None:
        raise ControlPointError(
            f"matter {matter_id} has no originating_decision_id; cannot resolve tenant"
        )
    originating = session.get(Decision, matter.originating_decision_id)
    if originating is None:
        raise ControlPointError(
            f"matter {matter_id} originating decision {matter.originating_decision_id} "
            "not found"
        )
    tenant_id = originating.tenant_id

    engine = get_engine()

    nodes = (
        session.execute(
            select(MatterNode)
            .where(MatterNode.matter_id == matter_id)
            .where(MatterNode.removed_at.is_(None))
        )
        .scalars()
        .all()
    )

    # Pre-fetch existing rows so we can skip combinations already seeded.
    existing = {
        (cp.node_id, cp.archetype_id, cp.trigger_event)
        for cp in session.execute(
            select(ControlPoint).where(ControlPoint.matter_id == matter_id)
        )
        .scalars()
        .all()
    }

    # Only the matter's canonical archetype is live at materialization
    # time. Other entries in node.active_archetypes represent decisions
    # the node *can* host (modifications, eligibility, etc.) — those get
    # CPs lazily when a decision of that archetype is actually created.
    # Eager materialization across all active_archetypes explodes row
    # counts without representing real upcoming clearances.
    matter_archetype_id = matter.federal_archetype
    try:
        archetype = engine.get_archetype(matter_archetype_id)
    except KeyError:
        log.warning(
            "control_points.materialize: unknown federal_archetype %s on matter %s",
            matter_archetype_id,
            matter_id,
        )
        return 0
    review = archetype.upstream_review

    inserted = 0
    for node in nodes:
        for trigger in _TRIGGER_EVENTS:
            gate_type = getattr(review, trigger)  # 'gate' or 'notify'
            # ADR-11 control point = clearance gate. 'notify' is
            # informational, not a clearance — skip.
            if gate_type != "gate":
                continue
            key = (node.id, matter_archetype_id, trigger)
            if key in existing:
                continue
            session.add(
                ControlPoint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    matter_id=matter_id,
                    node_id=node.id,
                    tier=node.tier,
                    archetype_id=matter_archetype_id,
                    trigger_event=trigger,
                    gate_type=gate_type,
                    required_authority_role=_node_authority_role(node),
                    status="pending",
                )
            )
            inserted += 1

    if inserted:
        session.flush()
    return inserted


# Map a finalizing Decision's archetype to the upstream-review trigger
# it represents at the matter's federal_archetype level. The matter's
# federal_archetype owns the CPs; a finalizing decision of one of these
# lifecycle archetypes is what clears them.
_DECISION_ARCHETYPE_TO_TRIGGER: dict[str, str] = {
    "modification": "on_modification",
    "adverse_action": "on_adverse_action",
    "closeout": "on_closeout",
}


def trigger_event_for_decision(decision: Decision, matter_federal_archetype: str) -> str:
    """Map ``decision.decision_type`` to its upstream-review trigger.

    Defaults to ``on_promote`` — that fires when the matter's
    federal_archetype itself is finalized (the initial promote) or for
    any archetype we don't have a specific lifecycle mapping for.
    """
    if decision.decision_type in _DECISION_ARCHETYPE_TO_TRIGGER:
        return _DECISION_ARCHETYPE_TO_TRIGGER[decision.decision_type]
    return "on_promote"


def find_pending_for_decision(
    decision: Decision,
    trigger_event: str,
    *,
    session: Session,
) -> ControlPoint | None:
    """Return the pending control point a Decision finalize would clear.

    CPs are keyed on the matter's ``federal_archetype`` (not the
    finalizing decision's own archetype). A ``modification`` decision
    finalize at a state node clears the federal_archetype's
    ``on_modification`` gate at that same node.

    Returns None when the decision isn't matter-bound or no matching row
    exists.
    """
    if decision.matter_node_id is None or decision.matter_id is None:
        return None
    matter = session.get(Matter, decision.matter_id)
    if matter is None:
        return None
    return session.execute(
        select(ControlPoint)
        .where(ControlPoint.node_id == decision.matter_node_id)
        .where(ControlPoint.archetype_id == matter.federal_archetype)
        .where(ControlPoint.trigger_event == trigger_event)
        .where(ControlPoint.status == "pending")
    ).scalar_one_or_none()


def clear(
    control_point_id: uuid.UUID,
    *,
    decision: Decision,
    user_id: uuid.UUID,
    session: Session,
) -> ControlPoint:
    """Mark a control point cleared by ``decision``.

    Records a ``control_point_cleared`` event on the Decision's ledger
    so the hash chain covers the clearance.
    """
    cp = session.get(ControlPoint, control_point_id)
    if cp is None:
        raise ControlPointError(f"control_point {control_point_id} not found")
    if cp.status != "pending":
        raise ControlPointError(
            f"control_point {control_point_id} is {cp.status!r}, cannot clear"
        )

    now = datetime.now(UTC)
    cp.status = "cleared"
    cp.cleared_by_decision_id = decision.id
    cp.cleared_by_user_id = user_id
    cp.cleared_at = now
    cp.updated_at = now

    _log_event(
        session,
        decision=decision,
        user_id=user_id,
        action="control_point_cleared",
        old_status=None,
        new_status=None,
        metadata={
            "control_point_id": str(cp.id),
            "archetype_id": cp.archetype_id,
            "trigger_event": cp.trigger_event,
            "tier": cp.tier,
            "node_id": str(cp.node_id),
            "gate_type": cp.gate_type,
        },
    )
    session.flush()
    return cp


def mark_gap(
    control_point_id: uuid.UUID,
    *,
    decision: Decision,
    user_id: uuid.UUID,
    reason: str,
    session: Session,
) -> ControlPoint:
    """Record this control point as a named gap — skipped with reason.

    Per ADR-11 the named-gap path is the auditable substitute for a
    silent skip: a reason on the record, hash-chained.

    ``decision`` is the Decision in whose ledger the
    ``control_point_skipped`` event lands — typically the matter's
    federal-root Decision (so the gap shows up on the matter's primary
    audit trail).
    """
    reason = reason.strip()
    if not reason:
        raise ControlPointError("named_gap_reason is required")

    cp = session.get(ControlPoint, control_point_id)
    if cp is None:
        raise ControlPointError(f"control_point {control_point_id} not found")
    if cp.status != "pending":
        raise ControlPointError(
            f"control_point {control_point_id} is {cp.status!r}, cannot mark gap"
        )

    now = datetime.now(UTC)
    cp.status = "skipped"
    cp.named_gap_reason = reason
    cp.cleared_by_user_id = user_id
    cp.cleared_at = now
    cp.updated_at = now

    _log_event(
        session,
        decision=decision,
        user_id=user_id,
        action="control_point_skipped",
        old_status=None,
        new_status=None,
        comment=reason,
        metadata={
            "control_point_id": str(cp.id),
            "archetype_id": cp.archetype_id,
            "trigger_event": cp.trigger_event,
            "tier": cp.tier,
            "node_id": str(cp.node_id),
            "gate_type": cp.gate_type,
            "named_gap_reason": reason,
        },
    )
    session.flush()
    return cp


__all__ = [
    "ControlPointError",
    "clear",
    "find_pending_for_decision",
    "mark_gap",
    "materialize_for_matter",
]
