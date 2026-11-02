# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter create transaction — TENANCY-MODEL.md §12.

Atomic operation that creates an award matter, its fund-flow tree, and
the originating federal Decision in one transaction. Idempotent on the
deterministic (program_id, awarding_agency, period_label,
federal_application_ref) key — re-running with the same key is a no-op.

Matter creation IS the entitlement grant (§12.3): once the nodes are
written, state and recipient users at the corresponding participant_orgs
see the matter through ``apply_tier_scope`` automatically. No separate
"grant" row exists.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.decisions.manager import create_decision
from reasonbook.models import DecisionEvent, Matter, MatterNode
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class StakeholderSpec:
    """One state stakeholder for the matter's create call.

    ``active_archetypes`` and ``authority_role`` are optional; if not
    supplied, the program's state-tier defaults are used (the persisted
    value on the node row is source of truth from t0 forward).
    """

    participant_org_id: uuid.UUID
    active_archetypes: list[str] | None = None
    authority_role: str | None = None


@dataclass(frozen=True)
class RecipientSpec:
    """One recipient in a matter.

    ``parent_state_org_id`` — when set, must match a participant_org_id
    supplied as a StakeholderSpec; the recipient node is wired to that
    state. When ``None``, the recipient is **federal-direct** and hangs
    off the federal root node — used when no state pass-through exists
    (most prime-award USAspending matters). The two modes can coexist
    on the same matter: some recipients via a state, others direct.
    """

    parent_state_org_id: uuid.UUID | None
    participant_org_id: uuid.UUID
    active_archetypes: list[str] | None = None
    authority_role: str | None = None


class MatterCreateError(ValueError):
    """Matter create failed validation (bad spec, unknown program, etc.)."""


def _idempotency_id(
    *,
    program_id: str,
    awarding_agency: str,
    period_label: str,
    federal_application_ref: str,
) -> uuid.UUID:
    """Derive a deterministic matter uuid from the create-key tuple.

    Same inputs → same UUID; subsequent INSERTs collide on the PK so
    retries become no-ops (per §12.2). UUIDv5 over a namespace UUID
    derived from a fixed sentinel keeps the mapping reproducible
    without leaking the inputs into the id.
    """
    key = f"{program_id}|{awarding_agency}|{period_label}|{federal_application_ref}"
    # Hex-only sentinel namespace ('df' = Reasonbook fragment).
    namespace = uuid.UUID("00000000-0000-0000-0000-0000000000df")
    return uuid.uuid5(namespace, hashlib.sha256(key.encode()).hexdigest())


def create_matter(
    *,
    program_id: str,
    awarding_agency: str,
    amount_obligated: Decimal,
    period_label: str,
    terms: str,
    federal_application_ref: str,
    states: list[StakeholderSpec],
    recipients: list[RecipientSpec],
    actor_user_id: uuid.UUID,
    tenant_id: str,
    session: Session,
    # DP tenancy substrate — owning agency for scope filtering. Stamped
    # on the matter AND on the originating decision so the scope filter
    # can reject at either the decision or matter level. Nullable so
    # older callers keep working; demo seed + future admin flows always
    # supply it.
    agency_id: uuid.UUID | None = None,
) -> Matter:
    """Atomic matter create per §12.1.

    Steps within the caller's transaction:

    1. Derive deterministic matter id from the create-key tuple.
    2. INSERT matters (skip if already present — idempotent).
    3. Build the fund-flow tree: federal root → state nodes → recipient
       nodes. Active_archetypes / authority_role pull from program
       defaults when not overridden in the spec.
    4. Mint the originating federal Decision via the normal lifecycle
       (bound to matter_id + federal-root matter_node_id,
       fund_flow_path=[]).
    5. Close the originating_decision_id FK loop.
    6. Append ``matter_created`` + per-node ``node_established`` events
       to the Decision's ledger.

    Caller owns the session/transaction boundary — if any step raises,
    a rollback on the outer transaction undoes the whole matter.
    """
    engine = get_engine()
    try:
        program = engine.get_program(program_id)
    except KeyError as exc:
        raise MatterCreateError(f"unknown program_id: {program_id}") from exc

    defaults = program.defaults

    # Validate recipients reference declared states. Federal-direct
    # recipients (parent_state_org_id=None) skip this check — they hang
    # off the federal root instead.
    state_org_ids = {s.participant_org_id for s in states}
    for r in recipients:
        if r.parent_state_org_id is not None and r.parent_state_org_id not in state_org_ids:
            raise MatterCreateError(
                f"recipient {r.participant_org_id} parent_state_org_id "
                f"{r.parent_state_org_id} is not in the states[] list"
            )

    matter_id = _idempotency_id(
        program_id=program_id,
        awarding_agency=awarding_agency,
        period_label=period_label,
        federal_application_ref=federal_application_ref,
    )

    # Idempotency check: if the matter already exists, return it.
    existing = session.get(Matter, matter_id)
    if existing is not None:
        # Backfill agency_id when the row predates the agency substrate
        # (migration 0046). Keeps re-seeds honest without a separate
        # backfill script.
        if existing.agency_id is None and agency_id is not None:
            existing.agency_id = agency_id
            session.flush()
            log.info(
                "matter.create backfilled agency_id=%s on matter_id=%s",
                agency_id,
                matter_id,
            )
        log.info(
            "matter.create idempotent_noop matter_id=%s program_id=%s",
            matter_id,
            program_id,
        )
        return existing

    # 2. Insert matter (originating_decision_id stays NULL until step 5).
    matter = Matter(
        id=matter_id,
        program_id=program_id,
        federal_archetype=program.profile.binds_archetype,
        awarding_agency=awarding_agency,
        agency_id=agency_id,
        amount_obligated=amount_obligated,
        period_label=period_label,
        terms=terms,
        retention_months=(
            program.reconstructability.get("retention_months")
            if isinstance(program.reconstructability, dict)
            else None
        ),
        originating_decision_id=None,
        created_by_user_id=actor_user_id,
    )
    session.add(matter)
    session.flush()

    # 3a. Federal root node.
    federal_root = MatterNode(
        matter_id=matter.id,
        parent_node_id=None,
        tier="federal",
        participant_org_id=None,
        active_archetypes=list(defaults.federal.active_archetypes),
        authority_role=defaults.federal.authority_role or "awarding_official",
        added_by_user_id=actor_user_id,
    )
    session.add(federal_root)
    session.flush()

    # 3b. State nodes.
    state_node_by_org: dict[uuid.UUID, MatterNode] = {}
    for spec in states:
        node = MatterNode(
            matter_id=matter.id,
            parent_node_id=federal_root.id,
            tier="state",
            participant_org_id=spec.participant_org_id,
            active_archetypes=list(
                spec.active_archetypes or defaults.state.active_archetypes
            ),
            authority_role=(
                spec.authority_role
                or defaults.state.authority_role
                or "state_program_director"
            ),
            added_by_user_id=actor_user_id,
        )
        session.add(node)
        state_node_by_org[spec.participant_org_id] = node
    session.flush()

    # 3c. Recipient nodes — under a declared state when one is named,
    # otherwise federal-direct (parent = federal root) per P29.
    recipient_nodes: list[MatterNode] = []
    for r in recipients:
        parent_node = (
            state_node_by_org[r.parent_state_org_id]
            if r.parent_state_org_id is not None
            else federal_root
        )
        node = MatterNode(
            matter_id=matter.id,
            parent_node_id=parent_node.id,
            tier="recipient",
            participant_org_id=r.participant_org_id,
            active_archetypes=list(
                r.active_archetypes or defaults.recipient.active_archetypes
            ),
            authority_role=(
                r.authority_role
                or defaults.recipient.authority_role
                or "certifying_officer"
            ),
            added_by_user_id=actor_user_id,
        )
        session.add(node)
        recipient_nodes.append(node)
    session.flush()

    # 4. Originating federal Decision.
    federal_decision = create_decision(
        tenant_id=tenant_id,
        workflow_id=program_id,
        decision_type=program.profile.binds_archetype,
        title=f"{program_id.upper()} {period_label} — federal award",
        created_by=actor_user_id,
        matter_id=matter.id,
        matter_node_id=federal_root.id,
        fund_flow_path=[],
        agency_id=agency_id,
        session=session,
    )

    # 5. Close the FK loop.
    matter.originating_decision_id = federal_decision.id
    session.flush()

    # 6. Append matter_created + per-node node_established events.
    _append_event(
        session,
        decision_id=federal_decision.id,
        tenant_id=tenant_id,
        workflow_id=program_id,
        user_id=actor_user_id,
        action="matter_created",
        event_metadata={
            "matter_id": str(matter.id),
            "program_id": program_id,
            "awarding_agency": awarding_agency,
            "period_label": period_label,
            "amount_obligated": str(amount_obligated),
        },
    )
    _append_event(
        session,
        decision_id=federal_decision.id,
        tenant_id=tenant_id,
        workflow_id=program_id,
        user_id=actor_user_id,
        action="node_established",
        event_metadata={
            "node_id": str(federal_root.id),
            "tier": "federal",
            "participant_org_id": None,
            "active_archetypes": list(federal_root.active_archetypes),
        },
    )
    for node in state_node_by_org.values():
        _append_event(
            session,
            decision_id=federal_decision.id,
            tenant_id=tenant_id,
            workflow_id=program_id,
            user_id=actor_user_id,
            action="node_established",
            event_metadata={
                "node_id": str(node.id),
                "tier": "state",
                "participant_org_id": str(node.participant_org_id),
                "active_archetypes": list(node.active_archetypes),
            },
        )
    for node in recipient_nodes:
        _append_event(
            session,
            decision_id=federal_decision.id,
            tenant_id=tenant_id,
            workflow_id=program_id,
            user_id=actor_user_id,
            action="node_established",
            event_metadata={
                "node_id": str(node.id),
                "tier": "recipient",
                "participant_org_id": str(node.participant_org_id),
                "active_archetypes": list(node.active_archetypes),
            },
        )
    session.flush()

    log.info(
        "matter.create program_id=%s matter_id=%s states=%d recipients=%d",
        program_id,
        matter.id,
        len(states),
        len(recipients),
    )
    return matter


def _append_event(
    session: Session,
    *,
    decision_id: uuid.UUID,
    tenant_id: str,
    workflow_id: str,
    user_id: uuid.UUID,
    action: str,
    event_metadata: dict[str, Any],
) -> None:
    """Append one row to platform.decision_events."""
    session.add(
        DecisionEvent(
            decision_id=decision_id,
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            user_id=user_id,
            action=action,
            event_metadata=event_metadata,
        )
    )
