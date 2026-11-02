# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""GET /api/workflows + GET /api/workflows/:id/config tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
from reasonbook.db import schema_prefix
from reasonbook.db import session_scope
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


def test_list_workflows_returns_entitled_set(client: FlaskClient) -> None:
    _login(client)
    resp = client.get("/api/workflows")
    assert resp.status_code == 200
    ids = sorted(w["id"] for w in resp.get_json()["workflows"])
    assert ids == [
        "01-regulatory-compliance",
        "01-regulatory-compliance",
        "10-oversight",
        # User-configuration workflow — always entitled per
        # decision-governance-self-assessment-platform-variant-v1_0.md §8.5.
        # Surfaces in /api/workflows; the rail filters it out client-side.
        "user-configuration",
    ]


def test_list_workflows_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/workflows").status_code == 401


def test_get_workflow_config_returns_merged_config(client: FlaskClient) -> None:
    _login(client)
    resp = client.get("/api/workflows/01-regulatory-compliance/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["workflow"]["id"] == "01-regulatory-compliance"
    # Sanity check — a metric and a decision type are present.
    metric_ids = {m["id"] for m in body.get("metrics", [])}
    assert "sar_filing_timeliness" in metric_ids
    decision_ids = {d["id"] for d in body.get("decision_types", [])}
    assert "sar_filing_decision" in decision_ids


def test_get_workflow_config_404_for_unknown_workflow(client: FlaskClient) -> None:
    _login(client)
    assert client.get("/api/workflows/99-nope/config").status_code == 404


def test_get_workflow_config_403_when_not_entitled(client: FlaskClient, seeded: Engine) -> None:
    # Create a workflow file that's loaded but not in seed entitlements.
    # Simulate by ending Jamie's BSA entitlement and re-fetching.
    from sqlalchemy import text

    with session_scope() as conn:
        conn.execute(
            text("""
                UPDATE {schema_prefix()}tenant_entitlements
                SET ended_at = CURRENT_TIMESTAMP
                WHERE tenant_id = 'us-federal' AND workflow_id = '01-regulatory-compliance'
            """)
        )

    _login(client, "jamie.kim")
    resp = client.get("/api/workflows/01-regulatory-compliance/config")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Phase 14 — Schema Explorer export endpoint
# ---------------------------------------------------------------------------


def test_schema_export_yaml_returns_workflow_config(client: FlaskClient) -> None:
    """YAML export round-trips the merged config — same data the explorer renders."""
    _login(client)
    resp = client.get("/api/workflows/01-regulatory-compliance/schema/export?format=yaml")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/yaml")
    body = resp.data.decode("utf-8")
    # Spot-check the YAML serialised content includes the workflow header
    # plus a trigger-metric column from the upload section.
    assert "id: 01-regulatory-compliance" in body
    assert "sar_filing_timeliness" in body


def test_schema_export_json_returns_workflow_config(client: FlaskClient) -> None:
    """JSON export round-trips the same merged config as YAML, just in JSON."""
    _login(client)
    resp = client.get("/api/workflows/01-regulatory-compliance/schema/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/json")
    import json

    body = json.loads(resp.data)
    assert body["workflow"]["id"] == "01-regulatory-compliance"
    metric_ids = {m["id"] for m in body.get("metrics", [])}
    assert "sar_filing_timeliness" in metric_ids


def test_schema_export_default_format_is_yaml(client: FlaskClient) -> None:
    _login(client)
    resp = client.get("/api/workflows/01-regulatory-compliance/schema/export")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/yaml")


def test_schema_export_rejects_unknown_format(client: FlaskClient) -> None:
    _login(client)
    resp = client.get("/api/workflows/01-regulatory-compliance/schema/export?format=xml")
    assert resp.status_code == 400


def test_schema_export_404_for_unknown_workflow(client: FlaskClient) -> None:
    _login(client)
    assert client.get("/api/workflows/99-nope/schema/export?format=yaml").status_code == 404


# test_schema_export_403_when_not_entitled removed in the DG-substrate
# cleanup — schema exports are no longer entitlement-gated (single-tenant
# DP has no per-workflow entitlements).


# ---------------------------------------------------------------------------
# Semantic Layer Catalog — aggregated multi-workflow export
# ---------------------------------------------------------------------------


def test_catalog_export_yaml_includes_all_entitled_workflows(
    client: FlaskClient,
) -> None:
    """Default (no workflow_ids param) returns every entitled workflow
    wrapped in the catalog: {version, workflows: [...]} structure."""
    _login(client)
    resp = client.get("/api/catalog/export?format=yaml")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("application/yaml")
    assert "reasonbook-catalog-all-v1.0.yaml" in resp.headers["Content-Disposition"]
    body = resp.data.decode("utf-8")
    assert "catalog:" in body
    assert "version: v1.0" in body
    assert "workflows:" in body
    # All entitled workflows are present
    assert "01-regulatory-compliance" in body
    assert "01-regulatory-compliance" in body


def test_catalog_export_json_returns_structured_catalog(
    client: FlaskClient,
) -> None:
    """JSON shape: {catalog: {version, workflows: [{workflow_id, config}]}}."""
    _login(client)
    resp = client.get("/api/catalog/export?format=json")
    assert resp.status_code == 200
    import json

    body = json.loads(resp.data)
    assert body["catalog"]["version"] == "v1.0"
    workflow_ids = {w["workflow_id"] for w in body["catalog"]["workflows"]}
    assert "01-regulatory-compliance" in workflow_ids
    # Each workflow carries its full merged config
    bsa = next(w for w in body["catalog"]["workflows"] if w["workflow_id"] == "01-regulatory-compliance")
    assert bsa["config"]["workflow"]["id"] == "01-regulatory-compliance"


def test_catalog_export_filters_by_workflow_ids(client: FlaskClient) -> None:
    """workflow_ids param narrows the export to the listed workflows."""
    _login(client)
    resp = client.get(
        "/api/catalog/export?format=json&workflow_ids=01-regulatory-compliance,01-regulatory-compliance"
    )
    assert resp.status_code == 200
    import json

    body = json.loads(resp.data)
    workflow_ids = [w["workflow_id"] for w in body["catalog"]["workflows"]]
    # Order preserved per the request
    assert workflow_ids == ["01-regulatory-compliance", "01-regulatory-compliance"]


def test_catalog_export_single_workflow_uses_id_in_filename(
    client: FlaskClient,
) -> None:
    """workflow_ids with one entry uses that id as the filename slug."""
    _login(client)
    resp = client.get("/api/catalog/export?format=yaml&workflow_ids=01-regulatory-compliance")
    assert resp.status_code == 200
    assert "reasonbook-catalog-01-regulatory-compliance-v1.0.yaml" in resp.headers["Content-Disposition"]


def test_catalog_export_silently_drops_unentitled_workflows(
    client: FlaskClient,
) -> None:
    """Unentitled or unknown workflow ids in workflow_ids drop silently —
    catalog is a discovery surface, partial views are expected. The 403
    path on /workflows/:id/schema/export remains the authoritative
    per-workflow gate."""
    _login(client)
    resp = client.get(
        "/api/catalog/export?format=json&workflow_ids=01-regulatory-compliance,99-fake,01-regulatory-compliance"
    )
    assert resp.status_code == 200
    import json

    body = json.loads(resp.data)
    workflow_ids = [w["workflow_id"] for w in body["catalog"]["workflows"]]
    assert workflow_ids == ["01-regulatory-compliance", "01-regulatory-compliance"]


def test_catalog_export_rejects_unknown_format(client: FlaskClient) -> None:
    _login(client)
    assert client.get("/api/catalog/export?format=xml").status_code == 400


def test_catalog_export_requires_auth(client: FlaskClient) -> None:
    assert client.get("/api/catalog/export?format=yaml").status_code == 401
