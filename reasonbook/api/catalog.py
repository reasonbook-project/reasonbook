# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Semantic Catalog — unified entry stream over the semantic layer.

Per docs/architecture/backlog/01_semantic_layer/DESIGN-SPEC-semantic-catalog.md.
One ``GET /api/catalog/entries`` endpoint returns every catalog-eligible
entry (metric, alert, persona, decision_type, archetype, program)
flattened into one shape with the catalog facets attached:

  who_watches | tier | domain | meaning | why_it_matters | owner |
  plain_thresholds | severity | direction | technical { id, unit, format }

The frontend renders three view modes (cards grouped by who_watches,
cards grouped by type, reference) over the same dataset; facets narrow
the result set in every mode.

Read-only; no tenant filtering applied. If we later need per-tenant
visibility, it lives on top of this read shape rather than collapsing
into it.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import or_, select

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.models import AgencyCatalog
from reasonbook.semantic.archetype import Archetype, Program
from reasonbook.semantic.engine import get_engine
from reasonbook.semantic.schema import (
    AlertCategory,
    DecisionType,
    Metric,
    Persona,
    WorkflowConfig,
)

bp = Blueprint("catalog", __name__)

# Default facet values applied when an entry doesn't declare its own.
# Oversight-workflow entries are agency-level by default; archetype and
# program entries get neutral defaults per the architecture.
_OVERSIGHT_DEFAULTS = {
    "who_watches": "agency_head",
    "tier": "federal",
    "domain": "governance",
}


@bp.get("/catalog/entries")
@require_auth
def list_entries() -> tuple[Response, int]:
    """Return every catalog entry across workflows + archetypes + programs."""
    engine = get_engine()
    entries: list[dict[str, Any]] = []

    # Workflow-derived entries (the legacy WorkflowConfig surface — apex
    # the only consumer post-pivot). Each metric / alert / persona /
    # decision_type becomes one entry with its workflow tagged on.
    for workflow_id in engine.workflow_ids():
        cfg = engine.get_config(workflow_id)
        entries.extend(_workflow_entries(cfg))

    # Archetype-derived entries — one entry per archetype, tagged with
    # its family / flow / decision_basis / promotes.
    for archetype_id in engine.archetype_ids():
        entries.append(_archetype_entry(engine.get_archetype(archetype_id)))

    # Program-derived entries — one entry per program, tagged with its
    # bound archetype + definition_quality + heartbeat shape.
    for program_id in engine.program_ids():
        entries.append(_program_entry(engine.get_program(program_id)))

    return jsonify({"entries": entries, "count": len(entries)}), 200


@bp.get("/catalog/agencies")
@require_auth
def list_agencies() -> tuple[Response, int]:
    """Federal agency typeahead for the matter-create drawer.

    Optional ``?q=`` substring match on display_name (case-insensitive).
    Empty / missing q returns all agencies (currently 111 from the
    USAspending demo pull — small enough to ship in one response).
    Forward-compatible with the eventual real connector (P25): when the
    catalog grows or stream-updates from the connector, we can paginate
    here without breaking the consumer.
    """
    q = (request.args.get("q") or "").strip()
    with session_scope() as s:
        stmt = select(AgencyCatalog).order_by(AgencyCatalog.display_name)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(
                    AgencyCatalog.display_name.ilike(like),
                    AgencyCatalog.slug.ilike(like),
                )
            )
        rows = s.execute(stmt).scalars().all()
        payload = [
            {
                "id": str(row.id),
                "slug": row.slug,
                "display_name": row.display_name,
                "source": row.source,
            }
            for row in rows
        ]
    return jsonify({"agencies": payload, "count": len(payload)}), 200


def _workflow_entries(cfg: WorkflowConfig) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    wf_id = cfg.workflow.id
    wf_name = cfg.workflow.full_name or cfg.workflow.name
    for m in cfg.metrics:
        out.append(_metric_entry(m, wf_id, wf_name))
    for a in cfg.alert_categories:
        out.append(_alert_entry(a, wf_id, wf_name))
    for p in cfg.personas:
        out.append(_persona_entry(p, wf_id, wf_name))
    for d in cfg.decision_types:
        out.append(_decision_type_entry(d, wf_id, wf_name))
    return out


def _facet_defaults(domain_fallback: str | None) -> dict[str, str]:
    return {
        "who_watches": _OVERSIGHT_DEFAULTS["who_watches"],
        "tier": _OVERSIGHT_DEFAULTS["tier"],
        "domain": domain_fallback or _OVERSIGHT_DEFAULTS["domain"],
    }


def _metric_entry(m: Metric, wf_id: str, wf_name: str) -> dict[str, Any]:
    defaults = _facet_defaults(m.domain)
    return {
        "type": "metric",
        "id": m.id,
        "name": m.name,
        "meaning": m.meaning or m.description,
        "why_it_matters": m.why_it_matters,
        "owner": m.owner,
        "who_watches": m.who_watches or defaults["who_watches"],
        "tier": m.tier or defaults["tier"],
        "domain": m.domain or defaults["domain"],
        "workflow_id": wf_id,
        "workflow_name": wf_name,
        "direction": m.direction,
        "severity": None,
        "plain_thresholds": m.plain_thresholds,
        "technical": {
            "id": m.id,
            "unit": m.unit,
            "format": m.format,
            "thresholds": m.thresholds.model_dump(),
        },
    }


def _alert_entry(a: AlertCategory, wf_id: str, wf_name: str) -> dict[str, Any]:
    defaults = _facet_defaults(a.domain)
    return {
        "type": "alert",
        "id": a.id,
        "name": a.name,
        "meaning": a.meaning or a.description,
        "why_it_matters": a.why_it_matters,
        "owner": a.owner,
        "who_watches": a.who_watches or defaults["who_watches"],
        "tier": a.tier or defaults["tier"],
        "domain": a.domain or defaults["domain"],
        "workflow_id": wf_id,
        "workflow_name": wf_name,
        "direction": None,
        "severity": a.severity,
        "plain_thresholds": a.plain_thresholds,
        "technical": {
            "id": a.id,
            "icon": a.icon,
            "color": a.color,
        },
    }


def _persona_entry(p: Persona, wf_id: str, wf_name: str) -> dict[str, Any]:
    defaults = _facet_defaults(p.domain)
    return {
        "type": "persona",
        "id": p.id,
        "name": p.name,
        "meaning": p.meaning or p.description,
        "why_it_matters": p.why_it_matters,
        "owner": p.owner,
        "who_watches": p.who_watches or defaults["who_watches"],
        "tier": p.tier or defaults["tier"],
        "domain": p.domain or defaults["domain"],
        "workflow_id": wf_id,
        "workflow_name": wf_name,
        "direction": None,
        "severity": None,
        "plain_thresholds": None,
        "technical": {
            "id": p.id,
            "icon": p.icon,
            "default_authority_level": p.default_authority_level,
        },
    }


def _decision_type_entry(d: DecisionType, wf_id: str, wf_name: str) -> dict[str, Any]:
    defaults = _facet_defaults(d.domain)
    return {
        "type": "decision_type",
        "id": d.id,
        "name": d.name,
        "meaning": d.meaning or d.description,
        "why_it_matters": d.why_it_matters,
        "owner": d.owner or d.default_owner_role or d.authoring_authority_level,
        "who_watches": d.who_watches or defaults["who_watches"],
        "tier": d.tier or defaults["tier"],
        "domain": d.domain or defaults["domain"],
        "workflow_id": wf_id,
        "workflow_name": wf_name,
        "direction": None,
        "severity": d.priority,
        "plain_thresholds": None,
        "technical": {
            "id": d.id,
            "priority": d.priority,
            "sla_hours": d.sla_hours,
            "authoring_authority_level": d.authoring_authority_level,
        },
    }


def _archetype_entry(arch: Archetype) -> dict[str, Any]:
    meta = arch.archetype
    return {
        "type": "archetype",
        "id": meta.id,
        "name": meta.name,
        "meaning": meta.description,
        "why_it_matters": None,
        "owner": None,
        # Archetypes are tier-agnostic contracts — they bind at every tier
        # via the programs that point at them. cross_tier captures that.
        "who_watches": "agency_head",
        "tier": "cross_tier",
        "domain": "governance",
        "workflow_id": None,
        "workflow_name": None,
        "direction": None,
        "severity": None,
        "plain_thresholds": None,
        "technical": {
            "id": meta.id,
            "family": list(meta.family),
            "flow": meta.flow,
            "decision_basis": meta.decision_basis,
            "promotes": meta.promotes,
        },
    }


def _program_entry(prog: Program) -> dict[str, Any]:
    profile = prog.profile
    return {
        "type": "program",
        "id": profile.id,
        "name": profile.display_name or profile.name,
        "meaning": (
            f"{profile.awarding_agency or profile.agency or 'Federal'} program "
            f"bound to the {profile.binds_archetype} archetype."
        ),
        "why_it_matters": None,
        "owner": profile.awarding_agency or profile.agency,
        # Programs are federal-level definitions; state/recipient view
        # them through their matter node.
        "who_watches": "agency_head",
        "tier": "federal",
        "domain": "governance",
        "workflow_id": None,
        "workflow_name": None,
        "direction": None,
        "severity": None,
        "plain_thresholds": None,
        "technical": {
            "id": profile.id,
            "binds_archetype": profile.binds_archetype,
            "awarding_agency": profile.awarding_agency or profile.agency,
            "definition_quality": prog.definition_quality,
            "retention_months": profile.retention_months,
        },
    }
