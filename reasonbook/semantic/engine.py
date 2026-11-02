# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Semantic layer engine — single in-memory registry of all workflow configs.

Consolidates the per-pipe ``core/semantic_engine.py`` modules from the legacy
codebase into one canonical implementation per schema doc §2B.1. The engine
is loaded once at app boot via ``init_engine()`` and held as a module-level
singleton; routes and the ingestion job read it through ``get_engine()``.

Per-tenant config (with overrides applied) is computed on demand by
``merged_config_for(tenant_id, workflow_id)``, which delegates to a
``ConfigMerger`` cached per workflow.

WORKFLOW-MIGRATION (Step 4): The engine now also carries the archetype +
program-profile registries loaded from ``dp/config/`` by
:mod:`reasonbook.semantic.archetype_loader`. Legacy workflows (``apex``,
``user-configuration``) keep loading through the original
:mod:`reasonbook.semantic.loader` path until they're migrated.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.semantic.archetype import (
    Archetype,
    DefinitionQualityLiteral,
    HeartbeatConfig,
    Program,
    ProgramDefaults,
    UpstreamReview,
)
from reasonbook.semantic.archetype_loader import load_all_archetypes_and_programs
from reasonbook.semantic.config_merger import ConfigMerger
from reasonbook.semantic.loader import WorkflowConfigError, load_all
from reasonbook.semantic.schema import WorkflowConfig

log = logging.getLogger(__name__)


class SemanticEngine:
    """Holds parsed workflow configs and the per-workflow ConfigMerger cache.

    The archetype + program registries layered on top are read-only views
    of the loaded YAML — tenant overrides on programs flow through the
    same ``ConfigMerger`` pipeline as workflows (programs are keyed by
    ``profile.id``; their override allowlist is the archetype's
    ``profile_extensible`` translated to dot-paths).
    """

    def __init__(
        self,
        registry: dict[str, WorkflowConfig],
        *,
        archetypes: dict[str, Archetype] | None = None,
        programs: dict[str, Program] | None = None,
    ) -> None:
        self._registry = registry
        self._archetypes: dict[str, Archetype] = archetypes or {}
        self._programs: dict[str, Program] = programs or {}
        self._mergers: dict[str, ConfigMerger] = {}
        for wf_id, cfg in registry.items():
            self._mergers[wf_id] = ConfigMerger(
                workflow_id=wf_id,
                base_config=cfg.model_dump(mode="json"),
                allowlist=cfg.overridable_keys,
            )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def workflow_ids(self) -> list[str]:
        return sorted(self._registry.keys())

    def has(self, workflow_id: str) -> bool:
        return workflow_id in self._registry

    def get_config(self, workflow_id: str) -> WorkflowConfig:
        if workflow_id not in self._registry:
            raise KeyError(workflow_id)
        return self._registry[workflow_id]

    def merged_config_for(
        self,
        tenant_id: str,
        workflow_id: str,
        *,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Return the workflow's config with this tenant's overrides applied."""
        merger = self._mergers.get(workflow_id)
        if merger is None:
            raise KeyError(workflow_id)
        return merger.get_merged(tenant_id, session=session)

    # ------------------------------------------------------------------
    # Lookups commonly needed by callers
    # ------------------------------------------------------------------

    def list_summaries(self) -> list[dict[str, Any]]:
        """Compact view used by ``GET /api/workflows`` and the rail UI."""
        out: list[dict[str, Any]] = []
        for wf_id in self.workflow_ids():
            wf = self._registry[wf_id].workflow
            out.append(
                {
                    "id": wf.id,
                    "name": wf.name,
                    "description": wf.description,
                    "icon": wf.icon,
                    "color": wf.color,
                    "version": wf.version,
                    "apex_contributing": wf.apex_contributing,
                    "kind": wf.kind,
                }
            )
        return out

    # ------------------------------------------------------------------
    # Archetype + program access (WORKFLOW-MIGRATION Step 4)
    # ------------------------------------------------------------------

    def archetype_ids(self) -> list[str]:
        return sorted(self._archetypes)

    def program_ids(self) -> list[str]:
        return sorted(self._programs)

    def get_archetype(self, archetype_id: str) -> Archetype:
        if archetype_id not in self._archetypes:
            raise KeyError(archetype_id)
        return self._archetypes[archetype_id]

    def get_program(self, program_id: str) -> Program:
        if program_id not in self._programs:
            raise KeyError(program_id)
        return self._programs[program_id]

    def archetype_for_program(self, program_id: str) -> Archetype:
        """Resolve a program to its bound archetype.

        Promotion service entry point — given the program a determination
        runs against, the bound archetype's ``promotes`` and
        ``promotion_triggers`` drive ledger-vs-Decision dispatch.
        """
        prog = self.get_program(program_id)
        return self.get_archetype(prog.profile.binds_archetype)

    def list_programs_by_archetype(self, archetype_id: str) -> list[Program]:
        return sorted(
            (p for p in self._programs.values() if p.profile.binds_archetype == archetype_id),
            key=lambda p: p.profile.id,
        )

    # ------------------------------------------------------------------
    # Convenience accessors for TENANCY-MODEL §5 / §14.4 fields
    # ------------------------------------------------------------------

    def upstream_review_for(self, archetype_id: str) -> UpstreamReview:
        """Read archetype.upstream_review with the default-notify shape.

        Per TENANCY-MODEL §5. Promotion dispatch reads this to decide
        whether finalize writes a notify event or creates an upstream
        Decision (gate).
        """
        return self.get_archetype(archetype_id).upstream_review

    def heartbeat_for(self, program_id: str) -> HeartbeatConfig:
        """Read program.heartbeat.

        Per TENANCY-MODEL §14.3. The sweeper consumes this to know when
        to open ownership-gap alerts. Caller is responsible for honoring
        ``definition_quality == 'lacks_definition'`` (no pickup heartbeat).
        """
        return self.get_program(program_id).heartbeat

    def definition_quality_of(self, program_id: str) -> DefinitionQualityLiteral:
        """Read program.definition_quality.

        Per TENANCY-MODEL §14.4. Drives whether the pickup heartbeat
        fires at all and how the resulting alert is framed.
        """
        return self.get_program(program_id).definition_quality

    def defaults_for(self, program_id: str) -> ProgramDefaults:
        """Read program.defaults — the per-tier active_archetypes +
        authority_role pre-fill values for the matter create flow.

        Per TENANCY-MODEL §11.2. The matter create transaction (step 5)
        consumes this to populate ``matter_nodes.active_archetypes``
        and ``authority_role`` on each newly-minted node. Values are
        editable per-matter before submit; once persisted on the node
        the node is the source of truth.
        """
        return self.get_program(program_id).defaults


# ----------------------------------------------------------------------
# Module-level singleton
# ----------------------------------------------------------------------

_engine: SemanticEngine | None = None


def init_engine(workflows_dir: Path | None = None) -> SemanticEngine:
    """Load all workflow configs + archetypes + programs and bind the singleton.

    Idempotent. Calls fail loud (``WorkflowConfigError`` /
    ``ArchetypeConfigError``) on any validation issue — better to abort
    boot than to serve a half-loaded registry.
    """
    global _engine
    registry = load_all(workflows_dir)
    archetypes, programs = load_all_archetypes_and_programs()
    _engine = SemanticEngine(registry, archetypes=archetypes, programs=programs)
    log.info(
        "semantic engine initialised: %d workflow(s) [%s], %d archetype(s), %d program(s)",
        len(registry),
        ", ".join(sorted(registry)),
        len(archetypes),
        len(programs),
    )
    return _engine


def get_engine() -> SemanticEngine:
    if _engine is None:
        raise WorkflowConfigError("SemanticEngine not initialised — call init_engine() at app boot")
    return _engine


def reset_engine() -> None:
    """Test helper — clear the singleton."""
    global _engine
    _engine = None
