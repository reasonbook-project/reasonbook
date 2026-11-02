# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tenancy model — matter aggregate + tier columns.

Covers migration 0039 (TENANCY-MODEL.md §10 step 1):

- All three new tables exist with the right columns
- New columns on users + decisions exist
- CHECK constraints enforce the federal-root invariants
- Unique partial index allows multiple historical rows but one active
- GIN index on decisions.fund_flow_path exists
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from reasonbook.db import schema_prefix
from reasonbook.config import get_settings

import uuid

import psycopg
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def test_tenancy_tables_exist(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    tables = set(inspector.get_table_names(schema=get_settings().db_schema))
    assert "participant_orgs" in tables
    assert "matters" in tables
    assert "matter_nodes" in tables


def test_users_have_tier_columns(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    cols = {c["name"] for c in inspector.get_columns("users", schema=get_settings().db_schema)}
    assert "tier" in cols
    assert "participant_org_id" in cols


def test_decisions_have_matter_columns(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    cols = {c["name"] for c in inspector.get_columns("decisions", schema=get_settings().db_schema)}
    assert "matter_id" in cols
    assert "matter_node_id" in cols
    assert "fund_flow_path" in cols


def test_fund_flow_path_has_gin_index(clean_db: Engine) -> None:
    """apply_tier_scope (step 3) relies on GIN-indexed ANY() lookups.

    PostgreSQL-only: fund_flow_path is a JSON column (no GIN index) on
    SQLite, and pg_indexes is a PostgreSQL catalog.
    """
    import pytest

    if not get_settings().is_postgres:
        pytest.skip("GIN index / pg_indexes is PostgreSQL-only")
    with clean_db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname='platform' "
                "AND indexname='ix_decisions_fund_flow_path'"
            )
        ).fetchone()
    assert row is not None, "fund_flow_path GIN index missing"
    assert "using gin" in row[0].lower()


def test_user_tier_check_federal_must_be_null_org(clean_db: Engine) -> None:
    """A federal user with a participant_org_id violates the CHECK."""
    state_org_id = _insert_state_org(clean_db, "Georgia", code="GA")

    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) "
                    "VALUES ('fed-tenant', 'Federal')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}users "
                    "(id, tenant_id, username, email, password_hash, name, role, "
                    " tier, participant_org_id) "
                    "VALUES (gen_random_uuid(), 'fed-tenant', 'bad-fed', "
                    "'bad-fed@example.com', 'x', 'Bad Fed', 'member', "
                    "'federal', :org)"
                ),
                {"org": state_org_id},
            )
    except IntegrityError:
        raised = True
    except Exception:
        raised = True
    assert raised, "expected CHECK violation: federal tier with participant_org_id"


def test_user_tier_check_state_must_have_org(clean_db: Engine) -> None:
    """A state/recipient user with NULL participant_org_id violates the CHECK."""
    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) "
                    "VALUES ('s-tenant', 'State')"
                )
            )
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}users "
                    "(id, tenant_id, username, email, password_hash, name, role, tier) "
                    "VALUES (gen_random_uuid(), 's-tenant', 'bad-state', "
                    "'bad-state@example.com', 'x', 'Bad State', 'member', 'state')"
                )
            )
    except IntegrityError:
        raised = True
    except Exception:
        raised = True
    assert raised, "expected CHECK violation: state tier without participant_org_id"


def test_matter_node_federal_root_invariant(clean_db: Engine) -> None:
    """A federal-tier node with a participant_org_id violates the CHECK."""
    matter_id, federal_user_id = _seed_matter_skeleton(clean_db)
    state_org_id = _insert_state_org(clean_db, "Georgia", code="GA")

    # Federal-root with participant_org_id set → violates ck_..._federal_root.
    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}matter_nodes "
                    "(id, matter_id, parent_node_id, tier, participant_org_id, "
                    " active_archetypes, authority_role, added_by_user_id) "
                    "VALUES (gen_random_uuid(), :matter, NULL, 'federal', :org, "
                    "'[\"competitive_award\"]', 'awarding_official', :user)"
                ),
                {"matter": matter_id, "org": state_org_id, "user": federal_user_id},
            )
    except IntegrityError:
        raised = True
    except Exception:
        raised = True
    assert raised, "expected CHECK violation: federal node with participant_org_id"


def test_matter_node_state_must_have_parent_and_org(clean_db: Engine) -> None:
    matter_id, federal_user_id = _seed_matter_skeleton(clean_db)

    # State node with NULL participant_org_id → CHECK violation.
    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}matter_nodes "
                    "(id, matter_id, parent_node_id, tier, participant_org_id, "
                    " active_archetypes, authority_role, added_by_user_id) "
                    "VALUES (gen_random_uuid(), :matter, gen_random_uuid(), "
                    "'state', NULL, '[]', 'state_program_director', :user)"
                ),
                {"matter": matter_id, "user": federal_user_id},
            )
    except IntegrityError:
        raised = True
    except Exception:
        raised = True
    assert raised, "expected CHECK violation: state node without participant_org_id"


def test_matter_node_unique_active_per_participant(clean_db: Engine) -> None:
    """One active row per (matter, participant_org); historical rows OK."""
    matter_id, federal_user_id = _seed_matter_skeleton(clean_db)
    state_org_id = _insert_state_org(clean_db, "Georgia", code="GA")

    # Insert a federal root and a state node.
    federal_root_id = uuid.uuid4()
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}matter_nodes "
                "(id, matter_id, parent_node_id, tier, participant_org_id, "
                " active_archetypes, authority_role, added_by_user_id) "
                "VALUES (:id, :matter, NULL, 'federal', NULL, "
                "'[\"competitive_award\"]', 'awarding_official', :user)"
            ),
            {"id": federal_root_id, "matter": matter_id, "user": federal_user_id},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}matter_nodes "
                "(id, matter_id, parent_node_id, tier, participant_org_id, "
                " active_archetypes, authority_role, added_by_user_id) "
                "VALUES (gen_random_uuid(), :matter, :parent, 'state', :org, "
                "'[\"formula_allocation\"]', "
                "'state_program_director', :user)"
            ),
            {
                "matter": matter_id,
                "parent": federal_root_id,
                "org": state_org_id,
                "user": federal_user_id,
            },
        )

    # A second ACTIVE state node for the same (matter, org) must fail.
    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {schema_prefix()}matter_nodes "
                    "(id, matter_id, parent_node_id, tier, participant_org_id, "
                    " active_archetypes, authority_role, added_by_user_id) "
                    "VALUES (gen_random_uuid(), :matter, :parent, 'state', :org, "
                    "'[\"formula_allocation\"]', "
                    "'state_program_director', :user)"
                ),
                {
                    "matter": matter_id,
                    "parent": federal_root_id,
                    "org": state_org_id,
                    "user": federal_user_id,
                },
            )
    except IntegrityError:
        raised = True
    except Exception:
        raised = True
    assert raised, "expected unique-violation on second active node for same org"

    # But: marking the first one removed_at THEN inserting a replacement
    # must succeed — append-only amendments.
    with clean_db.begin() as conn:
        conn.execute(
            text(
                f"UPDATE {schema_prefix()}matter_nodes SET removed_at = CURRENT_TIMESTAMP "
                "WHERE matter_id = :matter AND participant_org_id = :org "
                "AND removed_at IS NULL"
            ),
            {"matter": matter_id, "org": state_org_id},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}matter_nodes "
                "(id, matter_id, parent_node_id, tier, participant_org_id, "
                " active_archetypes, authority_role, added_by_user_id) "
                "VALUES (gen_random_uuid(), :matter, :parent, 'state', :org, "
                "'[\"formula_allocation\",\"modification\"]', "
                "'state_program_director', :user)"
            ),
            {
                "matter": matter_id,
                "parent": federal_root_id,
                "org": state_org_id,
                "user": federal_user_id,
            },
        )

    # Now there should be exactly 1 active row and 1 historical row.
    with clean_db.connect() as conn:
        active = conn.execute(
            text(
                f"SELECT count(*) FROM {schema_prefix()}matter_nodes "
                "WHERE matter_id = :matter AND participant_org_id = :org "
                "AND removed_at IS NULL"
            ),
            {"matter": matter_id, "org": state_org_id},
        ).scalar_one()
        historical = conn.execute(
            text(
                f"SELECT count(*) FROM {schema_prefix()}matter_nodes "
                "WHERE matter_id = :matter AND participant_org_id = :org "
                "AND removed_at IS NOT NULL"
            ),
            {"matter": matter_id, "org": state_org_id},
        ).scalar_one()
    assert active == 1
    assert historical == 1


def test_orm_round_trip(clean_db: Engine) -> None:
    """The SQLAlchemy models round-trip the canonical CDBG-shape skeleton."""
    from sqlalchemy.orm import Session

    from reasonbook.models import Matter, MatterNode, ParticipantOrg, Tenant, User

    with Session(clean_db) as s:
        s.add(Tenant(tenant_id="rt-tenant", name="Federal Govt"))
        s.flush()
        fed_user = User(
            tenant_id="rt-tenant",
            username="rt-fed",
            email="rt-fed@example.com",
            password_hash="x",
            name="Round-Trip Fed",
            role="member",
            tier="federal",
        )
        s.add(fed_user)
        s.flush()

        georgia = ParticipantOrg(kind="state", display_name="Georgia", code="GA")
        s.add(georgia)
        s.flush()

        matter = Matter(
            program_id="CDBG",
            federal_archetype="formula_allocation",
            awarding_agency="HUD",
            amount_obligated=1_200_000,
            period_label="FY26",
            terms="Uniform Guidance 2 CFR 200",
            retention_months=60,
            created_by_user_id=fed_user.id,
        )
        s.add(matter)
        s.flush()

        federal_root = MatterNode(
            matter_id=matter.id,
            parent_node_id=None,
            tier="federal",
            participant_org_id=None,
            active_archetypes=["formula_allocation"],
            authority_role="awarding_official",
            added_by_user_id=fed_user.id,
        )
        s.add(federal_root)
        s.flush()

        state_node = MatterNode(
            matter_id=matter.id,
            parent_node_id=federal_root.id,
            tier="state",
            participant_org_id=georgia.id,
            active_archetypes=["formula_allocation", "recertification"],
            authority_role="state_program_director",
            added_by_user_id=fed_user.id,
        )
        s.add(state_node)
        s.commit()

        # Read back: there's one matter with two nodes.
        nodes = s.query(MatterNode).filter(
            MatterNode.matter_id == matter.id
        ).order_by(MatterNode.tier).all()
        assert [n.tier for n in nodes] == ["federal", "state"]
        assert nodes[1].active_archetypes == [
            "formula_allocation",
            "recertification",
        ]
        # federal root has no parent or participant_org.
        assert nodes[0].parent_node_id is None
        assert nodes[0].participant_org_id is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_state_org(engine: Engine, name: str, *, code: str | None = None) -> uuid.UUID:
    org_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}participant_orgs (id, kind, display_name, code) "
                "VALUES (:id, 'state', :name, :code)"
            ),
            {"id": org_id, "name": name, "code": code},
        )
    return org_id


def _seed_matter_skeleton(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a federal tenant + user + bare Matter; return (matter_id, user_id)."""
    matter_id = uuid.uuid4()
    user_id = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}tenants (tenant_id, name) "
                "VALUES ('sk-tenant', 'Federal') ON CONFLICT DO NOTHING"
            )
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, tier) "
                "VALUES (:id, 'sk-tenant', :uname, :email, 'x', 'Skel User', "
                "'member', 'federal')"
            ),
            {
                "id": user_id,
                "uname": f"sk-{user_id.hex[:8]}",
                "email": f"sk-{user_id.hex[:8]}@example.com",
            },
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}matters "
                "(id, program_id, federal_archetype, awarding_agency, "
                " created_by_user_id) "
                "VALUES (:id, 'CDBG', 'formula_allocation', 'HUD', :user)"
            ),
            {"id": matter_id, "user": user_id},
        )
    return matter_id, user_id
