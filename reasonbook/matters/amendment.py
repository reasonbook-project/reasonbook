# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter amendment service — TENANCY-MODEL.md §13.2.

Amendments are append-only: every change writes a new row in
``matter_nodes`` and stamps ``removed_at`` on the prior. The
node graph is the audit trail of its own evolution.

This module covers the state-tier amendments:

- Add a recipient under an existing state (state OR federal)
- Remove a recipient (state OR federal)

Federal-only amendments (add/remove state stakeholder, change
authority_role, change matter-level fields) and "tier-above amends
node's active_archetypes" are tracked as follow-ups.

Authorization rules per §13.2:

| Amendment              | Authorized actors                            |
|------------------------|-----------------------------------------------|
| Add a recipient        | state tier at the parent state + federal      |
| Remove a recipient     | same                                          |
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.models import DecisionEvent, MatterNode, User
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)


class AmendmentError(ValueError):
    """The amendment failed validation or authorization."""


class AmendmentAuthorityError(PermissionError):
    """The actor is not allowed to perform this amendment."""


@dataclass(frozen=True)
class AmendmentResult:
    new_node_id: uuid.UUID | None
    removed_node_id: uuid.UUID | None


def _resolve_actor_tier(actor: User) -> tuple[str, uuid.UUID | None]:
    return actor.tier, actor.participant_org_id


def _check_state_amendment_authority(
    actor: User, *, parent_state_node: MatterNode
) -> None:
    """Authorize a state-tier amendment.

    Allowed: federal tier (any state); state tier whose
    participant_org_id matches the parent state node's
    participant_org_id. Anything else → 403.
    """
    tier, org_id = _resolve_actor_tier(actor)
    if tier == "federal":
        return
    if tier == "state" and parent_state_node.participant_org_id == org_id:
        return
    raise AmendmentAuthorityError(
        "only federal-tier users or the parent state's tier may amend its recipients"
    )


def add_recipient_node(
    *,
    matter_id: uuid.UUID,
    parent_state_node_id: uuid.UUID,
    participant_org_id: uuid.UUID,
    active_archetypes: list[str] | None = None,
    authority_role: str | None = None,
    actor: User,
    session: Session,
) -> MatterNode:
    """Add a recipient under the given state node.

    Defaults pull from the matter's program YAML when not supplied. The
    unique partial index on ``(matter_id, participant_org_id) WHERE
    removed_at IS NULL`` blocks duplicate active nodes at the DB level
    — caller surfaces the resulting IntegrityError as 409 conflict.
    """
    parent = session.get(MatterNode, parent_state_node_id)
    if parent is None:
        raise AmendmentError(f"parent state node {parent_state_node_id} not found")
    if parent.matter_id != matter_id:
        raise AmendmentError("parent state node is in a different matter")
    if parent.tier != "state":
        raise AmendmentError(f"parent node tier must be 'state', got {parent.tier!r}")
    if parent.removed_at is not None:
        raise AmendmentError("parent state node has been amended-out")

    _check_state_amendment_authority(actor, parent_state_node=parent)

    # Pull defaults from the matter's program YAML.
    from reasonbook.models import Matter  # local import to avoid cycle

    matter = session.get(Matter, matter_id)
    if matter is None:
        raise AmendmentError(f"matter {matter_id} not found")

    defaults = get_engine().defaults_for(matter.program_id)
    final_archetypes = list(
        active_archetypes if active_archetypes is not None else defaults.recipient.active_archetypes
    )
    final_role = (
        authority_role
        or defaults.recipient.authority_role
        or "certifying_officer"
    )

    node = MatterNode(
        matter_id=matter_id,
        parent_node_id=parent.id,
        tier="recipient",
        participant_org_id=participant_org_id,
        active_archetypes=final_archetypes,
        authority_role=final_role,
        added_by_user_id=actor.id,
    )
    session.add(node)
    session.flush()
    log.info(
        "matter.amend.add_recipient matter_id=%s state_node=%s recipient_org=%s",
        matter_id,
        parent_state_node_id,
        participant_org_id,
    )
    return node


def _check_federal_only(actor: User) -> None:
    """Federal-tier-only amendments (add/remove state, change
    authority_role, change matter-level fields) per §13.2."""
    if actor.tier != "federal":
        raise AmendmentAuthorityError(
            "this amendment is federal-tier only"
        )


def add_state_node(
    *,
    matter_id: uuid.UUID,
    participant_org_id: uuid.UUID,
    active_archetypes: list[str] | None = None,
    authority_role: str | None = None,
    actor: User,
    session: Session,
) -> MatterNode:
    """Federal-tier amendment: add a new state stakeholder to a matter.

    Inserts an matter_nodes row at tier='state' whose parent is
    the matter's federal root. Defaults pull from the program YAML's
    state-tier defaults when not supplied.
    """
    _check_federal_only(actor)

    from reasonbook.models import Matter  # local to avoid cycle

    matter = session.get(Matter, matter_id)
    if matter is None:
        raise AmendmentError(f"matter {matter_id} not found")

    federal_root = (
        session.query(MatterNode)
        .filter_by(matter_id=matter_id, tier="federal", removed_at=None)
        .one_or_none()
    )
    if federal_root is None:
        raise AmendmentError(
            f"matter {matter_id} has no active federal root (invariant violated)"
        )

    defaults = get_engine().defaults_for(matter.program_id)
    final_archetypes = list(
        active_archetypes if active_archetypes is not None else defaults.state.active_archetypes
    )
    final_role = (
        authority_role
        or defaults.state.authority_role
        or "state_program_director"
    )

    node = MatterNode(
        matter_id=matter_id,
        parent_node_id=federal_root.id,
        tier="state",
        participant_org_id=participant_org_id,
        active_archetypes=final_archetypes,
        authority_role=final_role,
        added_by_user_id=actor.id,
    )
    session.add(node)
    session.flush()
    log.info(
        "matter.amend.add_state matter_id=%s state_org=%s",
        matter_id,
        participant_org_id,
    )
    return node


def remove_state_node(
    *,
    state_node_id: uuid.UUID,
    actor: User,
    session: Session,
) -> MatterNode:
    """Federal-tier amendment: soft-remove a state node.

    Children (recipient nodes hanging off this state) are NOT
    automatically soft-removed — they keep their rows, but tier scope
    naturally excludes them once the state's link to the federal root
    is severed (no longer in any user's fund_flow_path). The historical
    record stays intact for audit.
    """
    _check_federal_only(actor)

    node = session.get(MatterNode, state_node_id)
    if node is None:
        raise AmendmentError(f"node {state_node_id} not found")
    if node.tier != "state":
        raise AmendmentError(
            f"only state nodes can be removed via this amendment; got {node.tier!r}"
        )
    if node.removed_at is not None:
        raise AmendmentError("node is already removed")

    node.removed_at = datetime.now(UTC)
    session.flush()
    log.info(
        "matter.amend.remove_state node_id=%s matter_id=%s",
        state_node_id,
        node.matter_id,
    )
    return node


def amend_node_active_archetypes(
    *,
    node_id: uuid.UUID,
    new_active_archetypes: list[str],
    actor: User,
    session: Session,
) -> MatterNode:
    """Tier-above amendment: change a node's active_archetypes list.

    Per §13.2: federal amends state's list; state amends recipient's
    list. Append-only — writes a new row with the new list and stamps
    removed_at on the prior. The new row inherits the prior's
    matter_id / parent_node_id / participant_org_id / authority_role,
    so the only delta is active_archetypes.

    Returns the new row (the prior is left in place with removed_at set).
    """
    prior = session.get(MatterNode, node_id)
    if prior is None:
        raise AmendmentError(f"node {node_id} not found")
    if prior.removed_at is not None:
        raise AmendmentError("node has already been amended-out")

    # Authority: tier ABOVE the node owns its archetypes.
    if prior.tier == "federal":
        raise AmendmentError(
            "federal root archetypes are matter-fixed; create a new matter instead"
        )
    if prior.tier == "state":
        # Federal owns this amendment.
        _check_federal_only(actor)
    elif prior.tier == "recipient":
        # Parent state's tier owns this amendment; federal may also.
        parent = (
            session.get(MatterNode, prior.parent_node_id)
            if prior.parent_node_id
            else None
        )
        if parent is None:
            raise AmendmentError("recipient node has no parent (invariant violated)")
        _check_state_amendment_authority(actor, parent_state_node=parent)
    else:
        raise AmendmentError(f"unsupported node tier: {prior.tier!r}")

    # Append-only: stamp prior, write new row with same identity fields.
    prior.removed_at = datetime.now(UTC)
    new_node = MatterNode(
        matter_id=prior.matter_id,
        parent_node_id=prior.parent_node_id,
        tier=prior.tier,
        participant_org_id=prior.participant_org_id,
        active_archetypes=list(new_active_archetypes),
        authority_role=prior.authority_role,
        added_by_user_id=actor.id,
    )
    session.add(new_node)
    session.flush()
    log.info(
        "matter.amend.archetypes node_id=%s -> new_node_id=%s (tier=%s)",
        node_id,
        new_node.id,
        prior.tier,
    )
    return new_node


def amend_matter_fields(
    *,
    matter_id: uuid.UUID,
    actor: User,
    session: Session,
    amount_obligated: Decimal | None = None,
    terms: str | None = None,
    retention_months: int | None = None,
) -> dict[str, Any]:
    """Federal-only amendment of matter-level fields per §13.2.

    Mutates the matters row in place (these aren't nodes — no
    append-only history per the node-graph pattern). Each changed field
    writes a ``matter_field_amended`` event on the originating Decision
    so the audit trail captures who/when/before/after. Returns a dict
    of {field_name: {before, after}} for the route to surface.

    Only the fields whose kwargs are not None are touched. Returns an
    empty dict if no fields actually changed value.
    """
    _check_federal_only(actor)

    from reasonbook.models import Matter  # local to avoid cycle

    matter = session.get(Matter, matter_id)
    if matter is None:
        raise AmendmentError(f"matter {matter_id} not found")

    changes: dict[str, dict[str, Any]] = {}

    if amount_obligated is not None and amount_obligated != matter.amount_obligated:
        changes["amount_obligated"] = {
            "before": (
                str(matter.amount_obligated)
                if matter.amount_obligated is not None
                else None
            ),
            "after": str(amount_obligated),
        }
        matter.amount_obligated = amount_obligated

    if terms is not None and terms != matter.terms:
        changes["terms"] = {"before": matter.terms, "after": terms}
        matter.terms = terms

    if retention_months is not None and retention_months != matter.retention_months:
        changes["retention_months"] = {
            "before": matter.retention_months,
            "after": retention_months,
        }
        matter.retention_months = retention_months

    if not changes:
        return {}

    # Write an audit event on the originating Decision (when set).
    if matter.originating_decision_id is not None:
        from reasonbook.models import Decision

        originating = session.get(Decision, matter.originating_decision_id)
        if originating is not None:
            session.add(
                DecisionEvent(
                    decision_id=originating.id,
                    tenant_id=originating.tenant_id,
                    workflow_id=originating.workflow_id,
                    user_id=actor.id,
                    action="matter_field_amended",
                    event_metadata={
                        "matter_id": str(matter.id),
                        "changes": changes,
                    },
                )
            )
    log.info(
        "matter.amend.fields matter_id=%s changed=%s",
        matter_id,
        list(changes.keys()),
    )
    session.flush()
    return changes


def remove_recipient_node(
    *,
    recipient_node_id: uuid.UUID,
    actor: User,
    session: Session,
) -> MatterNode:
    """Soft-remove a recipient node by stamping removed_at.

    The row stays; readers filter by ``removed_at IS NULL``. The unique
    partial index frees up the (matter, participant_org) slot so a
    later re-add is allowed.
    """
    node = session.get(MatterNode, recipient_node_id)
    if node is None:
        raise AmendmentError(f"node {recipient_node_id} not found")
    if node.tier != "recipient":
        raise AmendmentError(
            f"only recipient nodes can be removed via this amendment; got {node.tier!r}"
        )
    if node.removed_at is not None:
        raise AmendmentError("node is already removed")

    # Authorization: parent must be a state node; same auth as add.
    if node.parent_node_id is None:
        raise AmendmentError("recipient node has no parent (data invariant violated)")
    parent_state = session.get(MatterNode, node.parent_node_id)
    if parent_state is None or parent_state.tier != "state":
        raise AmendmentError("recipient node's parent is not a state node")
    _check_state_amendment_authority(actor, parent_state_node=parent_state)

    node.removed_at = datetime.now(UTC)
    session.flush()
    log.info(
        "matter.amend.remove_recipient node_id=%s matter_id=%s",
        recipient_node_id,
        node.matter_id,
    )
    return node
