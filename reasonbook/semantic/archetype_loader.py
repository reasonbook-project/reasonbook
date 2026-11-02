# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Loader for the archetype × program-profile config corpus.

Walks ``dp/config/archetypes/<id>.yaml`` and ``dp/config/programs/<id>.yaml``,
parses with PyYAML, validates against the Pydantic models in
:mod:`reasonbook.semantic.archetype`, then runs the contract enforcement pass:

* every program's ``binds_archetype`` must resolve to a loaded archetype
* every key the program sets must be listed in that archetype's
  ``profile_extensible``
* every key in the archetype's ``profile_required`` must be supplied
  by the program

The same boot-fails-loud posture as :mod:`reasonbook.semantic.loader` —
``ArchetypeConfigError`` is raised on the first failure so the app
aborts startup rather than serving a half-loaded registry.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from reasonbook.semantic.archetype import Archetype, Program

log = logging.getLogger(__name__)

CONFIG_ROOT = Path(__file__).resolve().parent.parent / "config"
ARCHETYPES_DIR = CONFIG_ROOT / "archetypes"
PROGRAMS_DIR = CONFIG_ROOT / "programs"


class ArchetypeConfigError(RuntimeError):
    """Raised when archetype or program YAML fails validation."""


# ---------------------------------------------------------------------------
# Dot-path helpers (shared with the loader's contract enforcement pass)
# ---------------------------------------------------------------------------


def _resolve_dot_path(data: Any, dot_path: str) -> tuple[bool, Any]:
    """Walk ``dot_path`` against ``data``; return ``(present, value_or_none)``.

    Supports ``stages[].label`` style — the ``[]`` segment means "every
    element of this list must contain the remainder of the path." Present
    iff the list is non-empty and every element resolves.
    """
    parts = dot_path.split(".")
    current: Any = data
    for i, part in enumerate(parts):
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(current, dict) or key not in current:
                return False, None
            collection = current[key]
            if not isinstance(collection, list) or not collection:
                return False, None
            rest = ".".join(parts[i + 1 :])
            if not rest:
                return True, collection
            for item in collection:
                ok, _ = _resolve_dot_path(item, rest)
                if not ok:
                    return False, None
            return True, collection
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _collect_set_paths(prefix: str, value: Any) -> Iterable[str]:
    """Yield dot-paths for every leaf the program actually sets.

    Used to detect keys the program touched that aren't on the archetype's
    ``profile_extensible`` allowlist. We yield top-level keys only because
    the allowlist works at the section level (``decision_logic``,
    ``vocabulary``, etc.) — deeper paths inside those sections are
    program-defined content, not separate allowlist entries.
    """
    if isinstance(value, dict):
        for k in value:
            yield f"{prefix}.{k}" if prefix else k
    else:
        yield prefix


# ---------------------------------------------------------------------------
# Archetype loading
# ---------------------------------------------------------------------------


def _load_yaml_dict(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ArchetypeConfigError(f"{path}: invalid YAML — {exc}") from exc
    if not isinstance(raw, dict):
        raise ArchetypeConfigError(f"{path}: top level must be a mapping")
    return raw


def load_archetype_file(path: Path) -> Archetype:
    raw = _load_yaml_dict(path)
    try:
        arch = Archetype.model_validate(raw)
    except ValidationError as exc:
        raise ArchetypeConfigError(f"{path}: schema validation failed —\n{exc}") from exc
    if arch.archetype.id != path.stem:
        raise ArchetypeConfigError(
            f"{path}: archetype.id={arch.archetype.id!r} does not match filename"
        )
    return arch


def load_archetypes(archetypes_dir: Path | None = None) -> dict[str, Archetype]:
    """Load every ``*.yaml`` under ``archetypes_dir``, keyed by archetype id."""
    base = archetypes_dir or ARCHETYPES_DIR
    if not base.exists():
        log.info("no archetypes directory at %s — skipping", base)
        return {}

    registry: dict[str, Archetype] = {}
    errors: list[str] = []

    for path in sorted(base.glob("*.yaml")):
        try:
            arch = load_archetype_file(path)
        except ArchetypeConfigError as exc:
            errors.append(str(exc))
            continue
        if arch.archetype.id in registry:
            errors.append(f"duplicate archetype id {arch.archetype.id!r} at {path}")
            continue
        registry[arch.archetype.id] = arch
        log.info("loaded archetype %s (%s)", arch.archetype.id, arch.archetype.name)

    if errors:
        raise ArchetypeConfigError("archetype loading failed:\n  - " + "\n  - ".join(errors))
    return registry


# ---------------------------------------------------------------------------
# Program loading (with profile_extensible / profile_required enforcement)
# ---------------------------------------------------------------------------


def load_program_file(path: Path, *, archetypes: dict[str, Archetype]) -> Program:
    raw = _load_yaml_dict(path)
    try:
        prog = Program.model_validate(raw)
    except ValidationError as exc:
        raise ArchetypeConfigError(f"{path}: schema validation failed —\n{exc}") from exc

    if prog.profile.id != path.stem:
        raise ArchetypeConfigError(
            f"{path}: profile.id={prog.profile.id!r} does not match filename"
        )

    archetype = archetypes.get(prog.profile.binds_archetype)
    if archetype is None:
        raise ArchetypeConfigError(
            f"{path}: binds_archetype={prog.profile.binds_archetype!r} is not a loaded archetype"
        )

    problems = _enforce_profile_contract(raw, archetype)
    if problems:
        raise ArchetypeConfigError(
            f"{path}: profile contract violations —\n  " + "\n  ".join(problems)
        )

    return prog


def _enforce_profile_contract(program_raw: dict[str, Any], archetype: Archetype) -> list[str]:
    """Check profile_required (must be supplied) + profile_extensible (allowlist).

    Returns a list of human-readable problems; empty list = clean.
    """
    problems: list[str] = []

    # profile_required — every listed path must resolve in the program.
    for required in archetype.profile_required:
        ok, _ = _resolve_dot_path(program_raw, required)
        if not ok:
            problems.append(f"missing required key {required!r}")

    # profile_extensible — the program may set only these top-level
    # sections (plus the ``profile`` metadata + ``schema_version`` envelope).
    #
    # We translate archetype-side allowlist paths into the program-side
    # section names that carry the override values. Critically:
    #   * ``stages[].*``  -> program uses ``stage_overrides`` (NOT ``stages``)
    #   * ``roles[].*``   -> program uses ``role_assignments`` (NOT ``roles``)
    # Letting the program write a top-level ``stages:`` or ``roles:`` block
    # would let it shadow archetype structure, which the contract forbids.
    # Base allowlist: the profile envelope + the cross-cutting matter-lifecycle
    # fields (TENANCY-MODEL §11.2 + §14.4). These are structural across all
    # programs — the archetype's profile_extensible list controls what's
    # negotiable about decision_logic / vocabulary / etc., but every program
    # gets to declare its delegation defaults, heartbeat clocks, and
    # definition-quality flag regardless of bound archetype.
    allowed_top: set[str] = {
        "profile",
        "schema_version",
        "definition_quality",
        "defaults",
        "heartbeat",
    }
    for path in archetype.profile_extensible:
        head = path.split(".")[0]
        if head == "stages[]":
            allowed_top.add("stage_overrides")
        elif head == "roles[]":
            allowed_top.add("role_assignments")
        else:
            # Scalar section name — strip any trailing index marker just in case.
            allowed_top.add(head.split("[")[0])
    # profile_required paths also imply their containing top-level section.
    for path in archetype.profile_required:
        head = path.split(".")[0]
        if head == "stages[]":
            allowed_top.add("stage_overrides")
        elif head == "roles[]":
            allowed_top.add("role_assignments")
        else:
            allowed_top.add(head.split("[")[0])

    for top in program_raw:
        if top not in allowed_top:
            problems.append(
                f"program touches disallowed section {top!r} "
                f"(allowed top-level sections: {sorted(allowed_top)})"
            )

    # reconstructability.retention_months: extend only
    base_retention = archetype.reconstructability.retention_months
    prog_recon = program_raw.get("reconstructability", {})
    if isinstance(prog_recon, dict):
        prog_retention = prog_recon.get("retention_months")
        if isinstance(prog_retention, int) and prog_retention < base_retention:
            problems.append(
                f"reconstructability.retention_months={prog_retention} "
                f"< archetype default {base_retention} (extend only)"
            )

    # definition_quality <-> heartbeat consistency (TENANCY-MODEL §14.4):
    #   * lacks_definition: NO pickup heartbeat fires (refuse to manufacture
    #     a timeline). state_pickup_days MUST be omitted.
    #   * clear with a state stakeholder declared: state_pickup_days MUST
    #     be set (a clear program must declare its pickup clock).
    definition_quality = program_raw.get("definition_quality", "clear")
    heartbeat = program_raw.get("heartbeat") or {}
    if not isinstance(heartbeat, dict):
        heartbeat = {}
    state_pickup_days = heartbeat.get("state_pickup_days")
    if definition_quality == "lacks_definition" and state_pickup_days is not None:
        problems.append(
            "definition_quality='lacks_definition' forbids "
            "heartbeat.state_pickup_days (no pickup clock for undefined timelines)"
        )
    if definition_quality == "clear":
        defaults_block = program_raw.get("defaults") or {}
        state_defaults = (
            defaults_block.get("state") if isinstance(defaults_block, dict) else None
        )
        has_state_node = (
            isinstance(state_defaults, dict)
            and bool(state_defaults.get("active_archetypes"))
        )
        if has_state_node and state_pickup_days is None:
            problems.append(
                "definition_quality='clear' with a state stakeholder requires "
                "heartbeat.state_pickup_days (the pickup clock)"
            )

    # ProfileMeta.retention_months — extend-only against archetype default
    # (mirrors reconstructability.retention_months but expressed at the
    # profile level so programs can declare their override either way).
    profile_block = program_raw.get("profile") or {}
    if isinstance(profile_block, dict):
        prog_retention = profile_block.get("retention_months")
        if isinstance(prog_retention, int) and prog_retention < base_retention:
            problems.append(
                f"profile.retention_months={prog_retention} "
                f"< archetype default {base_retention} (extend only)"
            )

    # stages[].sla_hint_hours: tighten only (per archetype.schema.yaml
    # ``stages[].sla_hint_hours # tighten only``).
    base_slas = {s.id: s.sla_hint_hours for s in archetype.stages}
    overrides = program_raw.get("stage_overrides", {})
    if isinstance(overrides, dict):
        for stage_id, sec in overrides.items():
            if not isinstance(sec, dict):
                continue
            new_sla = sec.get("sla_hint_hours")
            base_sla = base_slas.get(stage_id)
            if isinstance(new_sla, int) and isinstance(base_sla, int) and new_sla > base_sla:
                # Allow extension when the archetype.schema.yaml comment
                # says "tighten/extend within policy" (recertification.data_refresh,
                # nih-r01.merit_review). Recording but not blocking; the
                # rule could move to strict if/when we find an enforcement
                # surface that wants it. Logged for visibility.
                log.info(
                    "program loosens sla_hint_hours on stage %s: %s -> %s",
                    stage_id,
                    base_sla,
                    new_sla,
                )

    return problems


def load_programs(
    archetypes: dict[str, Archetype],
    *,
    programs_dir: Path | None = None,
) -> dict[str, Program]:
    """Load every ``*.yaml`` under ``programs_dir``, keyed by profile id."""
    base = programs_dir or PROGRAMS_DIR
    if not base.exists():
        log.info("no programs directory at %s — skipping", base)
        return {}

    registry: dict[str, Program] = {}
    errors: list[str] = []

    for path in sorted(base.glob("*.yaml")):
        try:
            prog = load_program_file(path, archetypes=archetypes)
        except ArchetypeConfigError as exc:
            errors.append(str(exc))
            continue
        if prog.profile.id in registry:
            errors.append(f"duplicate program id {prog.profile.id!r} at {path}")
            continue
        registry[prog.profile.id] = prog
        log.info(
            "loaded program %s (%s) -> archetype %s",
            prog.profile.id,
            prog.profile.name,
            prog.profile.binds_archetype,
        )

    if errors:
        raise ArchetypeConfigError("program loading failed:\n  - " + "\n  - ".join(errors))
    return registry


def load_all_archetypes_and_programs(
    *,
    archetypes_dir: Path | None = None,
    programs_dir: Path | None = None,
) -> tuple[dict[str, Archetype], dict[str, Program]]:
    archetypes = load_archetypes(archetypes_dir)
    programs = load_programs(archetypes, programs_dir=programs_dir)
    return archetypes, programs
