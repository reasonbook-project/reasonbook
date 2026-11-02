# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Integration: finalize_decision + record_outcome fire dispatch_upstream.

TENANCY-MODEL §10 step 7 follow-up. The lifecycle handlers in
``dp/decisions/manager`` now call ``dispatch_upstream`` after writing
their own event so the parent matter node sees the upstream signal.

Default upstream_review across all v1 archetypes is ``notify`` for both
on_promote and on_outcome, so the integration writes one
upstream_notify_* event per call. No new Decision is created unless a
gate fires (none in v1 for these two action_kinds).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.matters.service import StakeholderSpec, create_matter
from reasonbook.db import schema_prefix
from reasonbook.decisions.manager import claim_decision, create_decision, finalize_decision
from reasonbook.models import MatterNode, DecisionEvent
from reasonbook.semantic.engine import init_engine


@pytest.fixture(autouse=True)
def _engine() -> None:
    init_engine()


def _bootstrap(clean_db: Engine) -> dict:
    actor = uuid.uuid4()
    ga = uuid.uuid4()

    with clean_db.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) VALUES ('us-fed', 'US Fed')")
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, tier) "
                "VALUES (:id, 'us-fed', 'fed', 'fed@x.com', 'x', 'Fed', "
                "'member', 'federal')"
            ),
            {"id": actor},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                "VALUES (:id, 'state', 'Georgia')"
            ),
            {"id": ga},
        )

    with Session(clean_db) as s:
        matter = create_matter(
            program_id="cdbg",
            awarding_agency="HUD",
            amount_obligated=Decimal("1"),
            period_label="FY26",
            terms="t",
            federal_application_ref="WIRE-1",
            states=[StakeholderSpec(participant_org_id=ga)],
            recipients=[],
            actor_user_id=actor,
            tenant_id="us-fed",
            session=s,
        )
        s.commit()

        ga_node = (
            s.query(MatterNode)
            .filter_by(matter_id=matter.id, participant_org_id=ga)
            .one()
        )
        return {
            "actor": actor,
            "matter_id": matter.id,
            "ga_node_id": ga_node.id,
        }


def test_finalize_at_state_writes_upstream_notify_promote(
    clean_db: Engine,
) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        # Mint a state-tier Decision attached to the GA matter node.
        d = create_decision(
            tenant_id="us-fed",
            workflow_id="cdbg",
            decision_type="formula_allocation",
            title="State-tier decision",
            created_by=ctx["actor"],
            matter_id=ctx["matter_id"],
            matter_node_id=ctx["ga_node_id"],
            fund_flow_path=[],  # synthetic; not exercising tier-scope here
            session=s,
        )
        s.commit()
        decision_id = d.id

        # Need user_can_approve_action to pass — federal users with no
        # workflow authority grant currently bypass the check in tests
        # via the existing UserWorkflowAuthority seed for the test
        # tenant. To keep the integration self-contained, we grant the
        # actor approval on the workflow + action explicitly.
        s.execute(
            text(
                f"INSERT INTO {schema_prefix()}user_workflow_authority "
                "(id, user_id, workflow_id, level, granted_at, granted_by) "
                "VALUES (gen_random_uuid(), :uid, 'cdbg', 5, CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": ctx["actor"]},
        )
        s.commit()

        # Lifecycle: claim (open → in_progress) before finalize.
        claim_decision(decision_id=decision_id, user_id=ctx["actor"], session=s)
        finalize_decision(
            decision_id=decision_id,
            user_id=ctx["actor"],
            selected_option="advance",
            rationale="Standard advance to action",
            session=s,
        )
        s.commit()

    with Session(clean_db) as s:
        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=decision_id, action="upstream_notify_promote")
            .all()
        )
        assert len(events) == 1
        meta = events[0].event_metadata
        assert meta["mode"] == "notify"
        assert meta["action_kind"] == "promote"
        assert meta["source_tier"] == "state"
        assert meta["parent_tier"] == "federal"


def test_finalize_at_federal_root_is_a_noop(clean_db: Engine) -> None:
    """A Decision on the federal root has no upstream — dispatch is a no-op."""
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        # Look up the federal root node.
        federal_root = (
            s.query(MatterNode)
            .filter_by(matter_id=ctx["matter_id"], tier="federal")
            .one()
        )
        d = create_decision(
            tenant_id="us-fed",
            workflow_id="cdbg",
            decision_type="formula_allocation",
            title="Federal-root decision",
            created_by=ctx["actor"],
            matter_id=ctx["matter_id"],
            matter_node_id=federal_root.id,
            fund_flow_path=[],
            session=s,
        )
        s.commit()
        decision_id = d.id

        s.execute(
            text(
                f"INSERT INTO {schema_prefix()}user_workflow_authority "
                "(id, user_id, workflow_id, level, granted_at, granted_by) "
                "VALUES (gen_random_uuid(), :uid, 'cdbg', 5, CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": ctx["actor"]},
        )
        s.commit()

        claim_decision(decision_id=decision_id, user_id=ctx["actor"], session=s)
        finalize_decision(
            decision_id=decision_id,
            user_id=ctx["actor"],
            selected_option="advance",
            rationale="Federal finalize",
            session=s,
        )
        s.commit()

    with Session(clean_db) as s:
        # No upstream events on a federal-root decision.
        events = (
            s.query(DecisionEvent)
            .filter_by(decision_id=decision_id)
            .filter(DecisionEvent.action.like("upstream_notify_%"))
            .all()
        )
        assert events == []
