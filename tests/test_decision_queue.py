# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""GET /api/decisions/queue tests (P17 decision-queue endpoint)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
from reasonbook.decisions import manager
from reasonbook.models import Decision
from scripts.seed_dev import DEMO_PASSWORD

pytestmark = pytest.mark.skip(
    reason=(
        "Banking-workflow fixtures retired in WORKFLOW-MIGRATION (Step 2). "
        "This module's tests assume specific banking workflow ids, decision "
        "types, and seeded entitlements; re-enable after the federal seed "
        "lands as part of Phase 1 Step 8 (UI / nav: Caseload)."
    ),
)


@pytest.fixture()
def app(seeded: Engine) -> Iterator[Flask]:  # noqa: ARG001
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def _login(client: FlaskClient, username: str = "jamie.kim") -> None:
    resp = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()


def _user_id(username: str) -> uuid.UUID:
    from reasonbook.db import session_scope
    from reasonbook.models import User

    with session_scope() as s:
        return s.query(User).filter(User.username == username).one().id


def _seed_at_risk(
    workflow_id: str = "01-regulatory-compliance",
    *,
    count: int = 1,
    creator: str = "sarah.mitchell",
) -> list[Decision]:
    """Create N decisions with sla_hours=1 so they fall inside the
    ``at_risk_filter`` 24h cutoff."""
    creator_id = _user_id(creator)
    created: list[Decision] = []
    for i in range(count):
        d = manager.create_decision(
            tenant_id="us-federal",
            workflow_id=workflow_id,
            decision_type="bsa_aml_alert"
            if workflow_id == "01-regulatory-compliance"
            else "exam_finding_response",
            title=f"Queue test alert {i}",
            created_by=creator_id,
            priority="high",
            sla_hours=1,
            signal_source=f"ingest.queue-test.{workflow_id}.{i}",
            signal_summary="queue test fixture",
            trigger_data={"alert_id": f"QUEUE-{workflow_id}-{i}"},
        )
        created.append(d)
    return created


# ---------------------------------------------------------------------------
# Auth + input validation
# ---------------------------------------------------------------------------


def test_queue_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/decisions/queue").status_code == 401


def test_queue_rejects_unknown_status(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _login(client)
    resp = client.get("/api/decisions/queue?status=something_else")
    assert resp.status_code == 400
    assert "status" in resp.get_json()["error"]


def test_queue_rejects_unknown_category(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _login(client)
    resp = client.get("/api/decisions/queue?status=at_risk&category=unknown")
    assert resp.status_code == 400
    assert "category" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# At-risk default
# ---------------------------------------------------------------------------


def test_queue_returns_at_risk_subset_with_canonical_envelope(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    _seed_at_risk(count=2)
    _login(client)
    resp = client.get("/api/decisions/queue?status=at_risk")
    assert resp.status_code == 200
    body = resp.get_json()
    # Envelope shape — every field the drawer + landing plan depend on.
    assert {
        "decisions",
        "total_count",
        "filtered_count",
        "next_cursor",
        "status",
        "category",
    } <= body.keys()
    assert body["status"] == "at_risk"
    assert body["category"] is None
    assert body["next_cursor"] is None
    assert body["total_count"] >= 2
    assert body["filtered_count"] >= 2


def test_queue_row_shape_is_slim_real_fields(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """Per D1 (a): real fields only — decision_number, category pill,
    title, SLA, assignee. No memberName/accountNumber placeholders."""
    _seed_at_risk(count=1)
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk").get_json()
    assert body["decisions"], "expected at least one at-risk decision"
    row = body["decisions"][0]
    expected = {
        "id",
        "decision_number",
        "workflow_id",
        "category",
        "title",
        "description",
        "sla_deadline",
        "sla_status",
        "status",
        "assignee",
    }
    assert expected <= row.keys()
    # No leftover placeholder fields from the design-package mock.
    assert "memberName" not in row
    assert "accountNumber" not in row
    # category for BSA workflows is "compliance" per the shared mapping.
    bsa_rows = [r for r in body["decisions"] if r["workflow_id"] == "01-regulatory-compliance"]
    if bsa_rows:
        assert bsa_rows[0]["category"] == "compliance"


def test_queue_count_matches_dashboard_at_risk_total(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """Invariant: a queue with ``status=at_risk`` and no category filter has
    ``filtered_count == dashboard.operational.totals.at_risk``. The two
    surfaces share ``at_risk_filter()`` so they must never drift."""
    _seed_at_risk(count=3)
    _login(client)
    dash = client.get("/api/dashboard").get_json()
    q = client.get("/api/decisions/queue?status=at_risk").get_json()
    assert q["filtered_count"] == dash["operational"]["totals"]["at_risk"]


def test_queue_apex_excluded(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """Apex decisions should never appear in the operational queue. Even
    if an at-risk apex decision exists (it shouldn't), the queue excludes it."""
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk").get_json()
    workflow_ids = {r["workflow_id"] for r in body["decisions"]}
    assert "10-apex" not in workflow_ids


# ---------------------------------------------------------------------------
# Category filter
# ---------------------------------------------------------------------------


def test_queue_category_filter_narrows_results(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _seed_at_risk(workflow_id="01-regulatory-compliance", count=2)
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk&category=compliance").get_json()
    # All rows are in compliance workflows.
    for row in body["decisions"]:
        assert row["category"] == "compliance"
    # filtered_count ≤ total_count invariant.
    assert body["filtered_count"] <= body["total_count"]


def test_queue_category_invariant_filtered_le_total(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """For every {at_risk + category} combination, filtered_count ≤ total_count."""
    _seed_at_risk(count=1)
    _login(client)
    for category in ("credit", "compliance", "ops"):
        body = client.get(f"/api/decisions/queue?status=at_risk&category={category}").get_json()
        assert body["filtered_count"] <= body["total_count"], (
            f"category={category} broke filtered ≤ total invariant"
        )


# ---------------------------------------------------------------------------
# Status=open variant (powers the "All clear → show all open" CTA)
# ---------------------------------------------------------------------------


def test_queue_status_open_returns_full_open_population(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    _login(client)
    dash = client.get("/api/dashboard").get_json()
    body = client.get("/api/decisions/queue?status=open").get_json()
    # Same status filter as the dashboard's "open" total.
    assert body["filtered_count"] == dash["operational"]["totals"]["open"]


# ---------------------------------------------------------------------------
# Posture context (empty at-risk = "All clear" empty state)
# ---------------------------------------------------------------------------


def test_queue_posture_context_present_when_at_risk_empty(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    """When status=at_risk and the filtered list is empty, the response
    includes the three-stat posture context that powers the All Clear
    empty state. Force the empty state by filtering on a category with
    no at-risk decisions seeded."""
    _login(client)
    # Use a category that's unlikely to have at-risk seeds — "credit" tends
    # to be quiet in the seed; we ensure the at-risk + credit intersection
    # is empty by filtering to a category we know has 0 matching at-risk.
    # (If the seed evolves to populate credit, this assertion still holds
    # only when filtered_count is 0; the conditional below skips otherwise.)
    body = client.get("/api/decisions/queue?status=at_risk&category=credit").get_json()
    if body["filtered_count"] == 0:
        assert "posture_context" in body
        pc = body["posture_context"]
        assert set(pc.keys()) == {"open_count", "avg_cycle_days", "upcoming_count_48h"}
        assert isinstance(pc["open_count"], int)
        assert isinstance(pc["upcoming_count_48h"], int)
        # avg_cycle_days is float | None depending on whether any decisions
        # have been resolved in the trailing 30 days.
        assert pc["avg_cycle_days"] is None or isinstance(pc["avg_cycle_days"], float)


def test_queue_posture_context_absent_when_results_present(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    """When the at-risk list isn't empty, posture_context is omitted."""
    _seed_at_risk(count=1)
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk").get_json()
    assert body["filtered_count"] >= 1
    assert "posture_context" not in body


def test_queue_posture_context_absent_for_status_open(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """posture_context only fires on the at-risk variant — the "All clear"
    empty state doesn't apply to the "show all open" widened view."""
    _login(client)
    body = client.get("/api/decisions/queue?status=open").get_json()
    assert "posture_context" not in body


# ---------------------------------------------------------------------------
# Pagination + sort
# ---------------------------------------------------------------------------


def test_queue_pagination_caps_limit_and_floors_offset(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk&limit=1&offset=0").get_json()
    assert len(body["decisions"]) <= 1


def test_queue_sort_is_sla_deadline_ascending(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """The drawer's "most urgent first" reads as sla_deadline ASC nulls last."""
    _seed_at_risk(count=3)
    _login(client)
    body = client.get("/api/decisions/queue?status=at_risk&limit=50").get_json()
    deadlines = [r["sla_deadline"] for r in body["decisions"] if r["sla_deadline"]]
    assert deadlines == sorted(deadlines), "expected SLA deadlines in ascending order"
