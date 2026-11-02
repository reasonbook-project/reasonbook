# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Workflow YAML loader and boot-time validator.

Walks ``reasonbook/workflows/*/config.yaml``, parses each file with PyYAML, validates
against the Pydantic schema, then runs cross-section referential integrity
checks per workflow-yaml-schema-v1_0.md §7. Validation failures raise
``WorkflowConfigError`` so the Flask app aborts boot rather than serving a
half-loaded registry.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from reasonbook.semantic.schema import WorkflowConfig

log = logging.getLogger(__name__)

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"


class WorkflowConfigError(RuntimeError):
    """Raised when one or more workflow configs fail validation."""


def _validate_referential_integrity(cfg: WorkflowConfig) -> list[str]:
    """Return a list of human-readable problems; empty list = clean."""
    problems: list[str] = []

    metric_ids = {m.id for m in cfg.metrics}
    decision_type_ids = {d.id for d in cfg.decision_types}
    authority_ids = {a.id for a in cfg.authority_levels}
    action_ids: set[str] = set()
    for d in cfg.decision_types:
        action_ids.update(a.id for a in d.available_actions)

    # default_owner_role + each action's authority_required must reference a valid level.
    for d in cfg.decision_types:
        if d.default_owner_role and d.default_owner_role not in authority_ids:
            problems.append(
                f"decision_type '{d.id}' default_owner_role "
                f"'{d.default_owner_role}' is not a known authority_level"
            )
        for a in d.available_actions:
            if a.authority_required not in authority_ids:
                problems.append(
                    f"decision_type '{d.id}' action '{a.id}' authority_required "
                    f"'{a.authority_required}' is not a known authority_level"
                )
        # Phase 7.5 Gate 6: when a decision type is manually_creatable, its
        # authoring_authority_level must be set and must reference a known
        # authority_level on this workflow.
        if d.manually_creatable:
            if not d.authoring_authority_level:
                problems.append(
                    f"decision_type '{d.id}' is manually_creatable but has no "
                    f"authoring_authority_level"
                )
            elif d.authoring_authority_level not in authority_ids:
                problems.append(
                    f"decision_type '{d.id}' authoring_authority_level "
                    f"'{d.authoring_authority_level}' is not a known authority_level"
                )

    # authority_levels[].can_approve must reference real action ids (or 'all').
    for lvl in cfg.authority_levels:
        for action_id in lvl.can_approve:
            if action_id == "all":
                continue
            if action_id not in action_ids:
                problems.append(
                    f"authority_level '{lvl.id}' can_approve references unknown "
                    f"action_id '{action_id}'"
                )

    # outcome_metrics references known metrics.
    for d in cfg.decision_types:
        for mid in d.outcome_metrics:
            if mid not in metric_ids:
                problems.append(
                    f"decision_type '{d.id}' outcome_metrics references unknown metric '{mid}'"
                )

    # metric_groups[].metrics references known metric ids.
    for g in cfg.metric_groups:
        for mid in g.metrics:
            if mid not in metric_ids:
                problems.append(f"metric_group '{g.id}' references unknown metric '{mid}'")

    # segments[].decision_types references known decision_type ids.
    for seg_name, items in cfg.segments.items():
        for item in items:
            for did in item.decision_types:
                if did not in decision_type_ids:
                    problems.append(
                        f"segment '{seg_name}.{item.id}' references unknown decision_type '{did}'"
                    )

    # charts[].metrics references known metrics.
    for chart_id, chart in cfg.charts.items():
        for mid in chart.metrics:
            if mid not in metric_ids:
                problems.append(f"chart '{chart_id}' references unknown metric '{mid}'")

    # personas[].default_authority_level references a known level.
    for p in cfg.personas:
        if p.default_authority_level and p.default_authority_level not in authority_ids:
            problems.append(
                f"persona '{p.id}' default_authority_level "
                f"'{p.default_authority_level}' is not a known authority_level"
            )

    # workflow.id must match its directory name (enforced by the loader, not here).
    return problems


def load_workflow_file(path: Path) -> WorkflowConfig:
    """Parse and validate one workflow `config.yaml`. Raises WorkflowConfigError."""
    try:
        raw: Any = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise WorkflowConfigError(f"{path}: invalid YAML — {exc}") from exc

    if not isinstance(raw, dict):
        raise WorkflowConfigError(f"{path}: top level must be a mapping")

    try:
        cfg = WorkflowConfig.model_validate(raw)
    except ValidationError as exc:
        raise WorkflowConfigError(f"{path}: schema validation failed —\n{exc}") from exc

    problems = _validate_referential_integrity(cfg)
    if problems:
        raise WorkflowConfigError(
            f"{path}: referential integrity errors —\n  " + "\n  ".join(problems)
        )

    return cfg


def load_all(workflows_dir: Path | None = None) -> dict[str, WorkflowConfig]:
    """Load every `config.yaml` under ``workflows_dir``, keyed by workflow id.

    Directory name must match the workflow.id inside the file. Boot fails
    loudly on any validation problem.
    """
    base = workflows_dir or WORKFLOWS_DIR
    if not base.exists():
        log.info("no workflow directory at %s — skipping", base)
        return {}

    registry: dict[str, WorkflowConfig] = {}
    errors: list[str] = []

    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        cfg_path = child / "config.yaml"
        if not cfg_path.exists():
            continue
        try:
            cfg = load_workflow_file(cfg_path)
        except WorkflowConfigError as exc:
            errors.append(str(exc))
            continue

        if cfg.workflow.id != child.name:
            errors.append(
                f"{cfg_path}: workflow.id '{cfg.workflow.id}' "
                f"does not match directory name '{child.name}'"
            )
            continue

        if cfg.workflow.id in registry:
            errors.append(f"duplicate workflow.id '{cfg.workflow.id}' in {cfg_path}")
            continue

        registry[cfg.workflow.id] = cfg
        log.info("loaded workflow %s (%s)", cfg.workflow.id, cfg.workflow.name)

    if errors:
        raise WorkflowConfigError("workflow loading failed:\n  - " + "\n  - ".join(errors))

    return registry
