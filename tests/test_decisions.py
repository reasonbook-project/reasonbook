# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Decision lifecycle tests — manager + API + authority + scope/density."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
from reasonbook.db import schema_prefix
from reasonbook.db import session_scope
from reasonbook.decisions import manager
from reasonbook.models import Decision, User
from scripts.seed_dev import DEMO_PASSWORD

pytestmark = pytest.mark.skip(
    reason=(
        "Banking-workflow fixtures retired in WORKFLOW-MIGRATION (Step 2). "
        "This module's tests assume specific banking workflow ids, decision "
        "types, and seeded entitlements; re-enable after the federal seed "
        "lands as part of Phase 1 Step 8 (UI / nav: Caseload)."
    ),
)
# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(seeded: Engine) -> Iterator[Flask]:  # noqa: ARG001
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def _login(client: FlaskClient, username: str = "jamie.kim") -> dict[str, Any]:
    resp = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    body: dict[str, Any] = resp.get_json()
    return body


def _user_id(username: str) -> uuid.UUID:
    with session_scope() as s:
        user = s.query(User).filter(User.username == username).one()
        return user.id


def _create_bsa_alert(*, owner: str | None = None) -> uuid.UUID:
    """Insert a sample BSA AML alert decision via the manager directly."""
    creator = _user_id("sarah.mitchell")
    owner_id = _user_id(owner) if owner else None
    d = manager.create_decision(
        tenant_id="us-federal",
        workflow_id="01-regulatory-compliance",
        decision_type="bsa_aml_alert",
        title="Sample BSA Alert",
        created_by=creator,
        priority="critical",
        sla_hours=24,
        owner_id=owner_id,
        signal_source="ingest.bsa.test",
        signal_summary="Synthetic alert for tests",
        trigger_data={"alert_id": "TEST-001"},
    )
    return d.id


# ---------------------------------------------------------------------------
# DecisionManager — direct (no HTTP)
# ---------------------------------------------------------------------------


def test_create_decision_open_when_no_owner(seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    d = manager.get_decision(did)
    assert d is not None
    assert d.status == "open"
    assert d.signal_captured_at is not None
    assert d.decision_number is not None
    assert d.decision_number.startswith("DEC-")


def test_create_decision_assigned_when_owner_provided(
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert(owner="jamie.kim")
    d = manager.get_decision(did)
    assert d is not None
    assert d.status == "assigned"
    assert d.assigned_at is not None


def test_claim_decision_sets_in_progress_and_authority_snapshot(
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    d = manager.claim_decision(decision_id=did, user_id=_user_id("jamie.kim"))
    assert d.status == "in_progress"
    assert d.owner_authority_level == 3  # bsa_officer level from seed
    # Marcus is Jamie's supervisor for BSA, so escalation_path has him.
    assert d.escalation_path
    names = [step["name"] for step in d.escalation_path]
    assert "Marcus Webb" in names


def test_claim_is_idempotent_for_existing_owner(seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    again = manager.claim_decision(decision_id=did, user_id=jamie)
    assert again.status == "in_progress"


def test_finalize_with_sufficient_authority_succeeds(
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    d = manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",  # bsa_officer level 3
        rationale="Pattern matches structuring; aggregate $42K across 6 accounts.",
        evidence_refs=[{"type": "transaction_log", "id": "txlog-1"}],
        alternatives=[{"id": "continue_monitoring", "rejected_reason": "pattern is clear"}],
    )
    assert d.status == "decided"
    assert d.selected_option == "file_sar"
    assert d.rationale is not None
    assert d.rationale.startswith("Pattern matches")


def test_finalize_with_insufficient_authority_rejected(
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    # David has no user_workflow_authority on BSA per seed.
    david = _user_id("david.park")
    # David can't even claim it (no authority level), but he can become
    # owner; the gate is at finalize. Manually claim to set ownership:
    with session_scope() as s:
        d = s.get(Decision, did)
        assert d is not None
        d.owner_id = david
        d.status = "in_progress"

    with pytest.raises(manager.DecisionAuthorityError):
        manager.finalize_decision(
            decision_id=did,
            user_id=david,
            selected_option="file_sar",
            rationale="Trying to file as data steward.",
        )


def test_full_lifecycle_creates_event_log(seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",
        rationale="Confirmed structuring across multiple accounts.",
    )
    manager.record_action(
        decision_id=did,
        user_id=jamie,
        artifacts=[{"type": "sar_form", "id": "SAR-1"}],
    )
    manager.record_outcome(
        decision_id=did,
        user_id=jamie,
        outcome_text="SAR accepted by FinCEN.",
        outcome_impact="positive",
    )

    events = manager.get_events(did)
    actions = [e.action for e in events]
    assert actions == [
        "created",
        "claimed",
        "finalized",
        "action_recorded",
        "outcome_recorded",
    ]
    # Final state
    d = manager.get_decision(did)
    assert d is not None
    assert d.status == "closed"
    assert d.outcome_recorded_at is not None


# ---------------------------------------------------------------------------
# HTTP API
# ---------------------------------------------------------------------------


def test_get_decisions_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/decisions").status_code == 401


def test_scope_mine_only_shows_owned(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _create_bsa_alert()  # unowned
    _create_bsa_alert(owner="jamie.kim")  # Jamie's

    _login(client, "jamie.kim")
    resp = client.get("/api/decisions?scope=mine&density=active")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 1
    assert items[0]["owner_id"] == str(_user_id("jamie.kim"))


def test_scope_team_for_supervisor_shows_reports(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    new_id = _create_bsa_alert(owner="jamie.kim")
    _login(client, "marcus.webb")  # supervises Jamie on BSA
    resp = client.get("/api/decisions?scope=team")
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    # Marcus's team scope returns decisions owned by his reports. The new
    # decision should be visible; sanity-check Jamie's id is among the
    # owners (other seeded team members may also appear).
    jamie_id = str(_user_id("jamie.kim"))
    ids = {d["id"] for d in items}
    assert str(new_id) in ids
    assert jamie_id in {d["owner_id"] for d in items}


def test_density_active_excludes_closed(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",
        rationale="x",
    )
    manager.record_outcome(
        decision_id=did, user_id=jamie, outcome_text="done", outcome_impact="positive"
    )

    _login(client, "jamie.kim")
    active = client.get("/api/decisions?density=active").get_json()["total"]
    all_ = client.get("/api/decisions?density=all").get_json()["total"]
    assert all_ == active + 1


def test_default_sort_is_severity_then_due_date(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """Default list order is severity DESC (critical → high → medium → low),
    sla_deadline ASC nulls-last within tier, created_at DESC tiebreak.
    Round 2 of inbox UX — supersedes the round-1 'due today' pin."""
    from datetime import UTC, datetime, timedelta

    crit = _create_bsa_alert()
    hi = _create_bsa_alert()
    med = _create_bsa_alert()
    now = datetime.now(UTC)
    with session_scope() as s:
        # Critical with the LATEST deadline; medium with the EARLIEST.
        # Severity wins regardless of date — proves severity is the
        # primary sort key, not just a tiebreak.
        for did, severity, deadline in (
            (crit, "critical", now + timedelta(days=10)),
            (hi, "high", now + timedelta(days=5)),
            (med, "medium", now + timedelta(hours=1)),
        ):
            row = s.get(Decision, did)
            assert row is not None
            row.severity = severity
            row.sla_deadline = deadline

    _login(client, "jamie.kim")
    items = client.get("/api/decisions?density=active").get_json()["items"]
    ids = [d["id"] for d in items]
    assert ids.index(str(crit)) < ids.index(str(hi)) < ids.index(str(med))


def test_claim_via_api_then_finalize(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    claim_resp = client.post(f"/api/decisions/{did}/claim")
    assert claim_resp.status_code == 200
    assert claim_resp.get_json()["status"] == "in_progress"

    finalize_resp = client.post(
        f"/api/decisions/{did}/finalize",
        json={
            "selected_option": "file_sar",
            "rationale": "Pattern matches structuring across 6 accounts.",
            "evidence_refs": [],
        },
    )
    assert finalize_resp.status_code == 200
    body = finalize_resp.get_json()
    assert body["status"] == "decided"
    assert body["selected_option"] == "file_sar"


def test_finalize_blocks_unauthorised_user_via_api(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    # David has no BSA authority. Login + try to finalize.
    _login(client, "david.park")
    # David must claim first to set ownership.
    claim_resp = client.post(f"/api/decisions/{did}/claim")
    assert claim_resp.status_code == 200

    finalize_resp = client.post(
        f"/api/decisions/{did}/finalize",
        json={"selected_option": "file_sar", "rationale": "Trying anyway."},
    )
    assert finalize_resp.status_code == 403


def test_decision_detail_404_when_other_tenant(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    from reasonbook.auth.users import hash_password

    did = _create_bsa_alert()

    # Create a stranger tenant + user with a freshly hashed password.
    spy_hash = hash_password(DEMO_PASSWORD)
    from sqlalchemy import text

    from reasonbook.db import session_scope as _ss

    with _ss() as conn:
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type)
                VALUES ('stranger', 'Stranger Co', 'CREDIT_UNION')
            """)
        )
        # eula_version set to current so the spy isn't intercepted by the
        # §9.11 EULA re-prompt middleware before reaching the cross-tenant
        # 404 path this test is verifying.
        from reasonbook.legal.eula import EULA_CURRENT_VERSION

        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}users
                  (id, tenant_id, username, email, password_hash, name, role, status,
                   eula_version, eula_accepted_at)
                VALUES
                  (gen_random_uuid(), 'stranger', 'spy',
                   's@x.com', :ph, 'Spy', 'admin', 'active',
                   :eula_version, CURRENT_TIMESTAMP)
            """),
            {"ph": spy_hash, "eula_version": EULA_CURRENT_VERSION},
        )

    resp = client.post("/api/auth/login", json={"username": "spy", "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()
    detail_resp = client.get(f"/api/decisions/{did}")
    assert detail_resp.status_code == 404


def test_events_endpoint_returns_full_log(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)

    _login(client, "jamie.kim")
    resp = client.get(f"/api/decisions/{did}/events")
    assert resp.status_code == 200
    actions = [e["action"] for e in resp.get_json()["items"]]
    assert actions == ["created", "claimed"]


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 4 — manual decision creation via POST /api/decisions
# ---------------------------------------------------------------------------


def test_manual_create_succeeds_with_sufficient_authority(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """Jamie (BSA officer level 3) can create a sar_filing_decision
    (manually_creatable=true, authoring_authority_level=bsa_officer)."""
    _login(client, "jamie.kim")
    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "01-regulatory-compliance",
            "decision_type": "sar_filing_decision",
            "title": "Manual SAR — wire transfer pattern",
            "signal_summary": "Officer noticed structuring pattern across three accounts",
            "priority": "critical",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()

    # Server-generated signal_source carries the manual.{user_id}.{uuid} shape.
    jamie_id = str(_user_id("jamie.kim"))
    assert body["signal_source"].startswith(f"manual.{jamie_id}.")

    with session_scope() as s:
        d = s.get(Decision, uuid.UUID(body["id"]))
        assert d is not None
        assert d.signal_source is not None
        assert d.signal_source.startswith(f"manual.{jamie_id}.")
        assert d.created_by == _user_id("jamie.kim")


def test_manual_create_rejects_when_not_manually_creatable(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """bsa_aml_alert has manually_creatable=false (it's a pure-monitoring
    detection). Even Jamie's BSA officer authority can't create one manually."""
    _login(client, "jamie.kim")
    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "01-regulatory-compliance",
            "decision_type": "bsa_aml_alert",
            "title": "Should not be allowed",
        },
    )
    assert resp.status_code == 403
    assert "not manually creatable" in resp.get_json()["error"]


def test_manual_create_rejects_when_user_below_required_authority(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """David (data steward) has no BSA authority — must be 403'd even on a
    manually_creatable=true decision type."""
    _login(client, "david.park")
    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "01-regulatory-compliance",
            "decision_type": "sar_filing_decision",
            "title": "Unauthorised attempt",
        },
    )
    assert resp.status_code == 403
    error = resp.get_json()["error"]
    assert "no active authority" in error or "below the required" in error


def test_manual_create_overrides_client_supplied_signal_source(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """If the body sets signal_source, the server discards it and writes the
    manual.{user_id}.{uuid} value. Prevents callers from spoofing ingest
    signal_source values that would otherwise collide with the dedup invariant."""
    _login(client, "jamie.kim")
    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "01-regulatory-compliance",
            "decision_type": "sar_filing_decision",
            "title": "Override test",
            "signal_source": "ingest.bsa.sar_filing_decision.alert_backlog",
        },
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert not body["signal_source"].startswith("ingest.")
    assert body["signal_source"].startswith("manual.")


def test_manual_create_rejects_unknown_decision_type(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    _login(client, "jamie.kim")
    resp = client.post(
        "/api/decisions",
        json={
            "workflow_id": "01-regulatory-compliance",
            "decision_type": "ghost_type",
            "title": "x",
        },
    )
    assert resp.status_code == 403
    assert "not defined" in resp.get_json()["error"]


def test_manual_create_requires_workflow_id(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    _login(client, "jamie.kim")
    resp = client.post("/api/decisions", json={"decision_type": "sar_filing_decision"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 5 — PATCH stage edits
# ---------------------------------------------------------------------------


def test_patch_signal_records_diff_event(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.patch(
        f"/api/decisions/{did}/signal",
        json={"signal_summary": "Updated — pattern includes wire transfers"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["signal_summary"].startswith("Updated")

    events = manager.get_events(did)
    edits = [e for e in events if e.action == "stage_edit"]
    assert len(edits) == 1
    meta = edits[0].event_metadata
    assert meta is not None
    assert meta["stage"] == "signal"
    assert meta["diff"]["signal_summary"]["old"] == "Synthetic alert for tests"
    assert meta["diff"]["signal_summary"]["new"].startswith("Updated")


def test_patch_signal_rejects_signal_source_immutable(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/signal",
        json={"signal_source": "spoofed.ingest.something"},
    )
    assert resp.status_code == 400
    assert "immutable" in resp.get_json()["error"]


def test_patch_decision_rejected_before_claim(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """Decision stage isn't reached until claim → in_progress."""
    did = _create_bsa_alert()  # status: open
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/decision",
        json={"rationale": "Too early"},
    )
    assert resp.status_code == 409
    assert "not yet editable" in resp.get_json()["error"]


def test_patch_decision_works_after_claim(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)  # → in_progress

    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/decision",
        json={
            "selected_option": "file_sar",
            "rationale": "Working draft of rationale before finalizing",
            "evidence_refs": [{"type": "txlog", "id": "T-1"}],
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    # Status unchanged — PATCH never advances the lifecycle.
    assert body["status"] == "in_progress"
    assert body["selected_option"] == "file_sar"


def test_patch_action_rejected_before_finalize(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/action",
        json={"action_artifacts": [{"type": "sar_form", "id": "X"}]},
    )
    assert resp.status_code == 409


def test_patch_action_works_after_finalize(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",
        rationale="Pattern matches; aggregate $42K across 6 accounts.",
    )
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/action",
        json={
            "action_started_at": "2026-04-29T10:00:00+00:00",
            "action_artifacts": [{"type": "sar_form", "id": "SAR-7788"}],
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["action_started_at"] is not None


def test_patch_outcome_rejected_before_recorded(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",
        rationale="Rationale text long enough to satisfy len(50) gate.",
    )
    # status is now decided — outcome stage not yet reached.
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/outcome",
        json={"outcome_text": "Premature"},
    )
    assert resp.status_code == 409


def test_patch_outcome_works_after_recorded(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.finalize_decision(
        decision_id=did,
        user_id=jamie,
        selected_option="file_sar",
        rationale="Rationale text long enough to satisfy len(50) gate.",
    )
    manager.record_outcome(decision_id=did, user_id=jamie, outcome_text="Initial outcome captured.")
    # status now closed — outcome stage reached.
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/outcome",
        json={
            "outcome_text": "Revised outcome — SAR accepted by FinCEN.",
            "outcome_impact": "positive",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["outcome_text"].startswith("Revised")


def test_patch_rejects_user_without_workflow_authority(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """David has no BSA authority — can't patch even stage 1 fields."""
    did = _create_bsa_alert()
    _login(client, "david.park")
    resp = client.patch(
        f"/api/decisions/{did}/signal",
        json={"signal_summary": "Should be blocked"},
    )
    assert resp.status_code == 403
    assert "no active authority" in resp.get_json()["error"]


def test_patch_no_op_when_value_unchanged(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    """If the new value equals the existing value, no event is written."""
    did = _create_bsa_alert()
    _login(client, "jamie.kim")
    resp = client.patch(
        f"/api/decisions/{did}/signal",
        json={"signal_summary": "Synthetic alert for tests"},  # unchanged
    )
    assert resp.status_code == 200

    events = manager.get_events(did)
    edits = [e for e in events if e.action == "stage_edit"]
    assert edits == []


# ---------------------------------------------------------------------------
# Phase 7.5 Gate 7 — attachments + comments
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> Iterator[Any]:
    """Point AttachmentStorage at a tmp directory for the duration of the test."""
    from reasonbook.config import get_settings

    monkeypatch.setenv("ATTACHMENT_BACKEND", "local")
    monkeypatch.setenv("ATTACHMENT_LOCAL_ROOT", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_attachment_upload_creates_row_and_event(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
) -> None:
    import io

    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.post(
        f"/api/decisions/{did}/attachments",
        data={
            "stage": "evidence",
            "description": "Transaction log for SAR review",
            "file": (io.BytesIO(b"transaction log contents"), "txlog.csv"),
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["filename"] == "txlog.csv"
    assert body["stage"] == "evidence"
    assert body["size_bytes"] == len(b"transaction log contents")
    assert body["storage_backend"] == "local"

    events = manager.get_events(did, include="all")
    actions = [e.action for e in events]
    assert "attachment_added" in actions
    added = [e for e in events if e.action == "attachment_added"][0]
    assert added.event_metadata is not None
    assert added.event_metadata["filename"] == "txlog.csv"
    assert added.event_metadata["attachment_id"] == body["id"]


def test_attachment_list_excludes_superseded(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
) -> None:
    import io

    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    upload = client.post(
        f"/api/decisions/{did}/attachments",
        data={"stage": "evidence", "file": (io.BytesIO(b"x"), "a.txt")},
        content_type="multipart/form-data",
    )
    aid = upload.get_json()["id"]

    listed = client.get(f"/api/decisions/{did}/attachments").get_json()["items"]
    assert len(listed) == 1

    delete_resp = client.delete(f"/api/decisions/{did}/attachments/{aid}")
    assert delete_resp.status_code == 200

    listed = client.get(f"/api/decisions/{did}/attachments").get_json()["items"]
    assert listed == []

    events = manager.get_events(did, include="all")
    actions = [e.action for e in events]
    assert "attachment_removed" in actions


def test_attachment_download_streams_bytes_for_local_backend(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
) -> None:
    import io

    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    upload = client.post(
        f"/api/decisions/{did}/attachments",
        data={"stage": "evidence", "file": (io.BytesIO(b"hello world"), "greet.txt")},
        content_type="multipart/form-data",
    )
    aid = upload.get_json()["id"]

    resp = client.get(f"/api/decisions/{did}/attachments/{aid}/download")
    assert resp.status_code == 200
    assert resp.data == b"hello world"
    assert "greet.txt" in resp.headers["Content-Disposition"]


def test_attachment_download_redirects_when_backend_mints_signed_url(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the storage backend can produce a presigned URL (e.g. DO Spaces
    in production), the API responds with a 302 redirect so the browser
    follows it natively. The frontend's <a target="_blank"> opens the PDF
    in a new tab — no JSON parsing required."""
    import io

    from reasonbook.api import decisions as decisions_api

    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    upload = client.post(
        f"/api/decisions/{did}/attachments",
        data={"stage": "evidence", "file": (io.BytesIO(b"x"), "x.pdf")},
        content_type="multipart/form-data",
    )
    aid = upload.get_json()["id"]

    fake_url = (
        "https://s3.nyc3.amazonaws.com/reasonbook-test/decision-uuid/key.pdf?X-Amz-Signature=abc"
    )

    class _SignedStorage:
        backend_name = "local"

        def signed_url(self, *_args: Any, **_kwargs: Any) -> str:
            return fake_url

        def get(self, *_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError("get should not be called when signed_url returns")

    monkeypatch.setattr(decisions_api, "get_storage", lambda: _SignedStorage())

    resp = client.get(
        f"/api/decisions/{did}/attachments/{aid}/download",
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["Location"] == fake_url


def test_attachment_upload_rejects_user_without_authority(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
) -> None:
    import io

    did = _create_bsa_alert()
    _login(client, "david.park")
    resp = client.post(
        f"/api/decisions/{did}/attachments",
        data={"stage": "evidence", "file": (io.BytesIO(b"x"), "a.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 403


def test_attachment_invalid_stage_rejected(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
    storage_root: Any,  # noqa: ARG001
) -> None:
    import io

    did = _create_bsa_alert()
    _login(client, "jamie.kim")
    resp = client.post(
        f"/api/decisions/{did}/attachments",
        data={"stage": "ghost_stage", "file": (io.BytesIO(b"x"), "a.txt")},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    assert "invalid attachment stage" in resp.get_json()["error"]


def test_comment_posts_event_with_metadata(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.post(
        f"/api/decisions/{did}/comments",
        json={
            "body": "Reviewing as part of Friday batch",
            "stage_context": "decision",
            "mentions": [str(_user_id("marcus.webb"))],
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["action"] == "comment"
    assert body["comment"] == "Reviewing as part of Friday batch"
    assert body["metadata"]["stage_context"] == "decision"
    assert body["metadata"]["mentions"] == [str(_user_id("marcus.webb"))]


def test_comment_rejects_user_without_authority(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    _login(client, "david.park")
    resp = client.post(
        f"/api/decisions/{did}/comments",
        json={"body": "Should not work"},
    )
    assert resp.status_code == 403


def test_events_include_filter(
    client: FlaskClient,
    seeded: Engine,  # noqa: ARG001
) -> None:
    did = _create_bsa_alert()
    jamie = _user_id("jamie.kim")
    manager.claim_decision(decision_id=did, user_id=jamie)
    manager.post_comment(
        decision_id=did,
        user_id=jamie,
        body="Quick note before finalizing.",
        stage_context="decision",
    )

    _login(client, "jamie.kim")

    audit = client.get(f"/api/decisions/{did}/events").get_json()["items"]
    audit_actions = [e["action"] for e in audit]
    assert "comment" not in audit_actions
    assert "created" in audit_actions
    assert "claimed" in audit_actions

    comments = client.get(f"/api/decisions/{did}/events?include=comments").get_json()["items"]
    assert [e["action"] for e in comments] == ["comment"]

    everything = client.get(f"/api/decisions/{did}/events?include=all").get_json()["items"]
    actions = [e["action"] for e in everything]
    assert actions == ["created", "claimed", "comment"]


# ---------------------------------------------------------------------------
# Phase 8.5 — bulk operations
# ---------------------------------------------------------------------------


def test_bulk_claim_succeeds_for_all_visible_decisions(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    a = _create_bsa_alert()
    b = _create_bsa_alert()
    c = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.post(
        "/api/decisions/bulk/claim",
        json={"decision_ids": [str(a), str(b), str(c)]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["succeeded"] == 3
    assert body["failed"] == 0
    assert all(r["ok"] for r in body["results"])
    assert "bulk_operation_id" in body

    # Each decision now belongs to Jamie and is in_progress.
    jamie = _user_id("jamie.kim")
    for did in (a, b, c):
        d = manager.get_decision(did)
        assert d is not None
        assert d.status == "in_progress"
        assert d.owner_id == jamie


def test_bulk_claim_writes_events_with_correlated_bulk_operation_id(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    """The whole point of bulk_operation_id — audit can reconstruct the
    fleet of decisions touched by a single request via one query."""
    from sqlalchemy import text as sql_text

    a = _create_bsa_alert()
    b = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.post(
        "/api/decisions/bulk/claim",
        json={"decision_ids": [str(a), str(b)]},
    )
    assert resp.status_code == 200
    bulk_op_id = resp.get_json()["bulk_operation_id"]

    # Both claim events carry the same bulk_operation_id in metadata.
    with session_scope() as s:
        rows = (
            s.execute(
                sql_text(
                    f"SELECT decision_id FROM {schema_prefix()}decision_events "
                    "WHERE action='claimed' "
                    "AND metadata->>'bulk_operation_id' = :bid"
                ),
                {"bid": bulk_op_id},
            )
            .mappings()
            .all()
        )
    decision_ids = {str(r["decision_id"]) for r in rows}
    assert decision_ids == {str(a), str(b)}


def test_bulk_claim_partial_success_when_one_decision_already_decided(
    client: FlaskClient, seeded: Engine
) -> None:  # noqa: ARG001
    """When some ids fail, the request still succeeds and the per-id
    results carry the specific reason."""
    a = _create_bsa_alert()  # claimable
    b = _create_bsa_alert(owner="jamie.kim")  # assigned to Jamie
    _login(client, "jamie.kim")
    # Drive b to decided: claim → finalize.
    claim = client.post(f"/api/decisions/{b}/claim")
    assert claim.status_code == 200, claim.get_json()
    finalize = client.post(
        f"/api/decisions/{b}/finalize",
        json={
            "selected_option": "file_sar",
            "rationale": "Pattern matches FinCEN red flags; filing within 30-day window.",
        },
    )
    assert finalize.status_code == 200, finalize.get_json()

    resp = client.post(
        "/api/decisions/bulk/claim",
        json={"decision_ids": [str(a), str(b)]},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {r["decision_id"]: r for r in body["results"]}
    assert by_id[str(a)]["ok"] is True
    assert by_id[str(b)]["ok"] is False
    assert "transition" in by_id[str(b)]["error"].lower()


def test_bulk_claim_rejects_decision_in_other_tenant(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    """Cross-tenant ids never sneak in via the bulk endpoint."""
    import uuid as _uuid

    a = _create_bsa_alert()
    fake_id = _uuid.uuid4()  # nonexistent / cross-tenant
    _login(client, "jamie.kim")

    resp = client.post(
        "/api/decisions/bulk/claim",
        json={"decision_ids": [str(a), str(fake_id)]},
    )
    body = resp.get_json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {r["decision_id"]: r for r in body["results"]}
    assert by_id[str(fake_id)]["ok"] is False


def test_bulk_comment_posts_one_event_per_decision(client: FlaskClient, seeded: Engine) -> None:  # noqa: ARG001
    from sqlalchemy import text as sql_text

    a = _create_bsa_alert()
    b = _create_bsa_alert()
    _login(client, "jamie.kim")

    resp = client.post(
        "/api/decisions/bulk/comment",
        json={
            "decision_ids": [str(a), str(b)],
            "body": "Reviewing as part of the Friday batch.",
        },
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["succeeded"] == 2
    assert body["failed"] == 0
    bulk_op_id = body["bulk_operation_id"]

    # One comment event per decision, both correlated.
    with session_scope() as s:
        rows = (
            s.execute(
                sql_text(
                    f"SELECT decision_id, comment FROM {schema_prefix()}decision_events "
                    "WHERE action='comment' "
                    "AND metadata->>'bulk_operation_id' = :bid"
                ),
                {"bid": bulk_op_id},
            )
            .mappings()
            .all()
        )
    assert len(rows) == 2
    assert all(r["comment"] == "Reviewing as part of the Friday batch." for r in rows)
