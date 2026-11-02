# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Smoke test for the health endpoint."""

from __future__ import annotations

from flask.testing import FlaskClient


def test_health_ok(client: FlaskClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body == {"status": "healthy", "version": "1.0.0"}
