# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Programs YAML registry round-trip (TENANCY-MODEL §10 step 4).

Each program YAML declares per-tier defaults (active_archetypes +
authority_role) per §11.2. The SemanticEngine exposes them via
``defaults_for(program_id)`` so the matter-create transaction (step 5)
can pre-fill the decision-rights table for each new node.

These tests assert the wire-up is sound: every shipped program loads,
each carries a defaults block, and the federal/state/recipient
authority roles are drawn from the closed v1 enum.
"""

from __future__ import annotations

import pytest

from reasonbook.semantic.engine import get_engine, init_engine


@pytest.fixture(autouse=True)
def _ensure_engine() -> None:
    """init_engine() is idempotent; call before each test in case other
    test modules left the singleton uninitialised."""
    init_engine()

# Closed enum per project_tenancy_model memory + TENANCY-MODEL §11.3.
V1_AUTHORITY_ROLES = {
    "awarding_official",
    "state_program_director",
    "certifying_officer",
}

# Programs shipped today. Adding a program means extending this list
# AND its YAML; both happen in the same change so the assertion stays
# honest. Order doesn't matter — set comparison below.
SHIPPED_PROGRAMS = {
    "cdbg",
    "grant-debarment",
    "nih-no-cost-extension",
    "nih-r01",
    "snap",
    "ssdi-cdr",
    "treasury-disbursement",
}


def test_engine_exposes_all_shipped_programs() -> None:
    engine = get_engine()
    loaded = {p.profile.id for p in engine._programs.values()}  # noqa: SLF001
    assert SHIPPED_PROGRAMS.issubset(loaded), (
        f"missing programs: {SHIPPED_PROGRAMS - loaded}"
    )


@pytest.mark.parametrize("program_id", sorted(SHIPPED_PROGRAMS))
def test_program_defaults_round_trip(program_id: str) -> None:
    defaults = get_engine().defaults_for(program_id)

    # Federal tier: every program must declare a federal_archetype + role.
    assert defaults.federal.active_archetypes, (
        f"{program_id}: federal.active_archetypes is empty"
    )
    assert defaults.federal.authority_role in V1_AUTHORITY_ROLES, (
        f"{program_id}: federal.authority_role={defaults.federal.authority_role} "
        f"not in v1 enum {V1_AUTHORITY_ROLES}"
    )

    # State + recipient tiers: optional but if declared must use v1 enum.
    for tier_name, tier in (("state", defaults.state), ("recipient", defaults.recipient)):
        if tier.authority_role is not None:
            assert tier.authority_role in V1_AUTHORITY_ROLES, (
                f"{program_id}: {tier_name}.authority_role={tier.authority_role} "
                f"not in v1 enum {V1_AUTHORITY_ROLES}"
            )


def test_cdbg_defaults_match_tenancy_spec() -> None:
    """The CDBG defaults are the worked example in TENANCY-MODEL §11.2.

    If this test fails the spec example and the shipped YAML have
    diverged — figure out which one is right before suppressing it.
    """
    defaults = get_engine().defaults_for("cdbg")

    assert defaults.federal.active_archetypes == ["formula_allocation"]
    assert defaults.federal.authority_role == "awarding_official"

    assert set(defaults.state.active_archetypes) == {
        "formula_allocation",
        "eligibility_determination",
        "recertification",
        "modification",
    }
    assert defaults.state.authority_role == "state_program_director"

    assert set(defaults.recipient.active_archetypes) == {
        "payment_authorization",
        "eligibility_determination",
        "adverse_action",
    }
    assert defaults.recipient.authority_role == "certifying_officer"
