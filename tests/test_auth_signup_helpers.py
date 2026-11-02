# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for ``reasonbook/auth/signup.py`` — slug generation + reserved blocklist."""

from __future__ import annotations

import re

import pytest

from reasonbook.auth.signup import (
    RESERVED_TENANT_IDS,
    SLUG_MAX_LENGTH,
    SUFFIX_LENGTH,
    ReservedSlugError,
    generate_tenant_id,
    slugify,
)

# ---------------------------------------------------------------------------
# slugify()
# ---------------------------------------------------------------------------


def test_slugify_simple_lowercases_and_hyphenates() -> None:
    assert slugify("Acme Credit Union") == "acme-credit-union"


def test_slugify_collapses_multiple_spaces() -> None:
    assert slugify("Acme   Credit  Union") == "acme-credit-union"


def test_slugify_collapses_punctuation() -> None:
    assert slugify("Acme, Credit & Union, Inc.") == "acme-credit-union-inc"


def test_slugify_drops_accents() -> None:
    assert slugify("Crédit Mutuel") == "credit-mutuel"


def test_slugify_drops_unicode() -> None:
    assert slugify("中国银行") == ""


def test_slugify_trims_hyphens() -> None:
    assert slugify("---Acme---") == "acme"


def test_slugify_empty_input_returns_empty() -> None:
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("---") == ""


# ---------------------------------------------------------------------------
# generate_tenant_id()
# ---------------------------------------------------------------------------


def test_generate_tenant_id_format() -> None:
    tid = generate_tenant_id("Acme Credit Union")
    # Format: {slug}-{6-char-suffix}
    pattern = re.compile(r"^[a-z0-9-]+-[a-f0-9]{6}$")
    assert pattern.match(tid), f"tenant_id {tid!r} doesn't match expected format"
    assert tid.startswith("acme-credit-union-")


def test_generate_tenant_id_fits_varchar_50() -> None:
    long_name = "A" * 100
    tid = generate_tenant_id(long_name)
    assert len(tid) <= 50, f"tenant_id {tid!r} exceeds VARCHAR(50)"


def test_generate_tenant_id_unique_suffix() -> None:
    """Two calls with the same institution_name produce different tenant_ids."""
    a = generate_tenant_id("Acme CU")
    b = generate_tenant_id("Acme CU")
    assert a != b
    assert a.split("-")[:-1] == b.split("-")[:-1]  # same slug, different suffix


def test_generate_tenant_id_handles_empty_input() -> None:
    """Defensive: empty institution_name resolves to a usable tenant_id, not crash."""
    tid = generate_tenant_id("")
    assert tid.startswith("tenant-")
    assert len(tid.split("-")) == 2  # 'tenant' + 6-char suffix


def test_generate_tenant_id_reserved_blocklist() -> None:
    """Institution names that resolve to reserved slugs raise ReservedSlugError."""
    for reserved in ["admin", "ADMIN", "Admin", "support", "API"]:
        with pytest.raises(ReservedSlugError):
            generate_tenant_id(reserved)


def test_generate_tenant_id_reserved_with_decoration_still_unique_slug() -> None:
    """`Admin Inc` slugifies to `admin-inc` which is NOT reserved — should pass."""
    tid = generate_tenant_id("Admin Inc")
    assert tid.startswith("admin-inc-")


def test_reserved_blocklist_includes_demo_tenants() -> None:
    """Sanity: at minimum these names must be in the blocklist."""
    for name in ["us-federal", "admin", "support"]:
        assert name in RESERVED_TENANT_IDS


def test_slug_length_constants() -> None:
    """Constants sized so {slug:43}-{suffix:6} = 50 chars total = VARCHAR(50)."""
    assert SLUG_MAX_LENGTH + 1 + SUFFIX_LENGTH == 50  # +1 for the separator hyphen
