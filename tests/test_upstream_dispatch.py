# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Upstream-review dispatch — notify vs gate per archetype + action_kind.

TENANCY-MODEL §5 + §10 step 7.
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
from reasonbook.models import MatterNode, Decision, DecisionEvent
from reasonbook.semantic.engine import init_engine
from reasonbook.upstream.dispatch import (
    UpstreamDispatchOutcome,
    dispatch_upstream,
)


@pytest.fixture(autouse=True)
def _engine() -> None:
    init_engine()


def _bootstrap(clean_db: Engine) -> dict[str, uuid.UUID | str]:
    """Insert tenant + actor + 3 participant orgs + a CDBG matter.

    Returns the federal/state/recipient node ids so tests can pin a
    Decision to a known level of the tree.
    """
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
            (delta, "Delta", "recipient"),
        ):
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                    "VALUES (:id, :kind, :name)"
                ),
                {"id": org_id, "kind": kind, "name": name},
            )

    with Session(clean_db) as s:
        matter = create_matter(
            program_id="cdbg",  # binds to formula_allocation archetype
            awarding_agency="HUD",
            amount_obligated=Decimal("100"),
            period_label="FY26",
            terms="t",
            federal_application_ref="UP-1",
            states=[
                StakeholderSpec(participant_org_id=georgia),
                StakeholderSpec(participant_org_id=ohio),
            ],
            recipients=[
                RecipientSpec(parent_state_org_id=georgia, participant_org_id=delta),
            ],
            actor_user_id=actor,
            tenant_id="us-fed",
            session=s,
        )
        s.commit()

        nodes = {
            n.tier: n
            for n in s.query(MatterNode).filter_by(matter_id=matter.id).all()
            if n.participant_org_id is None
        }
        federal_root_id = nodes["federal"].id

        ga_node = (
            s.query(MatterNode)
            .filter_by(matter_id=matter.id, participant_org_id=georgia)
            .one()
        )
        delta_node = (
            s.query(MatterNode)
            .filter_by(matter_id=matter.id, participant_org_id=delta)
            .one()
        )

    return {
        "actor": actor,
        "matter_id": matter.id,
        "federal_root_id": federal_root_id,
        "georgia": georgia,
        "ga_node_id": ga_node.id,
        "delta": delta,
        "delta_node_id": delta_node.id,
    }


def _seed_source_decision(
    session: Session, *, ctx: dict, node_id: uuid.UUID, path: list[uuid.UUID]
) -> Decision:
    d = Decision(
        tenant_id="us-fed",
        decision_number=f"SRC-{uuid.uuid4().hex[:6]}",
        workflow_id="cdbg",
        decision_type="formula_allocation",
        title="Source",
        priority="medium",
        severity="medium",
        status="open",
        matter_id=ctx["matter_id"],
        matter_node_id=node_id,
        fund_flow_path=path,
    )
    session.add(d)
    session.flush()
    return d


def test_federal_root_has_no_upstream(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        # Source at federal root.
        d = _seed_source_decision(s, ctx=ctx, node_id=ctx["federal_root_id"], path=[])
        s.commit()
        result = dispatch_upstream(
            source_decision=d,
            action_kind="modification",
            user_id=ctx["actor"],
            session=s,
        )
    assert result.outcome is UpstreamDispatchOutcome.NO_UPSTREAM
    assert result.event_id is None
    assert result.upstream_decision_id is None


def test_state_outcome_notifies(clean_db: Engine) -> None:
    """formula_allocation declares on_outcome=notify (default)."""
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        d = _seed_source_decision(
            s, ctx=ctx, node_id=ctx["ga_node_id"], path=[ctx["georgia"]]
        )
        s.commit()
        source_id = d.id
        result = dispatch_upstream(
            source_decision=d,
            action_kind="outcome",
            user_id=ctx["actor"],
            session=s,
        )
        s.commit()

    assert result.outcome is UpstreamDispatchOutcome.NOTIFIED
    assert result.event_id is not None
    assert result.upstream_decision_id is None

    with Session(clean_db) as s:
        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=source_id, action="upstream_notify_outcome")
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["mode"] == "notify"
        assert events[0].event_metadata["source_tier"] == "state"
        assert events[0].event_metadata["parent_tier"] == "federal"


def test_state_modification_gates(clean_db: Engine) -> None:
    """formula_allocation declares on_modification=gate."""
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        d = _seed_source_decision(
            s, ctx=ctx, node_id=ctx["ga_node_id"], path=[ctx["georgia"]]
        )
        s.commit()
        source_id = d.id
        result = dispatch_upstream(
            source_decision=d,
            action_kind="modification",
            user_id=ctx["actor"],
            session=s,
        )
        s.commit()

    assert result.outcome is UpstreamDispatchOutcome.GATED
    assert result.event_id is not None
    assert result.upstream_decision_id is not None

    with Session(clean_db) as s:
        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=source_id, action="upstream_notify_modification")
            .all()
        )
        assert len(events) == 1
        assert events[0].event_metadata["mode"] == "gate"

        upstream = s.get(Decision, result.upstream_decision_id)
        assert upstream is not None
        assert upstream.matter_node_id == ctx["federal_root_id"]
        assert upstream.fund_flow_path == []
        assert upstream.sla_hours == 120  # default review_sla_hours
        assert upstream.decision_payload["upstream_review"]["action_kind"] == "modification"
        assert upstream.decision_payload["upstream_review"]["source_decision_id"] == str(source_id)


def test_recipient_modification_gates_to_state(clean_db: Engine) -> None:
    """A recipient-tier source escalates to its state parent — not federal."""
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        d = _seed_source_decision(
            s,
            ctx=ctx,
            node_id=ctx["delta_node_id"],
            path=[ctx["georgia"], ctx["delta"]],
        )
        s.commit()
        result = dispatch_upstream(
            source_decision=d,
            action_kind="modification",
            user_id=ctx["actor"],
            session=s,
        )
        s.commit()

    assert result.outcome is UpstreamDispatchOutcome.GATED

    with Session(clean_db) as s:
        upstream = s.get(Decision, result.upstream_decision_id)
        assert upstream is not None
        assert upstream.matter_node_id == ctx["ga_node_id"]
        assert upstream.fund_flow_path == [ctx["georgia"]]
