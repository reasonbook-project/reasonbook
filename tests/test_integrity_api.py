# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""API-level smoke tests for the integrity endpoints.

Chain-walk mechanics are exercised in tests/test_hash_chain.py; this
file covers the HTTP surface — the per-matter chain-query endpoint
that powers the Inspector's Integrity drawer.
"""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from scripts.seed_dev import DEMO_PASSWORD, seed


def _login_as(app: Flask, username: str) -> FlaskClient:
    client = app.test_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_json()
    return client


def test_matter_chain_returns_slice_and_verified(
    clean_db: Engine, app: Flask
) -> None:
    """Endpoint returns this matter's events, chain pointers, verified=true."""
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")

    # Pick any matter with events — the CDBG seed always has decision events.
    matters = client.get("/api/matters").get_json()["items"]
    matter = next(m for m in matters if m["program_id"] == "cdbg")

    resp = client.get(f"/api/integrity/matters/{matter['id']}/chain")
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()

    # Shape
    assert body["matter_id"] == matter["id"]
    assert body["genesis_hash"] == "0" * 64
    assert body["verified"] is True
    assert body["event_count"] >= 1
    assert len(body["events"]) == body["event_count"]

    # Head hash matches the last event's hash + prev pointer chains correctly
    events = body["events"]
    assert body["head_hash"] == events[-1]["hash"]
    assert body["prev_hash"] == events[-1]["prev_hash"]

    # Every event has the drawer-required fields
    for e in events:
        assert set(e) >= {
            "event_id", "ts", "action", "summary",
            "hash", "prev_hash",
        }
        assert len(e["hash"]) == 64
        # prev_hash is 64 chars for non-genesis, empty string for the
        # very first global event
        assert len(e["prev_hash"]) in (0, 64)
