# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Loader, schema, merger, and registry tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from reasonbook.semantic.config_merger import ConfigMerger, validate_override
from reasonbook.semantic.loader import WorkflowConfigError, load_all, load_workflow_file

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "dp" / "workflows"


# ---------------------------------------------------------------------------
# Loader + schema validation
# ---------------------------------------------------------------------------


def test_load_all_loads_remaining_workflows() -> None:
    """The legacy WorkflowConfig loader now backs only the apex workflow;
    the banking workflows retired in WORKFLOW-MIGRATION Step 2 and the
    user-configuration workflow (retired governance feature)."""
    registry = load_all(WORKFLOWS_DIR)
    assert set(registry.keys()) == {"10-oversight"}


ALL_WORKFLOW_IDS = ["10-oversight"]


@pytest.mark.parametrize("workflow_id", ALL_WORKFLOW_IDS)
def test_workflow_passes_referential_integrity(workflow_id: str) -> None:
    """Every shipped workflow loads cleanly with referential integrity intact.

    Catches the failure mode that matters: typos in default_owner_role or
    authority_required that reference an authority_level that doesn't exist.
    Per-workflow assertion lists (specific decision IDs, metric IDs) were
    pruned — they restated the YAML rather than guarding behavior.
    """
    cfg = load_workflow_file(WORKFLOWS_DIR / workflow_id / "config.yaml")
    assert cfg.workflow.id == workflow_id

    authority_ids = {a.id for a in cfg.authority_levels}
    for d in cfg.decision_types:
        # Apex decisions derive owner role from `domain` at runtime; the
        # user-configuration workflow lets the system pick the owner; other
        # workflows declare `default_owner_role` directly.
        if d.default_owner_role is not None:
            assert d.default_owner_role in authority_ids, (workflow_id, d.id)
        for a in d.available_actions:
            assert a.authority_required in authority_ids, (workflow_id, d.id, a.id)
        assert d.oversight_evidence_eligible is not None, (workflow_id, d.id)


def test_loader_rejects_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "99-bad" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(": not yaml\n")
    with pytest.raises(WorkflowConfigError):
        load_all(tmp_path)


def test_loader_rejects_unknown_authority_reference(tmp_path: Path) -> None:
    bad = tmp_path / "99-broken" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "99-broken", "name": "Broken"},
                "decision_types": [
                    {
                        "id": "x",
                        "name": "X",
                        "priority": "low",
                        "available_actions": [
                            {
                                "id": "do",
                                "name": "Do",
                                "authority_required": "ghost",
                            }
                        ],
                    }
                ],
                "authority_levels": [],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "ghost"},
            }
        )
    )
    with pytest.raises(WorkflowConfigError, match="not a known authority_level"):
        load_all(tmp_path)


def test_loader_rejects_directory_id_mismatch(tmp_path: Path) -> None:
    bad = tmp_path / "99-mismatch" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "wrong-id", "name": "X"},
                "authority_levels": [{"id": "a", "name": "A", "level": 1}],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "a"},
            }
        )
    )
    with pytest.raises(WorkflowConfigError, match="does not match directory name"):
        load_all(tmp_path)


def test_loader_rejects_manually_creatable_without_authority(tmp_path: Path) -> None:
    """Phase 7.5 Gate 6: a manually_creatable decision type must declare an
    authoring_authority_level."""
    bad = tmp_path / "99-bad" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "99-bad", "name": "Bad"},
                "decision_types": [
                    {
                        "id": "manual_thing",
                        "name": "Manual Thing",
                        "priority": "low",
                        "manually_creatable": True,
                        # authoring_authority_level intentionally omitted
                    }
                ],
                "authority_levels": [{"id": "officer", "name": "Officer", "level": 1}],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "officer"},
            }
        )
    )
    with pytest.raises(
        WorkflowConfigError, match="manually_creatable but has no authoring_authority_level"
    ):
        load_all(tmp_path)


def test_loader_rejects_manually_creatable_with_unknown_authority(tmp_path: Path) -> None:
    """Phase 7.5 Gate 6: authoring_authority_level must reference a real
    authority_level on the workflow."""
    bad = tmp_path / "99-bad" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "99-bad", "name": "Bad"},
                "decision_types": [
                    {
                        "id": "manual_thing",
                        "name": "Manual Thing",
                        "priority": "low",
                        "manually_creatable": True,
                        "authoring_authority_level": "ghost_role",
                    }
                ],
                "authority_levels": [{"id": "officer", "name": "Officer", "level": 1}],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "officer"},
            }
        )
    )
    with pytest.raises(
        WorkflowConfigError,
        match="authoring_authority_level 'ghost_role' is not a known authority_level",
    ):
        load_all(tmp_path)


def test_loader_accepts_manually_creatable_with_valid_authority(tmp_path: Path) -> None:
    """Phase 7.5 Gate 6: a well-formed manually_creatable decision type loads."""
    good = tmp_path / "99-good" / "config.yaml"
    good.parent.mkdir()
    good.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "99-good", "name": "Good"},
                "decision_types": [
                    {
                        "id": "manual_thing",
                        "name": "Manual Thing",
                        "priority": "low",
                        "manually_creatable": True,
                        "authoring_authority_level": "officer",
                    }
                ],
                "authority_levels": [{"id": "officer", "name": "Officer", "level": 1}],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "officer"},
            }
        )
    )
    registry = load_all(tmp_path)
    assert "99-good" in registry
    dt = registry["99-good"].decision_types[0]
    assert dt.manually_creatable is True
    assert dt.authoring_authority_level == "officer"


def test_loader_rejects_duplicate_metric_ids(tmp_path: Path) -> None:
    bad = tmp_path / "99-dupe" / "config.yaml"
    bad.parent.mkdir()
    bad.write_text(
        yaml.safe_dump(
            {
                "workflow": {"id": "99-dupe", "name": "Dupe"},
                "metrics": [
                    {"id": "m1", "name": "A"},
                    {"id": "m1", "name": "B"},
                ],
                "authority_levels": [],
                "overridable_keys": {},
                "sla": {"timezone": "UTC"},
                "ownership": {"primary_role": "x"},
            }
        )
    )
    with pytest.raises(WorkflowConfigError, match="duplicate metric ids"):
        load_all(tmp_path)


# ---------------------------------------------------------------------------
# ConfigMerger — synthetic configs (no DB)
# ---------------------------------------------------------------------------


def test_merger_returns_base_when_no_overrides() -> None:
    merger = ConfigMerger(
        workflow_id="x",
        base_config={"sla": {"default_response_hours": 48}},
        allowlist={"sla.default_response_hours": "int"},
    )
    # Override loader is the DB; with no DB session passed and no rows, base.
    out = merger.get_merged("nonexistent-tenant")
    assert out["sla"]["default_response_hours"] == 48


def test_validate_override_accepts_correct_type() -> None:
    ok, err = validate_override("k", 7, {"k": "int"})
    assert ok and err is None


def test_validate_override_rejects_wrong_type() -> None:
    ok, err = validate_override("k", "not-an-int", {"k": "int"})
    assert not ok
    assert err is not None and "expected int" in err


def test_validate_override_rejects_unknown_key() -> None:
    ok, err = validate_override("ghost", 1, {"k": "int"})
    assert not ok
    assert err is not None and "not in the workflow's overridable_keys" in err
