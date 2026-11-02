# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Promotion service tests — exercises the volume switch + ledger writes.

Maps to the acceptance criteria in WORKFLOW-MIGRATION.md:

  * A ``competitive_award`` case (every_case) writes a ledger row
    AND materialises a Decision.
  * An ``on_trigger`` archetype (eligibility_determination, etc.)
    writes a ledger row but does NOT materialise a Decision when no
    trigger is supplied.
  * The same on_trigger archetype DOES materialise a Decision when
    a recognised promotion_trigger fires.
  * The promotion service resolves ``gate: conditional`` to
    ``authority`` before the Decision payload leaves the service, so
    the lifecycle never sees the conditional enum value.
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


def _make_stub_decision_callback(tenant_id: str) -> tuple[list[dict[str, Any]], Any]:
    """Build a create-decision callback that inserts a minimal real Decision.

    Real callers (the decision manager) build a fully fleshed Decision.
    For unit tests we only need the FK target to exist so the ledger
    update succeeds; the rest of the lifecycle isn't exercised here.
    """
    captured: list[dict[str, Any]] = []

    def callback(payload: dict[str, Any], session: Any) -> uuid.UUID:
        captured.append(payload)
        decision_id = uuid.uuid4()
        session.execute(
            text(
                f"INSERT INTO {schema_prefix()}decisions "
                "(id, tenant_id, decision_number, workflow_id, decision_type, "
                " title, priority, severity, status) "
                "VALUES (:id, :tid, :num, :wf, :dt, :title, "
                "        'medium', 'medium', 'open')"
            ),
            {
                "id": decision_id,
                "tid": tenant_id,
                "num": f"PROM-{decision_id.hex[:8]}",
                "wf": payload["program_id"],
                "dt": payload["archetype_id"],
                "title": f"Promoted from ledger {payload['ledger_id']}",
            },
        )
        session.flush()
        return decision_id

    return captured, callback


# Use the canonical engine from the committed corpus — these tests run
# against the real dp/config/ archetypes + programs.
@pytest.fixture(scope="module", autouse=True)
def _engine() -> Iterator[None]:
    reset_engine()
    init_engine()
    yield
    reset_engine()


@pytest.fixture()
def clean_ledger(db_engine: Engine) -> Engine:
    """Empty the ledger before each test so assertions are deterministic."""
    with db_engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {schema_prefix()}determination_ledger"))
        conn.commit()
    return db_engine


def _seed_tenant_user(db_engine: Engine) -> tuple[str, uuid.UUID]:
    """Insert a minimal tenant + user so the promotion service has FK targets."""
    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"prom-test-{suffix}"
    user_id = uuid.uuid4()
    with db_engine.connect() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type) "
                "VALUES (:tid, 'Promotion Test CU', 'CREDIT_UNION')"
            ),
            {"tid": tenant_id},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, status) "
                "VALUES (:uid, :tid, :uname, :email, 'x', 'Prom', 'member', 'active')"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "uname": f"prom-{suffix}",
                "email": f"prom-{suffix}@x.com",
            },
        )
        conn.commit()
    return tenant_id, user_id


# ---------------------------------------------------------------------------
# every_case: NIH-R01 (competitive_award)
# ---------------------------------------------------------------------------


def test_every_case_writes_ledger_and_decides(clean_ledger: Engine) -> None:
    """A competitive_award determination always promotes."""
    tenant_id, user_id = _seed_tenant_user(clean_ledger)
    captured, fake_create_decision = _make_stub_decision_callback(tenant_id)

    result = record_determination(
        tenant_id=tenant_id,
        program_id="nih-r01",
        inputs={"applicant_id": str(user_id), "application_id": "R01-2026-001"},
        basis_result={"scores": {"significance": 2.0}, "rank": 14},
        actor={"kind": "system", "id": "nih-merit-review"},
        outcome=None,
        rule_version="nih-cycle-2026.06",
        create_decision=fake_create_decision,
    )

    assert result.promoted
    assert result.outcome is PromotionOutcome.PROMOTED_EVERY_CASE
    assert result.decision_id is not None
    assert captured, "create_decision callback should fire for every_case"

    # Ledger row exists and is flagged promoted.
    with session_scope() as s:
        row = s.execute(
            text(
                "SELECT promoted, promotion_trigger, archetype_id, program_id "
                f"FROM {schema_prefix()}determination_ledger WHERE id = :id"
            ),
            {"id": result.ledger_id},
        ).one()
        assert row.promoted is True
        assert row.promotion_trigger is None  # every_case has no trigger
        assert row.archetype_id == "competitive_award"
        assert row.program_id == "nih-r01"


# ---------------------------------------------------------------------------
# on_trigger: SNAP (eligibility_determination) — no trigger -> ledger only
# ---------------------------------------------------------------------------


def test_on_trigger_no_trigger_writes_ledger_only(clean_ledger: Engine) -> None:
    """SNAP routine determination: ledger row but NO Decision."""
    tenant_id, user_id = _seed_tenant_user(clean_ledger)

    captured: list[dict[str, Any]] = []

    def fake_create_decision(payload: dict[str, Any], _session: Any) -> uuid.UUID:
        captured.append(payload)
        return uuid.uuid4()

    result = record_determination(
        tenant_id=tenant_id,
        program_id="snap",
        inputs={"claimant_id": str(user_id), "household_size": 3},
        basis_result={"eligible": True, "benefit_amount": 540},
        actor={"kind": "system", "id": "snap-eligibility-engine"},
        outcome="eligible",
        rule_version="2026.06",
        promotion_trigger=None,
        create_decision=fake_create_decision,
    )

    assert not result.promoted
    assert result.outcome is PromotionOutcome.LEDGER_ONLY
    assert result.decision_id is None
    assert not captured, "create_decision must NOT fire for routine on_trigger"

    # Ledger row exists and is flagged NOT promoted.
    with session_scope() as s:
        row = s.execute(
            text(
                "SELECT promoted, promotion_trigger, outcome "
                f"FROM {schema_prefix()}determination_ledger WHERE id = :id"
            ),
            {"id": result.ledger_id},
        ).one()
        assert row.promoted is False
        assert row.promotion_trigger is None
        assert row.outcome == "eligible"


# ---------------------------------------------------------------------------
# on_trigger: SNAP with a recognised trigger -> Decision is created
# ---------------------------------------------------------------------------


def test_on_trigger_recognised_trigger_promotes(clean_ledger: Engine) -> None:
    """SNAP determination with an override trigger spawns a Decision."""
    tenant_id, user_id = _seed_tenant_user(clean_ledger)
    captured, fake_create_decision = _make_stub_decision_callback(tenant_id)

    result = record_determination(
        tenant_id=tenant_id,
        program_id="snap",
        inputs={"claimant_id": str(user_id), "household_size": 3},
        basis_result={"eligible": False, "rule": "gross_income_test"},
        actor={"kind": "user", "id": str(user_id)},
        outcome="ineligible",
        promotion_trigger="override",  # caseworker overrode the auto-result
        create_decision=fake_create_decision,
    )

    assert result.promoted
    assert result.outcome is PromotionOutcome.PROMOTED_ON_TRIGGER
    assert result.decision_id is not None
    assert captured, "create_decision should fire for on_trigger + recognised trigger"

    payload = captured[0]
    assert payload["archetype_id"] == "eligibility_determination"
    assert payload["promotion_trigger"] == "override"

    # All stages handed downstream resolve gate to none|authority only —
    # the lifecycle should never see "conditional".
    gates = {stage["gate"] for stage in payload["stages"]}
    assert "conditional" not in gates, (
        "promotion service must resolve gate: conditional before payload exits"
    )
    # The eligibility_determination ``determination`` stage was conditional;
    # after promotion it must be authority.
    determination_stage = next(s for s in payload["stages"] if s["id"] == "determination")
    assert determination_stage["gate"] == "authority"


# ---------------------------------------------------------------------------
# Unrecognised trigger -> ValueError
# ---------------------------------------------------------------------------


def test_unknown_trigger_raises(clean_ledger: Engine) -> None:
    tenant_id, user_id = _seed_tenant_user(clean_ledger)

    with pytest.raises(ValueError, match="promotion_trigger"):
        record_determination(
            tenant_id=tenant_id,
            program_id="snap",
            inputs={"claimant_id": str(user_id)},
            basis_result={"eligible": True},
            actor={"kind": "system", "id": "snap"},
            promotion_trigger="not_a_real_trigger",
        )


# ---------------------------------------------------------------------------
# Unknown program -> KeyError from engine
# ---------------------------------------------------------------------------


def test_unknown_program_raises(clean_ledger: Engine) -> None:
    tenant_id, _ = _seed_tenant_user(clean_ledger)
    with pytest.raises(KeyError):
        record_determination(
            tenant_id=tenant_id,
            program_id="does-not-exist",
            inputs={},
            basis_result={},
            actor={"kind": "system", "id": "x"},
        )


# ---------------------------------------------------------------------------
# Ledger row uses the program's vocabulary for stage labels (when promoted)
# ---------------------------------------------------------------------------


def test_promoted_payload_uses_program_vocabulary(clean_ledger: Engine) -> None:
    """The promotion service maps program.vocabulary into stage labels."""
    tenant_id, user_id = _seed_tenant_user(clean_ledger)
    captured, fake_create_decision = _make_stub_decision_callback(tenant_id)

    record_determination(
        tenant_id=tenant_id,
        program_id="nih-r01",
        inputs={"applicant_id": str(user_id)},
        basis_result={"scores": {"approach": 2.1}},
        actor={"kind": "system", "id": "nih"},
        create_decision=fake_create_decision,
    )

    payload = captured[0]
    labels = {s["id"]: s["label"] for s in payload["stages"]}
    # nih-r01.program.yaml maps merit_review -> study_section_review
    assert labels.get("merit_review") == "study_section_review"


# ---------------------------------------------------------------------------
# adverse_action child Decision — appeal pattern via parent_ledger_id
# ---------------------------------------------------------------------------


def test_child_determination_links_to_parent_ledger(clean_ledger: Engine) -> None:
    """Appeals / re-decisions run as a fresh archetype against a new ledger
    row whose parent_ledger_id points at the originating determination.
    The parent stays closed; the child becomes its own governed Decision."""
    tenant_id, user_id = _seed_tenant_user(clean_ledger)
    captured, fake_create_decision = _make_stub_decision_callback(tenant_id)

    # Originating debarment — grant-debarment binds adverse_action.
    parent_result = record_determination(
        tenant_id=tenant_id,
        program_id="grant-debarment",
        inputs={"respondent_id": str(user_id), "basis": "conviction"},
        basis_result={"recommendation": "debar", "duration_months": 36},
        actor={"kind": "user", "id": str(user_id)},
        outcome="sustained",
        create_decision=fake_create_decision,
    )
    assert parent_result.promoted
    parent_ledger_id = parent_result.ledger_id

    # Appeal: fresh adverse_action run with parent_ledger_id pointing back.
    appeal_result = record_determination(
        tenant_id=tenant_id,
        program_id="grant-debarment",
        inputs={"respondent_id": str(user_id), "filing": "appeal"},
        basis_result={"recommendation": "modify", "new_duration_months": 12},
        actor={"kind": "user", "id": str(user_id)},
        outcome="modified",
        parent_ledger_id=parent_ledger_id,
        create_decision=fake_create_decision,
    )

    assert appeal_result.promoted
    assert appeal_result.decision_id is not None
    assert appeal_result.decision_id != parent_result.decision_id, (
        "appeal must be a separate Decision; the lifecycle never re-enters the originating Decision"
    )

    # Both ledger rows exist; the child carries the parent link.
    with session_scope() as s:
        parent_row = s.execute(
            text(f"SELECT id, parent_ledger_id FROM {schema_prefix()}determination_ledger WHERE id = :id"),
            {"id": parent_ledger_id},
        ).one()
        child_row = s.execute(
            text(f"SELECT id, parent_ledger_id FROM {schema_prefix()}determination_ledger WHERE id = :id"),
            {"id": appeal_result.ledger_id},
        ).one()
        assert parent_row.parent_ledger_id is None
        assert child_row.parent_ledger_id == parent_ledger_id
