# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter create transaction (TENANCY-MODEL §10 step 5, §12).

Covers the happy path (federal root + 2 states + 1 recipient), the
idempotency rule (same key → same id, second call is a no-op), and
the FK loop closure (originating_decision_id is set to the newly-minted
federal Decision).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.db import schema_prefix
from reasonbook.matters.service import (
    MatterCreateError,
    RecipientSpec,
    StakeholderSpec,
    _idempotency_id,
    create_matter,
)
from reasonbook.models import Matter, MatterNode, Decision, DecisionEvent
from reasonbook.semantic.engine import init_engine


@pytest.fixture(autouse=True)
def _engine() -> None:
    init_engine()


def _bootstrap(clean_db: Engine) -> dict[str, uuid.UUID | str]:
    """Insert the fixture orgs + the actor user the matter service needs."""
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

    return {
        "actor": actor,
        "georgia": georgia,
        "ohio": ohio,
        "delta": delta,
    }


def test_idempotency_id_is_deterministic() -> None:
    a = _idempotency_id(
        program_id="cdbg",
        awarding_agency="HUD",
        period_label="FY26",
        federal_application_ref="HUD-2026-001",
    )
    b = _idempotency_id(
        program_id="cdbg",
        awarding_agency="HUD",
        period_label="FY26",
        federal_application_ref="HUD-2026-001",
    )
    c = _idempotency_id(
        program_id="cdbg",
        awarding_agency="HUD",
        period_label="FY27",  # different period
        federal_application_ref="HUD-2026-001",
    )
    assert a == b
    assert a != c


def test_happy_path_creates_full_tree(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("1200000.00"),
            period_label="FY26",
            terms="Uniform Guidance 2 CFR 200",
            federal_application_ref="HUD-2026-001",
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
        s.commit()

        # Matter row.
        assert matter.program_id == "cdbg"
        assert matter.awarding_agency == "HUD"
        assert matter.amount_obligated == Decimal("1200000.00")
        assert matter.federal_archetype == "formula_allocation"
        assert matter.originating_decision_id is not None

        # Federal root + 2 state nodes + 1 recipient node = 4.
        nodes = s.query(MatterNode).filter_by(matter_id=matter.id).all()
        assert len(nodes) == 4
        tiers = sorted(n.tier for n in nodes)
        assert tiers == ["federal", "recipient", "state", "state"]

        federal_root = next(n for n in nodes if n.tier == "federal")
        assert federal_root.participant_org_id is None
        assert federal_root.parent_node_id is None
        assert federal_root.active_archetypes == ["formula_allocation"]
        assert federal_root.authority_role == "awarding_official"

        state_nodes = [n for n in nodes if n.tier == "state"]
        assert {n.participant_org_id for n in state_nodes} == {ctx["georgia"], ctx["ohio"]}
        for sn in state_nodes:
            assert sn.parent_node_id == federal_root.id
            assert sn.authority_role == "state_program_director"

        recip = next(n for n in nodes if n.tier == "recipient")
        assert recip.participant_org_id == ctx["delta"]
        recip_parent = next(n for n in state_nodes if n.participant_org_id == ctx["georgia"])
        assert recip.parent_node_id == recip_parent.id
        assert recip.authority_role == "certifying_officer"

        # Originating Decision exists + is wired to federal root.
        decision = s.get(Decision, matter.originating_decision_id)
        assert decision is not None
        assert decision.matter_id == matter.id
        assert decision.matter_node_id == federal_root.id
        assert decision.fund_flow_path == []

        # Ledger: 'created' + 'matter_created' + 4×'node_established'.
        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=decision.id)
            .order_by(DecisionEvent.created_at.asc(), DecisionEvent.id.asc())
            .all()
        )
        actions = [e.action for e in events]
        assert actions.count("matter_created") == 1
        assert actions.count("node_established") == 4


def test_idempotent_replay(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        b1 = create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("1200000.00"),
            period_label="FY26",
            terms="terms",
            federal_application_ref="HUD-2026-IDEM",
            states=[StakeholderSpec(participant_org_id=ctx["georgia"])],
            recipients=[],
            actor_user_id=ctx["actor"],
            tenant_id="us-fed",
            session=s,
        )
        s.commit()
        b2 = create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("1200000.00"),
            period_label="FY26",
            terms="terms",
            federal_application_ref="HUD-2026-IDEM",
            states=[StakeholderSpec(participant_org_id=ctx["georgia"])],
            recipients=[],
            actor_user_id=ctx["actor"],
            tenant_id="us-fed",
            session=s,
        )
        s.commit()

        assert b1.id == b2.id

        # Exactly one matter + 2 nodes (federal root + 1 state).
        matters = s.query(Matter).filter_by(id=b1.id).all()
        nodes = s.query(MatterNode).filter_by(matter_id=b1.id).all()
        assert len(matters) == 1
        assert len(nodes) == 2


def test_unknown_program_raises(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s, pytest.raises(MatterCreateError, match="unknown program_id"):
        create_matter(
            program_id="not-a-program",
            awarding_agency="HUD",
            amount_obligated=Decimal("0"),
            period_label="FY26",
            terms="",
            federal_application_ref="x",
            states=[],
            recipients=[],
            actor_user_id=ctx["actor"],
            tenant_id="us-fed",
            session=s,
        )


def test_federal_direct_recipient_hangs_off_federal_root(clean_db: Engine) -> None:
    """P29: parent_state_org_id=None puts the recipient directly under
    the federal root (no state tier in between). Matches USAspending
    prime-award data, which is mostly agency→recipient direct.
    """
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        matter = create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("4_500_000.00"),
            period_label="FY26",
            terms="USAspending prime — federal-direct",
            federal_application_ref="HUD-DIRECT-001",
            states=[],
            recipients=[
                RecipientSpec(
                    parent_state_org_id=None,
                    participant_org_id=ctx["delta"],
                ),
            ],
            actor_user_id=ctx["actor"],
            tenant_id="us-fed",
            session=s,
        )
        s.commit()

        nodes = s.query(MatterNode).filter_by(matter_id=matter.id).all()
        # Federal root + recipient = 2 nodes. NO state tier.
        assert len(nodes) == 2
        assert sorted(n.tier for n in nodes) == ["federal", "recipient"]

        federal_root = next(n for n in nodes if n.tier == "federal")
        recip = next(n for n in nodes if n.tier == "recipient")
        # Recipient parent IS the federal root, not a state.
        assert recip.parent_node_id == federal_root.id
        assert recip.participant_org_id == ctx["delta"]


def test_recipient_without_declared_parent_state_raises(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    bogus_state = uuid.uuid4()
    with Session(clean_db) as s, pytest.raises(MatterCreateError, match="is not in the states"):
        create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("100"),
            period_label="FY26",
            terms="",
            federal_application_ref="HUD-BAD-PARENT",
            states=[StakeholderSpec(participant_org_id=ctx["georgia"])],
            recipients=[
                RecipientSpec(
                    parent_state_org_id=bogus_state,  # not in states[]
                    participant_org_id=ctx["delta"],
                ),
            ],
            actor_user_id=ctx["actor"],
            tenant_id="us-fed",
            session=s,
        )
