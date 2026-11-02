# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Upstream-review dispatch — TENANCY-MODEL.md §5.

On a tier-bound Decision being finalized (or completing an action /
outcome / modification / adverse_action / closeout), the archetype's
``upstream_review.<action_kind>`` decides what happens upstream:

- ``notify`` — write a single ``decision_events`` row on the source
  Decision tagged ``upstream_notify_<action_kind>``. No new Decision.
- ``gate`` — write the notify event AND create an upstream Decision
  bound to the parent matter node in ``assigned`` status (lands in
  the upstream owner's Inbox via apply_tier_scope). The upstream
  Decision carries its own SLA (``review_sla_hours`` from the
  archetype's UpstreamReview block).

A Decision at the federal root (no parent node) has no upstream — both
modes become no-ops. The default behavior across archetypes is notify
(per §5 "don't accrete bureaucracy by inertia"); gates are declared
explicitly in archetype YAMLs.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from sqlalchemy.orm import Session

from reasonbook.decisions.manager import create_decision
from reasonbook.models import Decision, DecisionEvent, MatterNode
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)


ActionKindLiteral = Literal[
    "promote", "outcome", "modification", "adverse_action", "closeout"
]


class UpstreamDispatchOutcome(StrEnum):
    NO_UPSTREAM = "no_upstream"      # federal root or missing node — no-op
    NOTIFIED = "notified"            # event written, no new Decision
    GATED = "gated"                  # event written + upstream Decision created


@dataclass(frozen=True)
class UpstreamDispatchResult:
    outcome: UpstreamDispatchOutcome
    event_id: uuid.UUID | None = None
    upstream_decision_id: uuid.UUID | None = None


def _action_kind_to_field(action_kind: ActionKindLiteral) -> str:
    """Map the action_kind literal to the UpstreamReview attribute name."""
    return f"on_{action_kind}"


def dispatch_upstream(
    *,
    source_decision: Decision,
    action_kind: ActionKindLiteral,
    user_id: uuid.UUID,
    session: Session,
) -> UpstreamDispatchResult:
    """Run upstream review for ``source_decision``'s ``action_kind`` transition.

    Caller has already mutated the source Decision in-session (finalize,
    record_action, etc.); this function consumes that state and either
    notifies or gates upstream. Caller owns transaction commit.

    Idempotency is NOT enforced here — each call writes an event. The
    caller is responsible for invoking ``dispatch_upstream`` exactly
    once per transition (the finalize_decision wrapper does this).
    """
    # Federal-root decisions have no parent — nothing upstream.
    if source_decision.matter_node_id is None:
        return UpstreamDispatchResult(outcome=UpstreamDispatchOutcome.NO_UPSTREAM)

    source_node = session.get(MatterNode, source_decision.matter_node_id)
    if source_node is None or source_node.parent_node_id is None:
        return UpstreamDispatchResult(outcome=UpstreamDispatchOutcome.NO_UPSTREAM)

    parent_node = session.get(MatterNode, source_node.parent_node_id)
    if parent_node is None:
        return UpstreamDispatchResult(outcome=UpstreamDispatchOutcome.NO_UPSTREAM)

    # Resolve the archetype's upstream policy.
    archetype = get_engine().archetype_for_program(source_decision.workflow_id)
    review = archetype.upstream_review
    mode = getattr(review, _action_kind_to_field(action_kind))

    # Always write the notify event first.
    event = DecisionEvent(
        decision_id=source_decision.id,
        tenant_id=source_decision.tenant_id,
        workflow_id=source_decision.workflow_id,
        user_id=user_id,
        action=f"upstream_notify_{action_kind}",
        event_metadata={
            "mode": mode,
            "action_kind": action_kind,
            "source_node_id": str(source_node.id),
            "source_tier": source_node.tier,
            "parent_node_id": str(parent_node.id),
            "parent_tier": parent_node.tier,
        },
    )
    session.add(event)
    session.flush()

    if mode == "notify":
        log.info(
            "upstream.notify decision_id=%s action_kind=%s parent_node=%s",
            source_decision.id,
            action_kind,
            parent_node.id,
        )
        return UpstreamDispatchResult(
            outcome=UpstreamDispatchOutcome.NOTIFIED,
            event_id=event.id,
        )

    # mode == "gate": create the upstream Decision. fund_flow_path is
    # the parent node's ancestor walk — same shape as source minus the
    # source's leaf (or empty for parent-of-federal cases, though the
    # federal-root short-circuit above means parent_tier is never
    # 'federal' except when source was state).
    parent_path = _ancestor_path(session, parent_node)
    upstream = create_decision(
        tenant_id=source_decision.tenant_id,
        workflow_id=source_decision.workflow_id,
        decision_type=archetype.archetype.id,
        title=f"Upstream review · {action_kind} · {source_decision.decision_number}",
        created_by=user_id,
        sla_hours=review.review_sla_hours,
        matter_id=source_decision.matter_id,
        matter_node_id=parent_node.id,
        fund_flow_path=parent_path,
        # parent_decision_id in the payload is the lightweight cross-link.
        # Once the ledger.parent_ledger_id flow lands for archetype
        # finalize, swap to that for the canonical linkage.
        decision_payload={
            "upstream_review": {
                "action_kind": action_kind,
                "source_decision_id": str(source_decision.id),
                "source_node_id": str(source_node.id),
                "review_sla_hours": review.review_sla_hours,
            }
        },
        session=session,
    )

    log.info(
        "upstream.gate decision_id=%s action_kind=%s upstream_decision_id=%s "
        "review_sla_hours=%d",
        source_decision.id,
        action_kind,
        upstream.id,
        review.review_sla_hours,
    )
    return UpstreamDispatchResult(
        outcome=UpstreamDispatchOutcome.GATED,
        event_id=event.id,
        upstream_decision_id=upstream.id,
    )


def _ancestor_path(session: Session, node: MatterNode) -> list[uuid.UUID]:
    """Walk parent_node_id chain, collecting participant_org_ids from
    federal-down. Federal-root contributes nothing (its participant_org_id
    is NULL by the CHECK constraint). Result has the same shape as a
    Decision's ``fund_flow_path``.
    """
    path: list[uuid.UUID] = []
    current: MatterNode | None = node
    while current is not None:
        if current.participant_org_id is not None:
            path.append(current.participant_org_id)
        current = (
            session.get(MatterNode, current.parent_node_id)
            if current.parent_node_id is not None
            else None
        )
    path.reverse()  # federal-down order
    return path
