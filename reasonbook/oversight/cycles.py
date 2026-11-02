# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight cycle lifecycle — create, list, transition.

Cycles move through planned → active → concluded driven by
``cycle_start`` and ``cycle_end`` calendar dates. Manual override is
supported for special cycles (IG audit windows, Congressional inquiry
response cycles, ad-hoc reviews).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from reasonbook.models import OversightCycle

CYCLE_TYPES = ("quarterly", "special", "committee_review", "ig_audit", "appropriations")
CYCLE_STATES = ("planned", "active", "concluded")


class CycleError(ValueError):
    """Raised on oversight-cycle business-rule violations."""


def create_cycle(
    session: Session,
    *,
    tenant_id: str,
    name: str,
    cycle_type: str,
    cycle_start: date,
    cycle_end: date,
    created_by: uuid.UUID,
    committee: str | None = None,
    meeting_date: date | None = None,
    notes: str | None = None,
) -> OversightCycle:
    """Insert a new oversight cycle row in 'planned' state."""
    if cycle_type not in CYCLE_TYPES:
        raise CycleError(f"unknown cycle_type: {cycle_type}")
    if cycle_end < cycle_start:
        raise CycleError("cycle_end must be on or after cycle_start")

    cycle = OversightCycle(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=name,
        cycle_type=cycle_type,
        committee=committee,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        status="planned",
        meeting_date=meeting_date,
        notes=notes,
        created_by=created_by,
    )
    session.add(cycle)
    session.flush()
    return cycle


def transition(session: Session, *, cycle_id: uuid.UUID, to_status: str) -> OversightCycle:
    """Manually move a cycle to a different status.

    Auto-transitions (planned→active on cycle_start, active→concluded on
    cycle_end) run via ``auto_transition_due`` below — this function is
    for manual overrides.
    """
    if to_status not in CYCLE_STATES:
        raise CycleError(f"unknown status: {to_status}")
    cycle = session.get(OversightCycle, cycle_id)
    if cycle is None:
        raise CycleError("cycle not found")
    cycle.status = to_status
    session.flush()
    return cycle


def list_cycles(
    session: Session,
    *,
    tenant_id: str,
    status: str | None = None,
) -> list[OversightCycle]:
    q = session.query(OversightCycle).filter(OversightCycle.tenant_id == tenant_id)
    if status is not None:
        q = q.filter(OversightCycle.status == status)
    return q.order_by(OversightCycle.cycle_start.desc()).all()


def auto_transition_due(session: Session, *, today: date | None = None) -> int:
    """Move any cycles whose calendar boundary has passed.

    Idempotent: planned cycles whose ``cycle_start <= today`` move to
    active; active cycles whose ``cycle_end < today`` move to concluded.
    Returns the number of rows updated.
    """
    today = today or datetime.now(UTC).date()
    moved = 0

    planned = (
        session.query(OversightCycle)
        .filter(OversightCycle.status == "planned", OversightCycle.cycle_start <= today)
        .all()
    )
    for c in planned:
        c.status = "active"
        moved += 1

    active = (
        session.query(OversightCycle)
        .filter(OversightCycle.status == "active", OversightCycle.cycle_end < today)
        .all()
    )
    for c in active:
        c.status = "concluded"
        moved += 1

    if moved:
        session.flush()
    return moved
