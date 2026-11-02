# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Auth flow tests — login, /me, logout, decorators, entitlement enforcement.

Uses the session-scoped seeded fixture from ``tests/conftest.py``;
each test runs inside a transaction that rolls back at teardown,
sharing one seed across the whole pytest session.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
from scripts.seed_dev import DEMO_PASSWORD


@pytest.fixture()
def app(seeded: Engine) -> Iterator[Flask]:  # noqa: ARG001
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


# ---------------------------------------------------------------------------
# /api/auth/login
# ---------------------------------------------------------------------------


def test_login_success_sets_httponly_cookie_and_returns_user(
    client: FlaskClient,
) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "jamie.kim", "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["username"] == "jamie.kim"
    assert body["tenant_id"] == "us-federal"
    # The legacy workflow-entitlement surface now carries only the apex
    # workflow; archetype-based programs flow through /api/archetypes,
    # not tenant_entitlements.

    cookie_header = resp.headers.get("Set-Cookie", "")
    assert "dp_session=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header


def test_login_rejects_bad_password(client: FlaskClient) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "jamie.kim", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert "Set-Cookie" not in resp.headers or "dp_session=" not in resp.headers.get(
        "Set-Cookie", ""
    )


def test_login_rejects_missing_user(client: FlaskClient) -> None:
    resp = client.post(
        "/api/auth/login",
        json={"username": "ghost", "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 401


def test_login_validates_required_fields(client: FlaskClient) -> None:
    resp = client.post("/api/auth/login", json={"username": ""})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# /api/auth/me  +  /api/auth/session
# ---------------------------------------------------------------------------


def _login(client: FlaskClient, username: str = "jamie.kim") -> None:
    resp = client.post("/api/auth/login", json={"username": username, "password": DEMO_PASSWORD})
    assert resp.status_code == 200, resp.get_json()


def test_me_returns_current_user_when_authenticated(client: FlaskClient) -> None:
    _login(client)
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["username"] == "jamie.kim"


def test_me_returns_401_when_anonymous(client: FlaskClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_oversight_capabilities_null_for_non_oversight_user(client: FlaskClient) -> None:
    _login(client, "jamie.kim")
    body = client.get("/api/auth/me").get_json()
    assert body["oversight_capabilities"] is None


def test_me_oversight_capabilities_for_oversight_persona(client: FlaskClient) -> None:
    """Walter Knox seed: oversight_role=inspector_general, can_record_committee_action=true.

    The ``can_record_committee_action`` field name is kept for API/code compat
    until the rename migration; semantically this is
    "can record committee / oversight action" in the federalized framing.
    """
    _login(client, "walter.knox")
    body = client.get("/api/auth/me").get_json()
    caps = body["oversight_capabilities"]
    assert caps is not None
    assert caps["oversight_role"] == "inspector_general"
    assert caps["can_record_committee_action"] is True
    assert caps["is_committee"] is True       # is_committee predicate now covers
                                          # internal audit committee + IG
    assert caps["is_executive"] is False


def test_me_oversight_capabilities_for_executive(client: FlaskClient) -> None:
    """Sarah Mitchell seed: oversight_role=agency_head, can_record_committee_action=false."""
    _login(client, "sarah.mitchell")
    body = client.get("/api/auth/me").get_json()
    caps = body["oversight_capabilities"]
    assert caps is not None
    assert caps["oversight_role"] == "agency_head"
    assert caps["can_record_committee_action"] is False
    assert caps["is_executive"] is True
    assert caps["is_committee"] is False


def test_session_returns_200_when_authenticated(client: FlaskClient) -> None:
    _login(client)
    assert client.get("/api/auth/session").status_code == 200


def test_session_returns_401_when_anonymous(client: FlaskClient) -> None:
    assert client.get("/api/auth/session").status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/logout — revocation
# ---------------------------------------------------------------------------


def test_logout_clears_cookie_and_blocks_subsequent_requests(
    client: FlaskClient,
) -> None:
    _login(client)
    assert client.get("/api/auth/me").status_code == 200

    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200

    # Cookie cleared by server. The client no
    # longer carries a valid cookie.
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


# require_workflow decorator retired in the DG-substrate cleanup.
# Single-tenant DP has no per-workflow entitlements; the decorator's
# two tests were dropped alongside the decorator itself.


def test_require_admin_allows_admin_user(client: FlaskClient, app: Flask) -> None:
    from reasonbook.auth.decorators import require_admin

    @app.get("/__test/admin")
    @require_admin
    def _admin() -> tuple[dict[str, str], int]:
        return {"ok": "yes"}, 200

    _login(client, "sarah.mitchell")
    assert client.get("/__test/admin").status_code == 200


def test_require_admin_rejects_member_user(client: FlaskClient, app: Flask) -> None:
    from reasonbook.auth.decorators import require_admin

    @app.get("/__test/admin2")
    @require_admin
    def _admin2() -> tuple[dict[str, str], int]:
        return {"ok": "yes"}, 200

    _login(client, "jamie.kim")
    assert client.get("/__test/admin2").status_code == 403
