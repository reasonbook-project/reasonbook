# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Archetype catalog endpoint — backs the Caseload rail.

Per WORKFLOW-MIGRATION.md Step 8: the rail's "Caseload" section
renders the 7 archetypes in a fixed order. This endpoint returns a
flat list of archetype summaries; the frontend renders them with the
same row primitive that used to render the legacy entitled-workflow
list.

Per-tenant filtering is intentionally not applied yet — every tenant
sees every archetype. If we later need per-tenant archetype
entitlement (e.g. an SSA-only deployment shouldn't see
``competitive_award``), it lives on top of this read shape rather
than collapsing into it.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify

from reasonbook.auth.decorators import require_auth
from reasonbook.semantic.engine import get_engine

bp = Blueprint("archetypes", __name__)

# Display order locked to WORKFLOW-MIGRATION.md §"Wire the 7 to the nav
# 'Caseload' order". Position numbers (01-07) flow into the rail row's
# secondary text the same way legacy workflows surfaced 01-10.
_CASELOAD_ORDER: tuple[str, ...] = (
    "competitive_award",
    "formula_allocation",
    "eligibility_determination",
    "recertification",
    "modification",
    "adverse_action",
    "payment_authorization",
)


@bp.get("/archetypes")
@require_auth
def list_archetypes() -> tuple[Response, int]:
    """Return the 7 archetypes in Caseload order with summary metadata."""
    engine = get_engine()
    out: list[dict[str, Any]] = []
    for position, archetype_id in enumerate(_CASELOAD_ORDER, start=1):
        try:
            arch = engine.get_archetype(archetype_id)
        except KeyError:
            # An archetype dropped out of the corpus would only happen if
            # someone edited dp/config/archetypes/ without re-running
            # tests. Skip silently here; the boot-time loader would have
            # already failed loud if the corpus was malformed.
            continue
        out.append(
            {
                "id": arch.archetype.id,
                "name": arch.archetype.name,
                "description": arch.archetype.description,
                "family": list(arch.archetype.family),
                "flow": arch.archetype.flow,
                "decision_basis": arch.archetype.decision_basis,
                "promotes": arch.archetype.promotes,
                # Position drives the rail's display order + the "01..07"
                # mono-eyebrow numbers that mirror the legacy workflow rail.
                "position": position,
            }
        )
    return jsonify({"archetypes": out}), 200
