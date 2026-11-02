# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Control-points service tests (ADR-11).

Covers:
  * materialize_for_matter seeds N rows per (node × archetype × trigger)
  * materialize_for_matter is idempotent
  * find_pending_for_decision returns the matching pending row
  * clear() flips status to cleared and writes a hash-chained event
  * mark_gap() flips to skipped, requires a reason, writes an event
  * mark_gap on already-cleared raises ControlPointError
  * finalize_decision clears the matching control point as a side-effect
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.matters.service import RecipientSpec, StakeholderSpec, create_matter
from reasonbook.db import schema_prefix
from reasonbook.control_points import (
    ControlPointError,
    clear,
    find_pending_for_decision,
    mark_gap,
    materialize_for_matter,
)
from reasonbook.decisions.manager import claim_decision, finalize_decision
from reasonbook.models import (
    Matter,
    ControlPoint,
    Decision,
    DecisionEvent,
)
from reasonbook.semantic.engine import get_engine, init_engine


@pytest.fixture(autouse=True)
def _engine() -> None:
    init_engine()


def _bootstrap(clean_db: Engine) -> dict[str, uuid.UUID]:
    """Minimal seed: one tenant, one user, three orgs."""
    actor = uuid.uuid4()
    georgia = uuid.uuid4()
    ohio = uuid.uuid4()
    delta = uuid.uuid4()

    with clean_db.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) VALUES ('us-fed', 'US Fed')")
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, tier) "
                "VALUES (:id, 'us-fed', 'fed-actor', 'fed@example.com', 'x', "
                "'Fed Actor', 'member', 'federal')"
            ),
            {"id": actor},
        )
        for org_id, name, kind in (
            (georgia, "Georgia", "state"),
            (ohio, "Ohio", "state"),
            (delta, "Delta CDC", "recipient"),
        ):
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                    "VALUES (:id, :kind, :name)"
                ),
                {"id": org_id, "kind": kind, "name": name},
            )

    return {"actor": actor, "georgia": georgia, "ohio": ohio, "delta": delta}


def _make_matter(s: Session, ctx: dict[str, uuid.UUID]) -> Matter:
    return create_matter(
        program_id="cdbg",
        awarding_agency="HUD",
        amount_obligated=Decimal("1200000.00"),
        period_label="FY26",
        terms="Uniform Guidance 2 CFR 200",
        federal_application_ref="HUD-CP-001",
        states=[
            StakeholderSpec(participant_org_id=ctx["georgia"]),
            StakeholderSpec(participant_org_id=ctx["ohio"]),
        ],
        recipients=[
            RecipientSpec(
                parent_state_org_id=ctx["georgia"],
                participant_org_id=ctx["delta"],
            ),
        ],
        actor_user_id=ctx["actor"],
        tenant_id="us-fed",
        session=s,
    )


def _trigger_count_for_archetype(archetype_id: str) -> int:
    """How many upstream_review trigger events the archetype declares.

    Always 5 (the UpstreamReview model has five fixed fields), but read
    from the live model so the test catches a future schema change.
    """
    archetype = get_engine().get_archetype(archetype_id)
    review = archetype.upstream_review
    return sum(
        1
        for _ in (
            review.on_promote,
            review.on_outcome,
            review.on_modification,
            review.on_adverse_action,
            review.on_closeout,
        )
    )


def test_materialize_seeds_one_row_per_node_for_gate_triggers_only(clean_db: Engine) -> None:
    """Materialize is selective per the v1 contract:
    - Only the matter's ``federal_archetype`` (not every active archetype)
    - Only triggers with ``gate`` (skip ``notify`` — informational, not a clearance)
    """
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()

        # formula_allocation declares 3 gates (on_modification,
        # on_adverse_action, on_closeout). 4 nodes (federal + 2 state +
        # 1 recipient) × 3 gates = 12.
        archetype = get_engine().get_archetype(matter.federal_archetype)
        review = archetype.upstream_review
        gate_triggers = [
            t
            for t in (
                "on_promote",
                "on_outcome",
                "on_modification",
                "on_adverse_action",
                "on_closeout",
            )
            if getattr(review, t) == "gate"
        ]

        from reasonbook.models import MatterNode

        n_nodes = (
            s.query(MatterNode).filter_by(matter_id=matter.id, removed_at=None).count()
        )
        expected = n_nodes * len(gate_triggers)

        inserted = materialize_for_matter(matter.id, session=s)
        s.commit()
        assert inserted == expected

        rows = s.query(ControlPoint).filter_by(matter_id=matter.id).all()
        assert len(rows) == expected
        assert {r.status for r in rows} == {"pending"}

        # Tier denormalization matches each row's source node.
        tiers = {r.tier for r in rows}
        assert tiers == {"federal", "state", "recipient"}


def test_materialize_is_idempotent(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()
        first = materialize_for_matter(matter.id, session=s)
        s.commit()
        second = materialize_for_matter(matter.id, session=s)
        s.commit()
        assert first > 0
        assert second == 0


def test_clear_flips_status_and_writes_event(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()
        materialize_for_matter(matter.id, session=s)
        s.commit()

        # formula_allocation gates on on_modification — pick that row.
        cp = (
            s.query(ControlPoint)
            .filter_by(matter_id=matter.id, trigger_event="on_modification", tier="federal")
            .first()
        )
        assert cp is not None and cp.status == "pending"
        assert cp.gate_type == "gate"

        decision = s.get(Decision, matter.originating_decision_id)
        assert decision is not None

        cleared = clear(cp.id, decision=decision, user_id=ctx["actor"], session=s)
        s.commit()

        assert cleared.status == "cleared"
        assert cleared.cleared_by_decision_id == decision.id
        assert cleared.cleared_by_user_id == ctx["actor"]
        assert cleared.cleared_at is not None

        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=decision.id, action="control_point_cleared")
            .all()
        )
        assert len(events) == 1
        meta = events[0].event_metadata or {}
        assert meta.get("control_point_id") == str(cp.id)
        assert meta.get("trigger_event") == "on_modification"


def test_clear_rejects_non_pending(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()
        materialize_for_matter(matter.id, session=s)
        s.commit()

        cp = s.query(ControlPoint).filter_by(matter_id=matter.id).first()
        assert cp is not None
        decision = s.get(Decision, matter.originating_decision_id)
        assert decision is not None

        clear(cp.id, decision=decision, user_id=ctx["actor"], session=s)
        s.commit()
        with pytest.raises(ControlPointError):
            clear(cp.id, decision=decision, user_id=ctx["actor"], session=s)


def test_mark_gap_requires_reason_and_writes_event(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()
        materialize_for_matter(matter.id, session=s)
        s.commit()

        cp = s.query(ControlPoint).filter_by(matter_id=matter.id).first()
        assert cp is not None
        decision = s.get(Decision, matter.originating_decision_id)
        assert decision is not None

        with pytest.raises(ControlPointError):
            mark_gap(
                cp.id,
                decision=decision,
                user_id=ctx["actor"],
                reason="   ",
                session=s,
            )

        skipped = mark_gap(
            cp.id,
            decision=decision,
            user_id=ctx["actor"],
            reason="Sponsor accepted this control as not applicable; risk owned upstream",
            session=s,
        )
        s.commit()
        assert skipped.status == "skipped"
        assert skipped.named_gap_reason is not None
        assert skipped.named_gap_reason.startswith("Sponsor accepted")

        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=decision.id, action="control_point_skipped")
            .all()
        )
        assert len(events) == 1
        assert events[0].comment is not None
        assert "Sponsor accepted" in events[0].comment


def test_finalize_decision_clears_matching_control_point(clean_db: Engine) -> None:
    """Decision finalize is the canonical clear path — verify the wiring.

    No archetype currently declares ``on_promote: gate`` (all default to
    notify), so materialize doesn't create an on_promote row. We insert
    one manually to exercise the finalize → find_pending → clear path.
    """
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = _make_matter(s, ctx)
        s.commit()
        materialize_for_matter(matter.id, session=s)
        s.commit()

        decision = s.get(Decision, matter.originating_decision_id)
        assert decision is not None
        assert decision.matter_node_id is not None  # federal root

        # Inject an on_promote=gate row so finalize has something to clear.
        injected_cp = ControlPoint(
            id=uuid.uuid4(),
            tenant_id=decision.tenant_id,
            matter_id=matter.id,
            node_id=decision.matter_node_id,
            tier="federal",
            archetype_id=decision.decision_type,
            trigger_event="on_promote",
            gate_type="gate",
            required_authority_role="awarding_official",
            status="pending",
        )
        s.add(injected_cp)
        s.commit()

        cp_before = find_pending_for_decision(decision, "on_promote", session=s)
        assert cp_before is not None
        assert cp_before.id == injected_cp.id

        # Grant authority on the workflow so claim + finalize can pass.
        # The originating Decision uses the federal_archetype workflow;
        # we mint a max-level authority row for the actor.
        s.execute(
            text(
                f"INSERT INTO {schema_prefix()}user_workflow_authority "
                "(id, user_id, workflow_id, level, granted_at, granted_by) "
                "VALUES (gen_random_uuid(), :uid, :wf, 100, "
                "        CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": ctx["actor"], "wf": decision.workflow_id},
        )
        s.commit()

        # open → in_progress (required before finalize) → decided.
        claim_decision(
            decision_id=decision.id,
            user_id=ctx["actor"],
            session=s,
        )
        finalize_decision(
            decision_id=decision.id,
            user_id=ctx["actor"],
            selected_option="advance",
            rationale="Federal authority advances the formula allocation",
            session=s,
        )
        s.commit()

        cp_after = s.get(ControlPoint, cp_before.id)
        assert cp_after is not None
        assert cp_after.status == "cleared"
        assert cp_after.cleared_by_decision_id == decision.id
