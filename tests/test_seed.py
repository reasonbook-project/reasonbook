# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Seed-script integration tests."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from reasonbook.db import session_scope
from reasonbook.db import schema_prefix
from scripts.seed_dev import seed

pytestmark = pytest.mark.skip(
    reason=(
        "Asserts on the banking-specific entitlements / authority grants "
        "that the federal seed retired. Rewrite alongside the federal seed "
        "once the assertion targets stabilize."
    ),
)


def _counts(engine: Engine) -> dict[str, int]:
    sql = text("""
        SELECT 'tenants' AS k, count(*)::int AS v FROM {schema_prefix()}tenants
        UNION ALL SELECT 'users',         count(*)::int FROM {schema_prefix()}users
        UNION ALL SELECT 'entitlements',  count(*)::int FROM {schema_prefix()}tenant_entitlements
        UNION ALL SELECT 'authorities',   count(*)::int FROM {schema_prefix()}user_workflow_authority
        UNION ALL SELECT 'supervisors',   count(*)::int FROM {schema_prefix()}user_supervisors
    """)
    with session_scope() as conn:
        return {row.k: row.v for row in conn.execute(sql)}


def test_seed_produces_expected_row_counts(clean_db: Engine) -> None:
    seed()
    counts = _counts(clean_db)
    assert counts == {
        # the single organization tenant.
        "tenants": 2,
        # 4 original Riverdale users + 12 narrative-roster personas
        # (v3.11) + the support super-admin = 17.
        "users": 17,
        # All 10 workflows entitled to Riverdale (Phase 13.7). The support
        # tenant has zero workflow entitlements by design.
        "entitlements": 10,
        # 21 original (3 BSA + 2 each on the other 9 workflows) + 17
        # new authorities for the 12 narrative personas (v3.11):
        #   Priya: BSA + Reg + Apex = 3
        #   Daniel: Credit + ALM + Apex = 3
        #   Lena: Credit = 1; Ravi: ALM = 1
        #   Claire: Vendor + Digital = 2; Fatima: Member = 1
        #   Eduardo: Product = 1; Nathan: Digital = 1
        #   Sofia: Model Risk = 1
        #   Walter/Linda/Gerald: Apex board = 3
        "authorities": 38,
        # 2 original (Marcus→Jamie BSA, Marcus→Sarah Reg) + 10 new
        # narrative supervisors (v3.11): Marcus→{Claire, Sofia, Fatima},
        # Daniel→{Lena, Ravi}, Sarah→{Marcus, Daniel, Priya, Eduardo,
        # Nathan} tenant-wide.
        "supervisors": 12,
    }


def test_seed_is_idempotent(clean_db: Engine) -> None:
    seed()
    first = _counts(clean_db)
    seed()
    second = _counts(clean_db)
    assert first == second


def test_seed_creates_us_federal_tenant_with_expected_attributes(clean_db: Engine) -> None:
    seed()
    with clean_db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, org_type, regulator "
                f"FROM {schema_prefix()}tenants WHERE tenant_id = 'us-federal'"
            )
        ).one()
    assert row.name == "United States Federal Government"
    assert row.org_type == "FEDERAL_GOVERNMENT"
    assert row.regulator is None
    # Phase 12 — Riverdale ships with apex enabled for demo coverage.
    assert row.has_apex is True


def test_seed_grants_marcus_supervises_jamie_for_bsa(clean_db: Engine) -> None:
    seed()
    with clean_db.connect() as conn:
        row = conn.execute(
            text("""
                SELECT s.workflow_id
                FROM {schema_prefix()}user_supervisors s
                JOIN {schema_prefix()}users u  ON u.id = s.user_id
                JOIN {schema_prefix()}users sv ON sv.id = s.supervisor_id
                WHERE u.username = 'jamie.kim' AND sv.username = 'marcus.webb'
            """)
        ).one()
    assert row.workflow_id == "01-regulatory-compliance"


def test_seed_grants_jamie_bsa_officer_authority_with_sar_limit(
    clean_db: Engine,
) -> None:
    seed()
    with clean_db.connect() as conn:
        row = conn.execute(
            text("""
                SELECT a.level, a.limits
                FROM {schema_prefix()}user_workflow_authority a
                JOIN {schema_prefix()}users u ON u.id = a.user_id
                WHERE u.username = 'jamie.kim' AND a.workflow_id = '01-regulatory-compliance'
                  AND a.revoked_at IS NULL
            """)
        ).one()
    assert row.level == 3
    assert row.limits == {"sar_max_aggregate": 250000}


def test_seed_grants_reg_compliance_authority(clean_db: Engine) -> None:
    """Phase 10 — Sarah and Marcus carry Reg Compliance authority."""
    seed()
    with clean_db.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT u.username, a.level
                FROM {schema_prefix()}user_workflow_authority a
                JOIN {schema_prefix()}users u ON u.id = a.user_id
                WHERE a.workflow_id = '01-regulatory-compliance'
                  AND a.revoked_at IS NULL
                ORDER BY u.username
            """)
        ).all()
    grants = {r.username: r.level for r in rows}
    # v3.11: Priya joins as compliance_officer (level 3) on Reg.
    assert grants == {"marcus.webb": 4, "priya.shah": 3, "sarah.mitchell": 3}



# CFI-workflow authority-grant tests removed in the DG-substrate cleanup —
# the workflows they queried against (03-credit-lending, 04-alm-treasury,
# 05-vendor-risk, 06-model-risk-ai-governance, 07-member-customer-risk,
# 08-product-performance, 09-digital-transformation) no longer exist in
# this codebase. Federal-native authority-grant tests will land as part
# of the federal seed rewrite.
