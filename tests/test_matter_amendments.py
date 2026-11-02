# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter amendments — TENANCY-MODEL §13.2 + §10 step 9.

State-tier amendments: add/remove recipient. Authorized for the parent
state's tier OR federal; everyone else gets 403. The unique partial
index blocks duplicate active nodes for the same (matter, org).
"""

from __future__ import annotations

from reasonbook.db import schema_prefix

import uuid

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from scripts.seed_dev import (
    _DELTA_RECIPIENT_ID,
    _GEORGIA_ORG_ID,
    _OHIO_ORG_ID,
    DEMO_PASSWORD,
    seed,
)


def _login_as(app: Flask, username: str) -> FlaskClient:
    client = app.test_client()
    resp = client.post(
        "/api/auth/login",
        json={"username": username, "password": DEMO_PASSWORD},
    )
    assert resp.status_code == 200, resp.get_json()
    return client


def _cdbg_matter_and_nodes(client: FlaskClient) -> dict:
    """Federal user fetches the CDBG matter + returns key node ids."""
    items = client.get("/api/matters").get_json()["items"]
    cdbg = next(b for b in items if b["program_id"] == "cdbg")
    detail = client.get(f"/api/matters/{cdbg['id']}").get_json()
    nodes = detail["nodes"]
    return {
        "matter_id": cdbg["id"],
        "ga_node_id": next(
            n["id"] for n in nodes
            if n["tier"] == "state" and n["participant_org_name"] == "Georgia"
        ),
        "oh_node_id": next(
            n["id"] for n in nodes
            if n["tier"] == "state" and n["participant_org_name"] == "Ohio"
        ),
        "delta_node_id": next(
            n["id"] for n in nodes
            if n["tier"] == "recipient" and n["participant_org_name"] == "Delta CDC"
        ),
    }


def _insert_new_recipient(clean_db: Engine, *, display_name: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                "VALUES (:id, 'recipient', :name)"
            ),
            {"id": org_id, "name": display_name},
        )
    return org_id


def test_state_user_can_add_recipient_under_own_state(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    new_recip = _insert_new_recipient(clean_db, display_name="Atlanta Housing Corp")

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")  # GA state director
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["ga_node_id"],
            "participant_org_id": str(new_recip),
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["tier"] == "recipient"
    assert body["participant_org_id"] == str(new_recip)
    assert body["authority_role"] == "certifying_officer"


def test_state_user_cannot_add_recipient_under_other_state(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    new_recip = _insert_new_recipient(clean_db, display_name="Cleveland Housing")

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")  # GA state director
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["oh_node_id"],  # OH, not GA
            "participant_org_id": str(new_recip),
        },
    )
    assert resp.status_code == 403


def test_recipient_user_cannot_amend(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    new_recip = _insert_new_recipient(clean_db, display_name="Sub-recipient")

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    rita = _login_as(app, "rita.alvarez")
    resp = rita.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["ga_node_id"],
            "participant_org_id": str(new_recip),
        },
    )
    assert resp.status_code == 403


def test_federal_can_add_recipient_under_any_state(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    new_recip = _insert_new_recipient(clean_db, display_name="Federal-Added Recipient")

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["oh_node_id"],  # OH; federal can do any
            "participant_org_id": str(new_recip),
        },
    )
    assert resp.status_code == 200


def test_duplicate_recipient_conflicts(clean_db: Engine, app: Flask) -> None:
    """Re-adding Delta CDC under Georgia (already there) → 409."""
    seed(include_apex=False)

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["ga_node_id"],
            "participant_org_id": str(_DELTA_RECIPIENT_ID),
        },
    )
    assert resp.status_code == 409


def test_remove_then_re_add_succeeds(clean_db: Engine, app: Flask) -> None:
    """Remove Delta, then add a new recipient at Delta's slot — works."""
    seed(include_apex=False)

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)
    elena = _login_as(app, "elena.ross")

    # Remove Delta first.
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={"type": "remove_recipient", "recipient_node_id": ctx["delta_node_id"]},
    )
    assert resp.status_code == 200
    assert resp.get_json()["removed_at"] is not None

    # Now add Delta back (the same org id) → succeeds because the unique
    # partial index only counts active rows.
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_recipient",
            "parent_state_node_id": ctx["ga_node_id"],
            "participant_org_id": str(_DELTA_RECIPIENT_ID),
        },
    )
    assert resp.status_code == 200, resp.get_json()


def test_oh_state_user_cannot_remove_ga_recipient(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    paul = _login_as(app, "paul.tate")  # OH director
    resp = paul.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={"type": "remove_recipient", "recipient_node_id": ctx["delta_node_id"]},
    )
    assert resp.status_code == 403
    # Avoid an unused-import lint warning while documenting the OH org
    # exists in the seed.
    assert isinstance(_OHIO_ORG_ID, uuid.UUID)
    assert isinstance(_GEORGIA_ORG_ID, uuid.UUID)


def test_invalid_amendment_type_returns_400(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={"type": "not_a_real_amendment"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Federal-only amendments (§13.2 follow-ups)
# ---------------------------------------------------------------------------


def test_federal_can_add_state(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    new_state_id = uuid.uuid4()
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                "VALUES (:id, 'state', 'Texas')"
            ),
            {"id": new_state_id},
        )

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_state",
            "participant_org_id": str(new_state_id),
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["tier"] == "state"
    assert body["authority_role"] == "state_program_director"


def test_state_user_cannot_add_state(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    new_state_id = uuid.uuid4()
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name) "
                "VALUES (:id, 'state', 'Florida')"
            ),
            {"id": new_state_id},
        )

    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "add_state",
            "participant_org_id": str(new_state_id),
        },
    )
    assert resp.status_code == 403


def test_federal_can_remove_state(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "remove_state",
            "state_node_id": ctx["oh_node_id"],
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["removed_at"] is not None


def test_state_user_cannot_remove_state(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "remove_state",
            "state_node_id": ctx["ga_node_id"],
        },
    )
    assert resp.status_code == 403


def test_federal_amends_state_active_archetypes(
    clean_db: Engine, app: Flask
) -> None:
    """Federal owns the 'change a state node's archetypes' amendment."""
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    new_list = ["formula_allocation", "modification"]
    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_archetypes",
            "node_id": ctx["ga_node_id"],
            "active_archetypes": new_list,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["tier"] == "state"
    assert sorted(body["active_archetypes"]) == sorted(new_list)
    # The original GA node should now be marked removed_at.
    detail = fed.get(f"/api/matters/{ctx['matter_id']}").get_json()
    historical_ids = {n["id"] for n in detail["historical_nodes"]}
    assert ctx["ga_node_id"] in historical_ids


def test_state_amends_recipient_active_archetypes(
    clean_db: Engine, app: Flask
) -> None:
    """State (parent's tier) owns the 'change a recipient's archetypes' amendment."""
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")
    new_list = ["payment_authorization"]
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_archetypes",
            "node_id": ctx["delta_node_id"],
            "active_archetypes": new_list,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["tier"] == "recipient"
    assert body["active_archetypes"] == new_list


def test_recipient_user_cannot_amend_archetypes(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    rita = _login_as(app, "rita.alvarez")
    resp = rita.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_archetypes",
            "node_id": ctx["delta_node_id"],
            "active_archetypes": ["payment_authorization"],
        },
    )
    assert resp.status_code == 403


def test_federal_amends_matter_fields(clean_db: Engine, app: Flask) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_matter_fields",
            "amount_obligated": "20000000.00",
            "terms": "FY26 · Uniform Guidance 2 CFR 200 · 84-month retention",
            "retention_months": 84,
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    changes = body["changes"]
    assert set(changes.keys()) == {"amount_obligated", "terms", "retention_months"}
    assert changes["retention_months"]["after"] == 84

    # Verify the matter GET reflects the change.
    detail = fed.get(f"/api/matters/{ctx['matter_id']}").get_json()
    assert detail["amount_obligated"] == "20000000.00"
    assert detail["retention_months"] == 84


def test_state_user_cannot_amend_matter_fields(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)

    elena = _login_as(app, "elena.ross")
    resp = elena.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_matter_fields",
            "amount_obligated": "1.00",
        },
    )
    assert resp.status_code == 403


def test_amend_matter_fields_noop_when_unchanged(
    clean_db: Engine, app: Flask
) -> None:
    seed(include_apex=False)
    fed = _login_as(app, "jamie.kim")
    ctx = _cdbg_matter_and_nodes(fed)
    detail = fed.get(f"/api/matters/{ctx['matter_id']}").get_json()

    # Submit the same values as already-set → no-op.
    resp = fed.post(
        f"/api/matters/{ctx['matter_id']}/amendments",
        json={
            "type": "amend_matter_fields",
            "amount_obligated": detail["amount_obligated"],
            "terms": detail["terms"],
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["changes"] == {}


@pytest.fixture(autouse=True)
def _engine_ready() -> None:
    from reasonbook.semantic.engine import init_engine

    init_engine()
