# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Regression test for P06 — federalized seed lifecycle.

The federal seed used to raw-INSERT Decision rows, bypassing the
manager. That left promoted Decisions with no decision_events trail —
``R01-2026-002`` showed ``outcome=declined`` in the ledger but the
Decision Detail looked unwalked. P06 routes the seed through
``create_decision → claim_decision → finalize_decision → record_outcome``
via ``make_federal_decision_factory``.

This test exercises the real factory (the same one the seed uses) and
asserts that a promoted federal Decision with an outcome carries the
full canonical event trail.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from reasonbook.db import session_scope
from reasonbook.db import schema_prefix
from reasonbook.promotion import PromotionOutcome, record_determination
from reasonbook.semantic.engine import init_engine, reset_engine
from scripts.seed_dev import make_federal_decision_factory


@pytest.fixture(scope="module", autouse=True)
def _engine() -> Iterator[None]:
    reset_engine()
    init_engine()
    yield
    reset_engine()


@pytest.fixture()
def clean_ledger(db_engine: Engine) -> Engine:
    with db_engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {schema_prefix()}determination_ledger"))
        conn.commit()
    return db_engine


def _seed_tenant_user(db_engine: Engine) -> tuple[str, uuid.UUID]:
    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"p06-{suffix}"
    user_id = uuid.uuid4()
    with db_engine.connect() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type) "
                "VALUES (:tid, 'P06 test', 'CREDIT_UNION')"
            ),
            {"tid": tenant_id},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, status) "
                "VALUES (:uid, :tid, :uname, :email, 'x', 'P06', 'member', 'active')"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "uname": f"p06-{suffix}",
                "email": f"p06-{suffix}@x.com",
            },
        )
        conn.commit()
    return tenant_id, user_id


def test_federalized_seed_writes_full_lifecycle_trail(clean_ledger: Engine) -> None:
    tenant_id, user_id = _seed_tenant_user(clean_ledger)

    # The factory only needs ``actor.id``; a minimal stand-in keeps the
    # test independent of the User ORM's required columns.
    actor: Any = type("Actor", (), {"id": user_id})()
    callback = make_federal_decision_factory(tenant_id=tenant_id, actor=actor)

    result = record_determination(
        tenant_id=tenant_id,
        program_id="nih-r01",
        inputs={"case_id": "R01-2026-002", "applicant_id": str(user_id)},
        basis_result={"impact_score": 32, "percentile": 28},
        actor={"kind": "user", "id": str(user_id), "role": "program_officer"},
        outcome="declined",
        rule_version="nih-fy2026-cycle-2",
        create_decision=callback,
    )

    assert result.promoted
    assert result.outcome is PromotionOutcome.PROMOTED_EVERY_CASE
    assert result.decision_id is not None

    with session_scope() as s:
        d = s.execute(
            text(
                "SELECT status, selected_option, outcome_text, signal_source "
                f"FROM {schema_prefix()}decisions WHERE id = :id"
            ),
            {"id": result.decision_id},
        ).one()
        assert d.status == "closed"
        assert d.selected_option == "declined"
        assert d.outcome_text == "Ledger outcome: declined"
        assert d.signal_source == "federal_seed_dev"

        events = s.execute(
            text(
                f"SELECT action, old_status, new_status FROM {schema_prefix()}decision_events "
                "WHERE decision_id = :id ORDER BY created_at"
            ),
            {"id": result.decision_id},
        ).all()
        actions = [e.action for e in events]
        assert actions == [
            "created",
            "assigned",
            "claimed",
            "finalized",
            "outcome_recorded",
        ]


def test_federalized_seed_stops_at_in_progress_when_outcome_none(
    clean_ledger: Engine,
) -> None:
    """outcome=None is the in-review case (R01-2026-003 in the corpus).

    The factory must NOT fake a finalize — the Decision stops at
    ``in_progress`` with no selected_option / outcome_text, and only
    the first three events are written.
    """
    tenant_id, user_id = _seed_tenant_user(clean_ledger)
    actor: Any = type("Actor", (), {"id": user_id})()
    callback = make_federal_decision_factory(tenant_id=tenant_id, actor=actor)

    result = record_determination(
        tenant_id=tenant_id,
        program_id="nih-r01",
        inputs={"case_id": "R01-2026-003", "applicant_id": str(user_id)},
        basis_result={"impact_score": 22, "percentile": 17},
        actor={"kind": "user", "id": str(user_id), "role": "program_officer"},
        outcome=None,
        create_decision=callback,
    )

    assert result.decision_id is not None
    with session_scope() as s:
        d = s.execute(
            text(
                "SELECT status, selected_option, outcome_text "
                f"FROM {schema_prefix()}decisions WHERE id = :id"
            ),
            {"id": result.decision_id},
        ).one()
        assert d.status == "in_progress"
        assert d.selected_option is None
        assert d.outcome_text is None

        actions = [
            row.action
            for row in s.execute(
                text(
                    f"SELECT action FROM {schema_prefix()}decision_events "
                    "WHERE decision_id = :id ORDER BY created_at"
                ),
                {"id": result.decision_id},
            ).all()
        ]
        assert actions == ["created", "assigned", "claimed"]
