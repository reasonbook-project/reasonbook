# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Phase 12 — apex workflow tests.

Covers evidence linkage (link, supersede, diversity), board cycle
lifecycle (create, list, auto-transition), authority resolution
(executive vs board), and the apex API surface.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from reasonbook.app import create_app
from reasonbook.db import schema_prefix
from reasonbook.db import session_scope
from reasonbook.decisions.manager import create_decision
from reasonbook.models import Decision, OversightCycle, OversightEvidenceLink, User
from reasonbook.oversight.authority import (
    can_record_committee_action,
    resolve_oversight_capabilities,
)
from reasonbook.oversight.cycles import (
    CycleError,
    auto_transition_due,
    create_cycle,
    list_cycles,
)
from reasonbook.oversight.evidence import (
    EvidenceError,
    evidence_diversity,
    link_evidence,
    list_active_evidence,
    supersede_evidence,
)
from scripts.seed_dev import DEMO_PASSWORD


@pytest.fixture()
def app(seeded: Engine) -> Iterator[Flask]:  # noqa: ARG001
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def _login(client: FlaskClient, username: str = "sarah.mitchell") -> None:
    resp = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()


def _user_id(username: str) -> uuid.UUID:
    with session_scope() as s:
        return s.query(User).filter(User.username == username).one().id


# ---------------------------------------------------------------------------
# Authority resolution
# ---------------------------------------------------------------------------


def test_sarah_resolves_as_ceo_with_all_domains(seeded: Engine) -> None:  # noqa: ARG001
    user_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        caps = resolve_oversight_capabilities(s, user_id=user_id)
    assert caps is not None
    assert caps.oversight_role == "agency_head"
    assert caps.is_executive is True
    assert caps.is_committee is False
    assert "appropriations_and_obligations" in caps.domains_owned
    assert can_record_committee_action(caps) is False


def test_jamie_has_no_apex_capabilities(seeded: Engine) -> None:  # noqa: ARG001
    user_id = _user_id("jamie.kim")
    with session_scope() as s:
        caps = resolve_oversight_capabilities(s, user_id=user_id)
    assert caps is None


# ---------------------------------------------------------------------------
# Board cycles
# ---------------------------------------------------------------------------


def test_create_cycle_in_planned_state(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        cycle = create_cycle(
            s,
            tenant_id="us-federal",
            name="Q3 2026 Special",
            cycle_type="special",
            cycle_start=date(2026, 7, 1),
            cycle_end=date(2026, 9, 30),
            created_by=sarah_id,
        )
        assert cycle.status == "planned"
        assert cycle.id is not None


def test_create_cycle_rejects_inverted_dates(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s, pytest.raises(CycleError):
        create_cycle(
            s,
            tenant_id="us-federal",
            name="Bad cycle",
            cycle_type="special",
            cycle_start=date(2026, 9, 30),
            cycle_end=date(2026, 7, 1),
            created_by=sarah_id,
        )


def test_auto_transition_moves_due_cycles(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    today = date.today()
    with session_scope() as s:
        # Past planned cycle.
        past_planned = create_cycle(
            s,
            tenant_id="us-federal",
            name="Past planned",
            cycle_type="special",
            cycle_start=today - timedelta(days=10),
            cycle_end=today + timedelta(days=20),
            created_by=sarah_id,
        )
        # Past active cycle (already ended).
        past_active = create_cycle(
            s,
            tenant_id="us-federal",
            name="Past active",
            cycle_type="special",
            cycle_start=today - timedelta(days=60),
            cycle_end=today - timedelta(days=5),
            created_by=sarah_id,
        )
        past_active.status = "active"
        s.flush()

        moved = auto_transition_due(s, today=today)
        assert moved >= 2
        s.refresh(past_planned)
        s.refresh(past_active)
        assert past_planned.status == "active"
        assert past_active.status == "concluded"


def test_list_cycles_filters_by_status(seeded: Engine) -> None:  # noqa: ARG001
    with session_scope() as s:
        active = list_cycles(s, tenant_id="us-federal", status="active")
        concluded = list_cycles(s, tenant_id="us-federal", status="concluded")
    # Seed wrote one of each.
    assert len(active) >= 1
    assert len(concluded) >= 1


# ---------------------------------------------------------------------------
# Evidence linkage
# ---------------------------------------------------------------------------


def _make_apex_decision(s: Session, *, owner_id: uuid.UUID) -> Decision:
    return create_decision(
        tenant_id="us-federal",
        workflow_id="10-oversight",
        decision_type="fraud_tolerance_limit_change",
        title="Test apex decision",
        priority="high",
        owner_id=owner_id,
        created_by=owner_id,
        session=s,
    )


def _make_op_decision(s: Session, *, owner_id: uuid.UUID, workflow: str) -> Decision:
    return create_decision(
        tenant_id="us-federal",
        workflow_id=workflow,
        decision_type="bsa_aml_alert" if workflow == "01-regulatory-compliance" else "exam_preparation",
        title=f"Op decision {workflow}",
        priority="high",
        owner_id=owner_id,
        created_by=owner_id,
        session=s,
    )


def test_link_evidence_happy_path(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        op = _make_op_decision(s, owner_id=sarah_id, workflow="01-regulatory-compliance")
        link = link_evidence(
            s,
            oversight_decision_id=apex.id,
            operational_decision_id=op.id,
            evidence_role="primary_evidence",
            linked_by=sarah_id,
            rationale="primary signal driving this revision",
        )
        assert link.id is not None
        assert link.superseded_at is None


def test_link_evidence_rejects_apex_to_apex(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex_a = _make_apex_decision(s, owner_id=sarah_id)
        apex_b = _make_apex_decision(s, owner_id=sarah_id)
        with pytest.raises(EvidenceError):
            link_evidence(
                s,
                oversight_decision_id=apex_a.id,
                operational_decision_id=apex_b.id,
                evidence_role="primary_evidence",
                linked_by=sarah_id,
            )


def test_supersede_preserves_audit(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        op_a = _make_op_decision(s, owner_id=sarah_id, workflow="01-regulatory-compliance")
        op_b = _make_op_decision(s, owner_id=sarah_id, workflow="01-regulatory-compliance")
        first = link_evidence(
            s,
            oversight_decision_id=apex.id,
            operational_decision_id=op_a.id,
            evidence_role="primary_evidence",
            linked_by=sarah_id,
        )
        second = link_evidence(
            s,
            oversight_decision_id=apex.id,
            operational_decision_id=op_b.id,
            evidence_role="primary_evidence",
            linked_by=sarah_id,
        )
        supersede_evidence(s, link_id=first.id, replacement=second)

        active = list_active_evidence(s, oversight_decision_id=apex.id)
        ids = [e.id for e in active]
        assert second.id in ids
        assert first.id not in ids

        s.refresh(first)
        assert first.superseded_at is not None
        assert first.superseded_by_link_id == second.id


def test_evidence_diversity_counts_active(seeded: Engine) -> None:  # noqa: ARG001
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        # Two operational decisions in different workflows so
        # distinct_workflows == 2. BSA was retired; use oversight and
        # regulatory-compliance as the two distinct workflow ids.
        op_reg = _make_op_decision(
            s, owner_id=sarah_id, workflow="01-regulatory-compliance"
        )
        # Second workflow id: a federal program id used as an
        # operational workflow slot (see program_id → workflow_id
        # aliasing in the federal seed). Any non-oversight string
        # would work; nih-r01 is real seed data.
        op_reg_2 = _make_op_decision(s, owner_id=sarah_id, workflow="nih-r01")
        link_evidence(
            s,
            oversight_decision_id=apex.id,
            operational_decision_id=op_reg.id,
            evidence_role="primary_evidence",
            linked_by=sarah_id,
        )
        link_evidence(
            s,
            oversight_decision_id=apex.id,
            operational_decision_id=op_reg_2.id,
            evidence_role="supporting_evidence",
            linked_by=sarah_id,
        )
        count, distinct_workflows = evidence_diversity(s, oversight_decision_id=apex.id)
        assert count == 2
        assert distinct_workflows == 2


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def test_apex_decisions_endpoint_lists_seeded(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.get("/api/oversight/decisions")
    assert resp.status_code == 200
    body = resp.get_json()
    titles = [item["title"] for item in body["items"]]
    assert any("oig" in t.lower() or "obligation" in t.lower() for t in titles)


def test_apex_decisions_403_when_oversight_disabled(client: FlaskClient) -> None:
    # Oversight is gated by tenants.has_oversight, not by an entitlement
    # row. Flip the flag off, log in fresh so the JWT reflects the new
    # state, and confirm the endpoint rejects.
    from sqlalchemy import text as sql_text

    from reasonbook.db import session_scope

    with session_scope() as s:
        s.execute(
            sql_text(
                f"UPDATE {schema_prefix()}tenants SET has_oversight = FALSE "
                "WHERE tenant_id='us-federal'"
            )
        )
    _login(client, "jamie.kim")
    resp = client.get("/api/oversight/decisions")
    assert resp.status_code == 403


def test_apex_cycles_endpoint_includes_decision_count(client: FlaskClient) -> None:
    """The cycles list view shows a per-cycle apex decision count so the
    frontend dossier surface can render rows without a second round-trip."""
    _login(client, "sarah.mitchell")
    resp = client.get("/api/oversight/cycles")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert items, "seed should have cycles"
    for c in items:
        assert "decision_count" in c
        assert isinstance(c["decision_count"], int)
        assert c["decision_count"] >= 0
    # At least one seeded cycle has tied apex decisions; sanity-check
    # the join actually runs rather than always returning zero.
    assert any(c["decision_count"] > 0 for c in items)


def test_apex_cycles_endpoint_403_when_oversight_disabled(client: FlaskClient) -> None:
    """Agencies without oversight enabled get 403 from the cycles
    endpoint so the frontend's auth-store gate isn't the only
    enforcement."""
    from sqlalchemy import text

    from reasonbook.db import session_scope as scope

    with scope() as s:
        s.execute(
            text(
                f"UPDATE {schema_prefix()}tenants SET has_oversight = FALSE "
                "WHERE tenant_id='us-federal'"
            )
        )
    _login(client, "jamie.kim")
    resp = client.get("/api/oversight/cycles")
    assert resp.status_code == 403


def test_create_apex_cycle(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.post(
        "/api/oversight/cycles",
        json={
            "name": "Q3 2026 Board Cycle",
            "cycle_type": "quarterly",
            "cycle_start": "2026-07-01",
            "cycle_end": "2026-09-30",
        },
    )
    assert resp.status_code == 201
    assert resp.get_json()["status"] == "planned"


def test_create_evidence_via_api(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        op = _make_op_decision(s, owner_id=sarah_id, workflow="01-regulatory-compliance")
        apex_id = apex.id
        op_id = op.id

    resp = client.post(
        f"/api/oversight/decisions/{apex_id}/evidence",
        json={
            "operational_decision_id": str(op_id),
            "evidence_role": "primary_evidence",
            "rationale": "central data point",
        },
    )
    assert resp.status_code == 201
    assert resp.get_json()["evidence_role"] == "primary_evidence"


def test_committee_action_requires_capability(client: FlaskClient) -> None:
    """Sarah is CEO — executive, not board. Cannot record board action."""
    _login(client, "sarah.mitchell")
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex_id = apex.id

    resp = client.post(
        f"/api/oversight/decisions/{apex_id}/committee-action",
        json={"action": "endorsed_by_committee"},
    )
    assert resp.status_code == 403


def test_audit_committee_chair_can_record_ratification(client: FlaskClient) -> None:
    """Walter Knox is Board Chair with can_record_committee_action=true."""
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex_id = apex.id

    _login(client, "linda.peters")
    resp = client.post(
        f"/api/oversight/decisions/{apex_id}/committee-action",
        json={"action": "endorsed_by_committee", "note": "Reviewed Q2 evidence."},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["action"] == "endorsed_by_committee"

    # Event surfaces in the default audit view.
    events = client.get(f"/api/decisions/{apex_id}/events").get_json()["items"]
    ratifications = [e for e in events if e["action"] == "endorsed_by_committee"]
    assert len(ratifications) == 1
    assert ratifications[0]["comment"] == "Reviewed Q2 evidence."


def test_apex_decided_decision_marked_awaiting_board(client: FlaskClient) -> None:
    """An apex decision in `decided` without a ratification event surfaces
    with awaiting_committee_endorsement=True. Walter recording ratification
    flips the flag back to False."""
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex.status = "decided"
        apex.decided_at = datetime.now(UTC)
        apex.selected_option = "approve"
        apex.rationale = "Stub rationale for test."
        s.flush()
        apex_id = apex.id

    _login(client, "sarah.mitchell")
    body = client.get(f"/api/decisions/{apex_id}").get_json()
    assert body["status"] == "decided"
    assert body["awaiting_committee_endorsement"] is True

    _login(client, "linda.peters")
    resp = client.post(
        f"/api/oversight/decisions/{apex_id}/committee-action",
        json={"action": "endorsed_by_committee"},
    )
    assert resp.status_code == 200

    body = client.get(f"/api/decisions/{apex_id}").get_json()
    assert body["awaiting_committee_endorsement"] is False


def test_awaiting_board_stage_filter(client: FlaskClient) -> None:
    """GET /decisions?stage=awaiting_committee returns only apex `decided`
    decisions without ratification events."""
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex.status = "decided"
        apex.decided_at = datetime.now(UTC)
        s.flush()
        apex_id = apex.id

    _login(client, "sarah.mitchell")
    body = client.get("/api/decisions?stage=awaiting_committee").get_json()
    items = body["items"]
    matched = [i for i in items if i["id"] == str(apex_id)]
    assert len(matched) == 1
    assert matched[0]["awaiting_committee_endorsement"] is True


def test_actions_stage_excludes_apex_awaiting_board(client: FlaskClient) -> None:
    """The Actions stage tile excludes apex decided-awaiting-board so the
    count reads honestly (operational decisions only)."""
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex.status = "decided"
        apex.decided_at = datetime.now(UTC)
        s.flush()
        apex_id = apex.id

    _login(client, "sarah.mitchell")
    body = client.get("/api/decisions?stage=actions").get_json()
    items = body["items"]
    assert not any(i["id"] == str(apex_id) for i in items)


def test_committee_action_rejects_unknown_action(client: FlaskClient) -> None:
    sarah_id = _user_id("sarah.mitchell")
    with session_scope() as s:
        apex = _make_apex_decision(s, owner_id=sarah_id)
        apex_id = apex.id

    _login(client, "linda.peters")
    resp = client.post(
        f"/api/oversight/decisions/{apex_id}/committee-action",
        json={"action": "approve"},  # not in BOARD_ACTIONS
    )
    assert resp.status_code == 400


def test_dossier_returns_pdf(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    cycles = client.get("/api/oversight/cycles?status=concluded").get_json()["items"]
    assert cycles, "seed should have a concluded cycle"
    cycle_id = cycles[0]["id"]
    resp = client.get(f"/api/oversight/cycles/{cycle_id}/dossier")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.data[:4] == b"%PDF"


# Unused imports kept for future test scaffolding.
_ = (datetime, UTC, OversightEvidenceLink, OversightCycle)
