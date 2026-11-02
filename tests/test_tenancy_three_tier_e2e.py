# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Three-tier end-to-end smoke (TENANCY-MODEL §10 step 6).

The seed creates:

- a federal user (jamie.kim) — sees the full chain
- a state user at Georgia (elena.ross) — sees Georgia's slice only
- a state user at Ohio (paul.tate) — sees Ohio's slice only
- a recipient user at Delta CDC (rita.alvarez) — sees the Delta leaf

Plus a CDBG matter whose originating federal Decision sits on the
federal root. This test inserts one Decision per (state, recipient)
node to give each tier something distinct to read, then exercises
the Inbox endpoint as each user and asserts the visibility rules.
"""

from __future__ import annotations

import uuid

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.models import MatterNode, Decision
from scripts.seed_dev import (
    _DELTA_RECIPIENT_ID,
    _GEORGIA_ORG_ID,
    _OHIO_ORG_ID,
    DEMO_PASSWORD,
    seed,
)


def _login_as(app: Flask, username: str) -> FlaskClient:
    """Return a fresh test client logged in as ``username``."""
    client = app.test_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_json()
    return client


def _numbers_in_cdbg_inbox(client: FlaskClient) -> set[str]:
    body = client.get(
        "/api/decisions?workflow_id=cdbg&density=all&limit=200"
    ).get_json()
    return {row["decision_number"] for row in body["items"]}


def _add_decision_for_node(
    session: Session,
    *,
    node_id: uuid.UUID,
    fund_flow_path: list[uuid.UUID],
    tenant_id: str,
    decision_number: str,
) -> Decision:
    """Synthetic Decision attached to a specific matter node + path."""
    node = session.get(MatterNode, node_id)
    assert node is not None
    d = Decision(
        tenant_id=tenant_id,
        decision_number=decision_number,
        workflow_id="cdbg",
        decision_type="formula_allocation",
        title=f"Test decision {decision_number}",
        priority="medium",
        severity="medium",
        status="open",
        matter_id=node.matter_id,
        matter_node_id=node_id,
        fund_flow_path=fund_flow_path,
    )
    session.add(d)
    session.flush()
    return d


def test_tier_visibility_end_to_end(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)

    # Drop in one Decision per non-federal node so each tier has
    # something distinct to read. The seeded originating federal
    # Decision already attaches to the federal root.
    with Session(clean_db) as s:
        # Look up the state nodes by participant_org_id.
        ga_node_id = s.execute(
            select(MatterNode.id).where(
                MatterNode.participant_org_id == _GEORGIA_ORG_ID,
                MatterNode.removed_at.is_(None),
            )
        ).scalar_one()
        oh_node_id = s.execute(
            select(MatterNode.id).where(
                MatterNode.participant_org_id == _OHIO_ORG_ID,
                MatterNode.removed_at.is_(None),
            )
        ).scalar_one()
        delta_node_id = s.execute(
            select(MatterNode.id).where(
                MatterNode.participant_org_id == _DELTA_RECIPIENT_ID,
                MatterNode.removed_at.is_(None),
            )
        ).scalar_one()

        _add_decision_for_node(
            s,
            node_id=ga_node_id,
            fund_flow_path=[_GEORGIA_ORG_ID],
            tenant_id="us-federal",
            decision_number="T-GA-001",
        )
        _add_decision_for_node(
            s,
            node_id=oh_node_id,
            fund_flow_path=[_OHIO_ORG_ID],
            tenant_id="us-federal",
            decision_number="T-OH-001",
        )
        _add_decision_for_node(
            s,
            node_id=delta_node_id,
            fund_flow_path=[_GEORGIA_ORG_ID, _DELTA_RECIPIENT_ID],
            tenant_id="us-federal",
            decision_number="T-DLT-001",
        )
        s.commit()

    # --- Federal: sees all three synthetic + originating.
    fed = _numbers_in_cdbg_inbox(_login_as(app, "jamie.kim"))
    assert "T-GA-001" in fed
    assert "T-OH-001" in fed
    assert "T-DLT-001" in fed

    # --- State (Georgia): sees its slice — GA + Delta (Delta's path
    # includes Georgia). Does NOT see Ohio.
    ga = _numbers_in_cdbg_inbox(_login_as(app, "elena.ross"))
    assert "T-GA-001" in ga
    assert "T-DLT-001" in ga
    assert "T-OH-001" not in ga

    # --- State (Ohio): sees Ohio only.
    oh = _numbers_in_cdbg_inbox(_login_as(app, "paul.tate"))
    assert "T-OH-001" in oh
    assert "T-GA-001" not in oh
    assert "T-DLT-001" not in oh

    # --- Recipient (Delta): sees ONLY its leaf. GA is in Delta's
    # ancestor path but recipient filter narrows to leaf-is-my-org.
    delta = _numbers_in_cdbg_inbox(_login_as(app, "rita.alvarez"))
    assert delta == {"T-DLT-001"}
