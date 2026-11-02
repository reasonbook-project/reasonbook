# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Backs /api/archetypes — the read shape behind the Caseload rail."""

from __future__ import annotations

import pytest
from tests.conftest import DEMO_PASSWORD
from flask.testing import FlaskClient

CASELOAD_ORDER = [
    "competitive_award",
    "formula_allocation",
    "eligibility_determination",
    "recertification",
    "modification",
    "adverse_action",
    "payment_authorization",
]


@pytest.fixture()
def auth_cookie(client: FlaskClient) -> str:
    """Log in as the canonical seeded BSA officer; return the session cookie."""
    resp = client.post(
        "/api/auth/login",
        json={"username": "jamie.kim", "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_json()
    cookie = resp.headers.get("Set-Cookie", "")
    assert "reasonbook_session" in cookie
    return cookie


def test_list_archetypes_requires_auth(client: FlaskClient) -> None:
    resp = client.get("/api/archetypes")
    assert resp.status_code == 401


def test_list_archetypes_returns_seven_in_caseload_order(
    client: FlaskClient,
    auth_cookie: str,  # noqa: ARG001 — fixture wires the session cookie
) -> None:
    resp = client.get("/api/archetypes")
    assert resp.status_code == 200
    body = resp.get_json()
    assert isinstance(body, dict)
    items = body.get("archetypes")
    assert isinstance(items, list)
    assert [a["id"] for a in items] == CASELOAD_ORDER
    # position numbers run 1..7
    assert [a["position"] for a in items] == list(range(1, 8))


def test_list_archetypes_payload_shape(
    client: FlaskClient,
    auth_cookie: str,  # noqa: ARG001
) -> None:
    resp = client.get("/api/archetypes")
    items = resp.get_json()["archetypes"]
    expected_keys = {
        "id",
        "name",
        "description",
        "family",
        "flow",
        "decision_basis",
        "promotes",
        "position",
    }
    for a in items:
        assert set(a.keys()) >= expected_keys
        assert isinstance(a["family"], list)
        assert a["promotes"] in ("every_case", "on_trigger")


def test_multi_family_archetypes_carry_all_three(
    client: FlaskClient,
    auth_cookie: str,  # noqa: ARG001
) -> None:
    """payment_authorization and adverse_action span grant / entitlement /
    procurement."""
    by_id = {a["id"]: a for a in client.get("/api/archetypes").get_json()["archetypes"]}
    assert set(by_id["payment_authorization"]["family"]) == {
        "grant",
        "entitlement",
        "procurement",
    }
    assert set(by_id["adverse_action"]["family"]) == {
        "grant",
        "entitlement",
        "procurement",
    }
