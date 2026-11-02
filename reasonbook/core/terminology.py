# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Vocabulary helpers — pre-archetype-model lookup surface.

WORKFLOW-MIGRATION Step 6: The credit-union ↔ community-bank vocabulary
mapping that lived here is retired. Federal programs each carry their
own ``vocabulary`` field in ``dp/config/programs/<program>.yaml`` —
NIH talks about Grant Applications, SNAP talks about Applications,
SSDI talks about Claims, and so on. That per-program dict is now the
authoritative substitution table.

For display-layer consumers (PDF renderers, email templates, narrative
voiceover scripts) the recommended call sequence is:

    from reasonbook.semantic.engine import get_engine
    program = get_engine().get_program(program_id)
    label = program.vocabulary.get(canonical_term, canonical_term)

This module remains as a passthrough shim so legacy call sites don't
hard-break during the transition. New code should reach for
``program.vocabulary`` directly.
"""

from __future__ import annotations


def get_term(term: str, institution_type: str = "") -> str:
    """Return ``term`` unchanged.

    Kept for source compatibility with legacy call sites. New code
    should resolve vocabulary off the program profile (see module
    docstring).
    """
    del institution_type
    return term


def get_terms(institution_type: str = "") -> dict[str, str]:
    """Return an empty mapping — the legacy CU↔bank dict is gone.

    Programs now carry their own ``vocabulary`` dicts; pull from there.
    """
    del institution_type
    return {}


__all__ = ["get_term", "get_terms"]
