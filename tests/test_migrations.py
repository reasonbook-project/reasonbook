# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Migration up/down round-trip tests.

These hit a live Postgres on the URL in DATABASE_URL (or the docker-compose
default). Skipped when Postgres is unreachable.
"""

from __future__ import annotations

from reasonbook.db import schema_prefix
from reasonbook.config import get_settings

import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

EXPECTED_TABLES = {
    "users",
    "user_audit",
    "tenants",
    "decisions",
    "decision_events",
    "decision_attachments",
    "decision_types",
    # Renamed in migration 0046 (DP tenancy clarification).
    "agency_semantic_overrides",
    "user_workflow_authority",
    "user_supervisors",
    "oversight_evidence_links",
    # Tenancy model — migration 0039
    "participant_orgs",
    "matters",
    "matter_nodes",
    # Agency-scope substrate — migration 0046
    "agencies",
    "user_agency_scopes",
}


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def test_upgrade_head_creates_all_tables(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    tables = set(inspector.get_table_names(schema=get_settings().db_schema))
    assert EXPECTED_TABLES.issubset(tables), f"missing: {EXPECTED_TABLES - tables}"


def test_downgrade_base_drops_all_tables(clean_db: Engine) -> None:
    # Truncate decision_types first — the 0012 → 0011 downgrade re-narrows the
    # priority CHECK constraint and any 'critical' rows would block it.
    with clean_db.begin() as conn:
        conn.execute(text(f"DELETE FROM {schema_prefix()}decision_types CASCADE"))
        conn.execute(text(f"DELETE FROM {schema_prefix()}decisions CASCADE"))

    cfg = _alembic_config()
    command.downgrade(cfg, "base")
    inspector = inspect(clean_db)
    tables = set(inspector.get_table_names(schema=get_settings().db_schema))
    assert tables.isdisjoint(EXPECTED_TABLES), (
        f"unexpected leftover tables: {tables & EXPECTED_TABLES}"
    )
    # Restore for subsequent tests in the session.
    command.upgrade(cfg, "head")


def test_decision_events_has_workflow_id(clean_db: Engine) -> None:
    """Schema doc §3.5 requires workflow_id on decision_events."""
    inspector = inspect(clean_db)
    cols = {c["name"] for c in inspector.get_columns("decision_events", schema=get_settings().db_schema)}
    assert "workflow_id" in cols
    assert "tenant_id" in cols


def test_decisions_has_five_stage_anatomy_columns(clean_db: Engine) -> None:
    """Schema doc §3.4 — verify the new stage-specific columns exist."""
    inspector = inspect(clean_db)
    cols = {c["name"] for c in inspector.get_columns("decisions", schema=get_settings().db_schema)}
    expected = {
        "signal_captured_at",
        "signal_source",
        "signal_summary",
        "owner_authority_level",
        "escalation_path",
        "selected_option",
        "alternatives",
        "evidence_refs",
        "rationale",
        "action_started_at",
        "action_completed_at",
        "action_artifacts",
        "outcome_recorded_at",
        "decision_payload",
    }
    missing = expected - cols
    assert not missing, f"missing columns on decisions: {missing}"


def test_tenant_entitlements_active_uniqueness(clean_db: Engine) -> None:
    """A tenant may have at most one active entitlement per workflow."""
    with clean_db.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type)
                VALUES ('uniq', 'Test', 'CREDIT_UNION')
            """)
        )
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}tenant_entitlements
                  (id, tenant_id, workflow_id, status, started_at)
                VALUES
                  (gen_random_uuid(), 'uniq', '01-regulatory-compliance', 'active', CURRENT_TIMESTAMP)
            """)
        )

    # Second active row for the same (tenant, workflow) must fail.
    import psycopg

    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO {schema_prefix()}tenant_entitlements
                      (id, tenant_id, workflow_id, status, started_at)
                    VALUES
                      (gen_random_uuid(), 'uniq', '01-regulatory-compliance', 'active', CURRENT_TIMESTAMP)
                """)
            )
    except (psycopg.errors.UniqueViolation, Exception):
        raised = True
    assert raised, "expected unique-violation on duplicate active entitlement"


def test_user_supervisor_self_blocked(clean_db: Engine) -> None:
    """A user cannot be their own supervisor (CHECK constraint)."""
    with clean_db.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type)
                VALUES ('selftest', 'Self Test', 'CREDIT_UNION')
            """)
        )
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}users (id, tenant_id, username, email,
                  password_hash, name, role, status)
                VALUES (gen_random_uuid(), 'selftest', 'lonely', 'l@x.com',
                  'x', 'Lonely', 'member', 'active')
            """)
        )
        uid = conn.execute(
            text(f"SELECT id FROM {schema_prefix()}users WHERE username='lonely'")
        ).scalar_one()

    raised = False
    try:
        with clean_db.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO {schema_prefix()}user_supervisors
                      (id, tenant_id, user_id, supervisor_id)
                    VALUES (gen_random_uuid(), 'selftest', :uid, :uid)
                """),
                {"uid": uid},
            )
    except Exception:
        raised = True
    assert raised, "expected check-violation on self-supervisor"
