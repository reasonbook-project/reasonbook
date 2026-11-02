# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Settings API tests — users, entitlements, overrides, PDF export."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
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


def _login(client: FlaskClient, username: str = "sarah.mitchell") -> None:
    resp = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


def test_list_users_admin_only(client: FlaskClient) -> None:
    _login(client, "jamie.kim")  # member
    assert client.get("/api/settings/users").status_code == 403


def test_list_users_returns_tenant_set(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.get("/api/settings/users")
    assert resp.status_code == 200
    usernames = sorted(u["username"] for u in resp.get_json()["items"])
    # v3.11: 12 narrative-roster personas joined the Riverdale seed.
    assert usernames == [
        "claire.boyd",
        "daniel.ortiz",
        "david.park",
        "eduardo.silva",
        "fatima.alvarez",
        "gerald.tan",
        "jamie.kim",
        "lena.tran",
        "linda.peters",
        "marcus.webb",
        "nathan.hill",
        "priya.shah",
        "ravi.kumar",
        "sarah.mitchell",
        "sofia.greer",
        "walter.knox",
    ]


def test_invite_user_creates_pending_invite(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.post(
        "/api/settings/users",
        json={
            "username": "new.user",
            "email": "new@riverdale.example",
            "name": "New User",
            "role": "member",
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "pending_invite"
    assert "temp_password" in body and len(body["temp_password"]) == 16


def test_invite_user_rejects_duplicate_username(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.post(
        "/api/settings/users",
        json={
            "username": "jamie.kim",
            "email": "x@y.com",
            "name": "X",
        },
    )
    assert resp.status_code == 409


def test_update_user_changes_role(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    list_resp = client.get("/api/settings/users").get_json()
    jamie = next(u for u in list_resp["items"] if u["username"] == "jamie.kim")
    resp = client.put(
        f"/api/settings/users/{jamie['id']}",
        json={"role": "admin", "title": "Senior BSA Officer"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["role"] == "admin"
    assert body["title"] == "Senior BSA Officer"


def test_deactivate_user_sets_inactive(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    list_resp = client.get("/api/settings/users").get_json()
    david = next(u for u in list_resp["items"] if u["username"] == "david.park")
    resp = client.delete(f"/api/settings/users/{david['id']}")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "inactive"


def test_deactivate_self_blocked(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    list_resp = client.get("/api/settings/users").get_json()
    sarah = next(u for u in list_resp["items"] if u["username"] == "sarah.mitchell")
    resp = client.delete(f"/api/settings/users/{sarah['id']}")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


def test_list_entitlements_returns_active_history_available(
    client: FlaskClient,
) -> None:
    _login(client, "sarah.mitchell")
    resp = client.get("/api/settings/entitlements")
    assert resp.status_code == 200
    body = resp.get_json()
    active_ids = {e["workflow_id"] for e in body["active"]}
    assert active_ids == {
        "01-regulatory-compliance",
        "01-regulatory-compliance",
        "10-oversight",
    }
    available_ids = {w["id"] for w in body["available"]}
    assert active_ids.issubset(available_ids)


def test_revoke_entitlement_sets_ended_at(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.delete("/api/settings/entitlements/01-regulatory-compliance")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "expired"
    assert body["ended_at"] is not None


def test_grant_entitlement_existing_active_returns_existing(
    client: FlaskClient,
) -> None:
    _login(client, "sarah.mitchell")
    resp = client.post("/api/settings/entitlements", json={"workflow_id": "01-regulatory-compliance"})
    assert resp.status_code == 200  # already active → returns same row, not 201


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


def test_get_workflow_config_returns_merged_plus_allowlist(
    client: FlaskClient,
) -> None:
    _login(client, "sarah.mitchell")
    resp = client.get("/api/settings/workflows/01-regulatory-compliance/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert "config" in body
    assert "overridable_keys" in body
    assert body["overridable_keys"]["thresholds.alert_disposition_sla_hours"] == "int"


def test_set_override_then_supersede(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    set_resp = client.post(
        "/api/settings/workflows/01-regulatory-compliance/overrides",
        json={
            "config_key": "thresholds.alert_disposition_sla_hours",
            "config_value": 24,
            "change_note": "tighter SLA per audit recommendation",
        },
    )
    assert set_resp.status_code == 201, set_resp.get_json()
    history_resp = client.get("/api/settings/workflows/01-regulatory-compliance/overrides/history")
    items = history_resp.get_json()["items"]
    assert any(i["config_key"] == "thresholds.alert_disposition_sla_hours" for i in items)

    drop_resp = client.delete(
        "/api/settings/workflows/01-regulatory-compliance/overrides/thresholds.alert_disposition_sla_hours"
    )
    assert drop_resp.status_code == 200


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------


def test_decision_pdf_export(client: FlaskClient) -> None:
    """Create a decision via the manager, then export it as PDF."""
    from reasonbook.db import session_scope as scope
    from reasonbook.decisions import manager
    from reasonbook.models import User

    with scope() as s:
        sarah = s.query(User).filter_by(username="sarah.mitchell").one()
        sarah_id = sarah.id

    decision = manager.create_decision(
        tenant_id="us-federal",
        workflow_id="01-regulatory-compliance",
        decision_type="sar_filing_decision",
        title="Test SAR for PDF export",
        created_by=sarah_id,
        priority="urgent",
        sla_hours=4,
        signal_summary="Synthetic test alert",
    )

    _login(client, "sarah.mitchell")
    resp = client.get(f"/api/decisions/{decision.id}/export")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert decision.decision_number in resp.headers["Content-Disposition"]


# ---------------------------------------------------------------------------
# Tenant settings (Phase 8.5)
# ---------------------------------------------------------------------------


def test_get_tenant_returns_basics_governance_and_profile(
    client: FlaskClient,
) -> None:
    """Members can read tenant settings; the response includes the
    structured columns plus the JSONB profile and governance defaults."""
    _login(client, "jamie.kim")  # member
    resp = client.get("/api/settings/tenant")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["tenant_id"] == "us-federal"
    assert body["org_type"] in {"CREDIT_UNION", "COMMUNITY_BANK", "SAVINGS_INSTITUTION"}
    # Profile starts as {} from the migration default; merge semantics fill in later.
    assert isinstance(body["tenant_profile"], dict)
    # Governance is surfaced with defaults even if no row exists.
    assert "governance" in body
    assert isinstance(body["governance"]["dual_control_enabled"], bool)


def test_patch_tenant_admin_only(client: FlaskClient) -> None:
    _login(client, "jamie.kim")  # member
    resp = client.patch("/api/settings/tenant", json={"name": "Riverdale 2"})
    assert resp.status_code == 403


def test_patch_tenant_basics_and_profile_merges(client: FlaskClient) -> None:
    _login(client, "sarah.mitchell")
    resp = client.patch(
        "/api/settings/tenant",
        json={
            "name": "Riverdale Community Credit Union",
            "regulator": "NCUA",
            "asset_size_band": "medium",
            "tenant_profile": {
                "fiscal_year_start_month": 1,
                "risk_appetite_statement": "Moderate, capital-preservation first.",
            },
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["name"] == "Riverdale Community Credit Union"
    assert body["regulator"] == "NCUA"
    assert body["asset_size_band"] == "medium"
    assert body["tenant_profile"]["fiscal_year_start_month"] == 1
    assert body["tenant_profile"]["risk_appetite_statement"].startswith("Moderate")

    # Second PATCH only updates one profile key — others should survive (merge semantics).
    resp2 = client.patch(
        "/api/settings/tenant",
        json={"tenant_profile": {"peer_group": "medium-credit-union-ncua"}},
    )
    assert resp2.status_code == 200
    profile = resp2.get_json()["tenant_profile"]
    assert profile["peer_group"] == "medium-credit-union-ncua"
    assert profile["fiscal_year_start_month"] == 1
    assert profile["risk_appetite_statement"].startswith("Moderate")


@pytest.mark.parametrize(
    "payload",
    [
        {"tenant_profile": {"not_a_known_key": "x"}},
        {"tenant_profile": {"fiscal_year_start_month": 13}},
        {"org_type": "FUTURE_THING"},
    ],
    ids=["unknown_profile_key", "invalid_fiscal_month", "invalid_org_type"],
)
def test_patch_tenant_rejects_invalid_payload(
    client: FlaskClient, payload: dict[str, object]
) -> None:
    """Tenant-settings PATCH rejects malformed payloads. Collapsed from three
    single-case tests."""
    _login(client, "sarah.mitchell")
    resp = client.patch("/api/settings/tenant", json=payload)
    assert resp.status_code == 400


def test_patch_tenant_governance_upserts_row(client: FlaskClient) -> None:
    """A tenant without a governance row gets one inserted on first PATCH."""
    _login(client, "sarah.mitchell")
    resp = client.patch(
        "/api/settings/tenant",
        json={
            "governance": {
                "dual_control_enabled": True,
                "require_approval_roles": ["admin"],
            }
        },
    )
    assert resp.status_code == 200
    gov = resp.get_json()["governance"]
    assert gov["dual_control_enabled"] is True
    assert gov["require_approval_roles"] == ["admin"]
    assert gov["updated_by"] is not None  # set to the calling admin's user id


def test_patch_tenant_does_not_let_admin_flip_has_apex(client: FlaskClient) -> None:
    """has_apex is gated behind the entitlements path; the tenant settings
    endpoint must ignore attempts to flip it directly."""
    _login(client, "sarah.mitchell")
    before = client.get("/api/settings/tenant").get_json()["has_apex"]
    resp = client.patch(
        "/api/settings/tenant",
        json={"has_apex": not before},
    )
    assert resp.status_code == 200
    after = resp.get_json()["has_apex"]
    assert after == before
