# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for the (now passthrough) terminology shim.

WORKFLOW-MIGRATION Step 6 retired the CU ↔ community-bank vocabulary
mapping that used to live in ``reasonbook.core.terminology``. The module
remains as a passthrough so legacy call sites compile, but the
authoritative substitution table is now ``program.vocabulary`` on the
loaded ``reasonbook.semantic.archetype.Program``.

These tests pin the passthrough behavior so a future revival of the
old mapping is a deliberate choice, not an accidental regression.
"""

from __future__ import annotations

import pytest

from reasonbook.core.terminology import get_term, get_terms


@pytest.mark.parametrize(
    "term",
    [
        "Member",
        "Members",
        "Credit Union",
        "Shares",
        "NCUA",
        "MEM-",
        "anything else",
        "",
    ],
)
def test_get_term_is_passthrough(term: str) -> None:
    assert get_term(term) == term
    assert get_term(term, "credit_union") == term
    assert get_term(term, "community_bank") == term
    assert get_term(term, "anything") == term


def test_get_terms_returns_empty_mapping() -> None:
    """The CU↔bank dict is gone; programs carry their own vocabulary."""
    assert get_terms() == {}
    assert get_terms("credit_union") == {}
    assert get_terms("community_bank") == {}
