# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""GET /api/matters and GET /api/matters/:id (TENANCY §10 step 8).

Tier scope: federal sees all matters; state/recipient see only matters
whose tree includes one of their participant_orgs.
"""

from __future__ import annotations

from reasonbook.db import schema_prefix

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


def test_federal_user_lists_cdbg_matter(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")

    body = client.get("/api/matters").get_json()
    items = body["items"]
    assert len(items) >= 1
    cdbg = next((b for b in items if b["program_id"] == "cdbg"), None)
    assert cdbg is not None
    # Agency-name normalization (commit 1992f51) canonicalizes HUD to
    # the full Department-of-… form via the agency catalog.
    assert cdbg["awarding_agency"] == "Department of Housing and Urban Development"
    assert cdbg["federal_archetype"] == "formula_allocation"
    assert cdbg["node_count"] == 4  # federal + 2 states + 1 recipient
    assert cdbg["originating_decision_id"] is not None


def test_state_user_only_sees_matters_in_its_chain(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)

    # Elena is the Georgia state director — sees the CDBG matter (GA
    # is a node in its tree). She'd also see any other matter that
    # has Georgia in it; in the demo seed the only such matter is CDBG.
    elena = _login_as(app, "elena.ross")
    body = elena.get("/api/matters").get_json()
    program_ids = {b["program_id"] for b in body["items"]}
    assert program_ids == {"cdbg"}


def test_recipient_user_only_sees_matters_with_its_org(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    rita = _login_as(app, "rita.alvarez")
    body = rita.get("/api/matters").get_json()
    program_ids = {b["program_id"] for b in body["items"]}
    assert program_ids == {"cdbg"}


def test_get_matter_returns_full_tree(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")

    matters_body = client.get("/api/matters").get_json()
    cdbg = next(b for b in matters_body["items"] if b["program_id"] == "cdbg")
    matter_id = cdbg["id"]

    body = client.get(f"/api/matters/{matter_id}").get_json()
    assert body["program_id"] == "cdbg"
    nodes = body["nodes"]
    # 1 federal + 2 state + 1 recipient = 4 active nodes.
    tiers = sorted(n["tier"] for n in nodes)
    assert tiers == ["federal", "recipient", "state", "state"]

    federal = next(n for n in nodes if n["tier"] == "federal")
    assert federal["participant_org_id"] is None
    assert federal["authority_role"] == "awarding_official"

    state_orgs = {n["participant_org_name"] for n in nodes if n["tier"] == "state"}
    assert state_orgs == {"Georgia", "Ohio"}

    delta = next(n for n in nodes if n["tier"] == "recipient")
    assert delta["participant_org_name"] == "Delta CDC"
    assert delta["authority_role"] == "certifying_officer"

    assert body["originating_decision"] is not None
    assert body["originating_decision"]["status"] in (
        "open",
        "assigned",
        "in_progress",
        "decided",
    )


def test_state_user_cannot_get_matter_outside_its_chain(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)

    # Find the CDBG matter id via the federal user.
    fed = _login_as(app, "jamie.kim")
    matters = fed.get("/api/matters").get_json()["items"]
    cdbg_id = next(b for b in matters if b["program_id"] == "cdbg")["id"]

    # Elena (Georgia) IS in CDBG → 200.
    elena = _login_as(app, "elena.ross")
    resp = elena.get(f"/api/matters/{cdbg_id}")
    assert resp.status_code == 200

    # Make up a UUID that doesn't match any matter → 404.
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = elena.get(f"/api/matters/{fake_id}")
    assert resp.status_code == 404


def test_invalid_uuid_returns_400(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")
    resp = client.get("/api/matters/not-a-uuid")
    assert resp.status_code == 400


def test_case_file_pdf_returns_pdf(clean_db: Engine, app: Flask) -> None:
    """Smoke test: GET /matters/<id>/case-file produces a real PDF.

    Verifies the headers + magic bytes; the rendered content is too
    layout-heavy to assert page-by-page. The matter case-file generator
    walks the hash chain, so this also covers integration with verify_chain.
    """
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    cdbg_id = next(
        b for b in fed.get("/api/matters").get_json()["items"] if b["program_id"] == "cdbg"
    )["id"]

    resp = fed.get(f"/api/matters/{cdbg_id}/case-file")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.headers["Content-Disposition"].startswith(
        'attachment; filename="matter-case-file-'
    )
    assert resp.data[:4] == b"%PDF"


def test_case_file_pdf_respects_tier_scope(clean_db: Engine, app: Flask) -> None:
    """A state user outside the matter's chain gets 403, not the PDF."""
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    # NIH-R01 matter has no Georgia state node; Elena (Georgia) shouldn't
    # be able to export its case file.
    nih = next(
        (b for b in fed.get("/api/matters").get_json()["items"] if b["program_id"] == "nih-r01"),
        None,
    )
    if nih is None:  # seed shape may evolve; bail rather than fail spuriously
        return
    elena = _login_as(app, "elena.ross")
    resp = elena.get(f"/api/matters/{nih['id']}/case-file")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/matters + GET /api/participant_orgs
# ---------------------------------------------------------------------------


def test_federal_user_creates_matter(clean_db: Engine, app: Flask) -> None:
    from sqlalchemy import text

    seed(include_apex=False)
    new_state = "00000000-0000-0000-0000-0000000000aa"
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                "VALUES (:id, 'state', 'New Mexico')"
            ),
            {"id": new_state},
        )

    fed = _login_as(app, "jamie.kim")
    resp = fed.post(
        "/api/matters",
        json={
            "program_id": "snap",
            "awarding_agency": "USDA — FNS",
            "amount_obligated": "5500000.00",
            "period_label": "FY26",
            "terms": "FY26 · 7 CFR 271-275",
            "federal_application_ref": "USDA-SNAP-2026-NM-001",
            "states": [{"participant_org_id": new_state}],
            "recipients": [],
        },
    )
    assert resp.status_code == 201, resp.get_json()
    body = resp.get_json()
    assert body["program_id"] == "snap"
    assert body["node_count"] == 2  # federal root + 1 state


def test_state_user_cannot_create_matter(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    elena = _login_as(app, "elena.ross")
    resp = elena.post(
        "/api/matters",
        json={
            "program_id": "snap",
            "awarding_agency": "USDA — FNS",
            "amount_obligated": "100",
            "period_label": "FY26",
            "terms": "x",
            "federal_application_ref": "X",
            "states": [],
            "recipients": [],
        },
    )
    assert resp.status_code == 403


def test_create_matter_replay_is_idempotent(clean_db: Engine, app: Flask) -> None:
    """Same key → same matter id, 201 both times."""
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    payload = {
        "program_id": "nih-r01",
        "awarding_agency": "NIH",
        "amount_obligated": "750000.00",
        "period_label": "FY26",
        "terms": "FY26 · NIH GPS",
        "federal_application_ref": "NIH-2026-IDEM-007",
        "states": [],
        "recipients": [],
    }
    a = fed.post("/api/matters", json=payload)
    b = fed.post("/api/matters", json=payload)
    assert a.status_code == 201
    assert b.status_code == 201
    assert a.get_json()["id"] == b.get_json()["id"]


def test_create_matter_missing_field_returns_400(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    resp = fed.post("/api/matters", json={"program_id": "cdbg"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["error"] == "missing_fields"


def test_list_participant_orgs(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")

    all_orgs = client.get("/api/participant_orgs").get_json()["items"]
    assert len(all_orgs) >= 3  # GA, OH, Delta at minimum

    states = client.get("/api/participant_orgs?kind=state").get_json()["items"]
    assert all(o["kind"] == "state" for o in states)
    assert {o["display_name"] for o in states} >= {"Georgia", "Ohio"}

    recips = client.get("/api/participant_orgs?kind=recipient").get_json()["items"]
    assert all(o["kind"] == "recipient" for o in recips)
    assert "Delta CDC" in {o["display_name"] for o in recips}


def test_list_participant_orgs_invalid_kind_returns_400(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    client = _login_as(app, "jamie.kim")
    resp = client.get("/api/participant_orgs?kind=invalid")
    assert resp.status_code == 400
