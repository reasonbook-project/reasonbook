# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Row-level enforcement via apply_tier_scope (TENANCY-MODEL.md §3).

Federal sees the full chain; state sees its slice; recipient sees only
its own leaf. Default-deny otherwise.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.decisions.scope import apply_tier_scope
from reasonbook.db import schema_prefix
from reasonbook.models import Decision


def _seed_decision(
    session: Session,
    *,
    tenant_id: str,
    fund_flow_path: list[uuid.UUID],
    decision_number: str,
) -> Decision:
    d = Decision(
        tenant_id=tenant_id,
        decision_number=decision_number,
        workflow_id="01-regulatory-compliance",
        decision_type="generic",
        title=f"Decision {decision_number}",
        priority="medium",
        severity="medium",
        status="open",
        fund_flow_path=fund_flow_path,
    )
    session.add(d)
    session.flush()
    return d


def _bootstrap(clean_db: Engine) -> dict[str, uuid.UUID | str]:
    """Seed a federal-root → state(GA) → recipient(Delta) → leaf chain."""
    state_ga = uuid.uuid4()
    recipient_delta = uuid.uuid4()
    other_state = uuid.uuid4()

    with clean_db.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) VALUES ('us-fed', 'Federal')")
        )
        for org_id, name, kind in (
            (state_ga, "Georgia", "state"),
            (recipient_delta, "Delta CDC", "recipient"),
            (other_state, "Ohio", "state"),
        ):
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                    "VALUES (:id, :kind, :name)"
                ),
                {"id": org_id, "kind": kind, "name": name},
            )

    return {
        "tenant_id": "us-fed",
        "state_ga": state_ga,
        "recipient_delta": recipient_delta,
        "other_state": other_state,
    }


def test_federal_tier_sees_everything(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        _seed_decision(s, tenant_id=ctx["tenant_id"], fund_flow_path=[], decision_number="DEC-1")
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"]],
            decision_number="DEC-2",
        )
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"], ctx["recipient_delta"]],
            decision_number="DEC-3",
        )
        s.commit()

        q = apply_tier_scope(s.query(Decision), tier="federal", participant_org_id=None)
        assert q.count() == 3


def test_state_sees_only_decisions_in_its_state_chain(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        _seed_decision(s, tenant_id=ctx["tenant_id"], fund_flow_path=[], decision_number="FED-ROOT")
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"]],
            decision_number="GA-STATE",
        )
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"], ctx["recipient_delta"]],
            decision_number="GA-RECIP",
        )
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["other_state"]],
            decision_number="OH-STATE",
        )
        s.commit()

        q = apply_tier_scope(
            s.query(Decision),
            tier="state",
            participant_org_id=ctx["state_ga"],
        )
        numbers = sorted(d.decision_number for d in q.all())
        assert numbers == ["GA-RECIP", "GA-STATE"]


def test_recipient_sees_only_its_leaf_slice(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        _seed_decision(s, tenant_id=ctx["tenant_id"], fund_flow_path=[], decision_number="FED")
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"]],
            decision_number="STATE",
        )
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"], ctx["recipient_delta"]],
            decision_number="LEAF",
        )
        # A decision where Delta appears in the path but ISN'T the leaf
        # (synthetic — sub-recipient hanging off Delta). Recipient at
        # Delta should NOT see this row; it's not their slice.
        sub_recip = uuid.uuid4()
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                    "VALUES (:id, 'recipient', 'SubX')"
                ),
                {"id": sub_recip},
            )
        _seed_decision(
            s,
            tenant_id=ctx["tenant_id"],
            fund_flow_path=[ctx["state_ga"], ctx["recipient_delta"], sub_recip],
            decision_number="SUB-LEAF",
        )
        s.commit()

        q = apply_tier_scope(
            s.query(Decision),
            tier="recipient",
            participant_org_id=ctx["recipient_delta"],
        )
        numbers = sorted(d.decision_number for d in q.all())
        assert numbers == ["LEAF"]


def test_state_tier_with_null_org_defaults_deny(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        _seed_decision(s, tenant_id=ctx["tenant_id"], fund_flow_path=[], decision_number="X")
        s.commit()

        q = apply_tier_scope(s.query(Decision), tier="state", participant_org_id=None)
        assert q.count() == 0


def test_unknown_tier_defaults_deny(clean_db: Engine) -> None:
    ctx = _bootstrap(clean_db)
    with Session(clean_db) as s:
        _seed_decision(s, tenant_id=ctx["tenant_id"], fund_flow_path=[], decision_number="X")
        s.commit()

        q = apply_tier_scope(
            s.query(Decision),
            tier="contractor",  # not a valid v1 tier
            participant_org_id=uuid.uuid4(),
        )
        assert q.count() == 0
