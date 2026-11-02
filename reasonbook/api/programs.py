# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Program catalog endpoint — backs the Programs scope on /catalog.

Sister surface to ``/api/archetypes``. Returns the 7 program profiles
(Tier 3) with their declared profile metadata plus the matter-lifecycle
fields landed in the semantic-layer rewrite: definition_quality,
per-tier defaults, heartbeat thresholds.

Read-only. No tenant filtering applied — every tenant sees every
program. If we later need per-tenant program entitlement, it lives on
top of this read shape rather than collapsing into it.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify

from reasonbook.auth.decorators import require_auth
from reasonbook.semantic.engine import get_engine

bp = Blueprint("programs", __name__)


@bp.get("/programs")
@require_auth
def list_programs() -> tuple[Response, int]:
    """Return all 7 programs with rich metadata for the catalog."""
    engine = get_engine()
    items: list[dict[str, Any]] = []
    for program_id in engine.program_ids():
        prog = engine.get_program(program_id)
        archetype = engine.archetype_for_program(program_id)
        items.append(
            {
                "id": prog.profile.id,
                "name": prog.profile.name,
                "display_name": prog.profile.display_name,
                "awarding_agency": prog.profile.awarding_agency or prog.profile.agency,
                "federal_archetype": prog.profile.federal_archetype,
                "binds_archetype": prog.profile.binds_archetype,
                "binds_archetype_name": archetype.archetype.name,
                "definition_quality": prog.definition_quality,
                "defaults": {
                    "federal": {
                        "active_archetypes": prog.defaults.federal.active_archetypes,
                        "authority_role": prog.defaults.federal.authority_role,
                    },
                    "state": {
                        "active_archetypes": prog.defaults.state.active_archetypes,
                        "authority_role": prog.defaults.state.authority_role,
                    },
                    "recipient": {
                        "active_archetypes": prog.defaults.recipient.active_archetypes,
                        "authority_role": prog.defaults.recipient.authority_role,
                    },
                },
                "heartbeat": prog.heartbeat.model_dump(),
                "retention_months": prog.profile.retention_months,
            }
        )
    items.sort(key=lambda x: x["display_name"] or x["name"])
    return jsonify({"programs": items}), 200
