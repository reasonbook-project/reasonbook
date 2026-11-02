# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ConfigMerger — merges a workflow's base config with tenant overrides.

Ported from `_legacy/dp-cu-bsa/core/config_merger.py` (byte-identical across
all 10 legacy pipe apps; consolidated here as the single canonical
implementation per schema doc §2A.5).

Adjustments from the legacy version:

- Application/credit_union vocabulary updated to workflow_id/tenant_id.
- The base config is no longer loaded from disk per-instance — it's passed
  in as a dict (the loaded WorkflowConfig serialised back out, or any other
  mapping). This lets us share one cached parse across many tenants.
- The override loader now reads from `platform.tenant_semantic_overrides`
  via SQLAlchemy ORM models.
"""

from __future__ import annotations

import copy
import logging
from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.models import AgencySemanticOverride

log = logging.getLogger(__name__)


_TYPE_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "str": lambda v: isinstance(v, str),
    "bool": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "dict": lambda v: isinstance(v, dict),
}


def _resolve_path(data: dict[str, Any], dot_path: str) -> tuple[dict[str, Any] | None, str | None]:
    """Walk ``data`` along ``dot_path`` → (parent_dict, final_key) or (None, None)."""
    parts = dot_path.split(".")
    current: Any = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current:
            return None, None
        current = current[part]
    if not isinstance(current, dict):
        return None, None
    return current, parts[-1]


def _set_path(data: dict[str, Any], dot_path: str, value: Any) -> None:
    parts = dot_path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def validate_override(
    config_key: str, value: Any, allowlist: Mapping[str, str]
) -> tuple[bool, str | None]:
    """True if ``value`` matches the allowlist's expected type for ``config_key``."""
    expected = allowlist.get(config_key)
    if expected is None:
        return False, f"key '{config_key}' is not in the workflow's overridable_keys"
    validator = _TYPE_VALIDATORS.get(expected)
    if validator is None:
        return False, f"unknown type '{expected}' in allowlist for '{config_key}'"
    if not validator(value):
        return False, (
            f"value for '{config_key}' failed type check "
            f"(expected {expected}, got {type(value).__name__})"
        )
    return True, None


class ConfigMerger:
    """Merge a workflow's base config dict with current tenant overrides."""

    def __init__(
        self,
        *,
        workflow_id: str,
        base_config: dict[str, Any],
        allowlist: Mapping[str, str],
        require_approval: bool = False,
    ) -> None:
        self.workflow_id = workflow_id
        self._base = base_config
        self.allowlist = allowlist
        self.require_approval = require_approval

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def get_merged(self, tenant_id: str, *, session: Session | None = None) -> dict[str, Any]:
        """Return a deep copy of the base config with current overrides applied."""
        merged = copy.deepcopy(self._base)
        rows = self._load_overrides(tenant_id, session=session)

        for config_key, config_value in rows:
            ok, err = validate_override(config_key, config_value, self.allowlist)
            if not ok:
                log.warning(
                    "override skipped: tenant=%s workflow=%s key=%s reason=%s",
                    tenant_id,
                    self.workflow_id,
                    config_key,
                    err,
                )
                continue

            parent, final_key = _resolve_path(merged, config_key)
            if parent is not None and final_key is not None:
                parent[final_key] = config_value
            else:
                _set_path(merged, config_key, config_value)
                log.info(
                    "override created path: tenant=%s workflow=%s key=%s",
                    tenant_id,
                    self.workflow_id,
                    config_key,
                )

        return merged

    def _load_overrides(
        self, tenant_id: str, *, session: Session | None = None
    ) -> list[tuple[str, Any]]:
        def _query(s: Session) -> list[tuple[str, Any]]:
            q = (
                s.query(AgencySemanticOverride)
                .filter(
                    AgencySemanticOverride.tenant_id == tenant_id,
                    AgencySemanticOverride.workflow_id == self.workflow_id,
                    AgencySemanticOverride.superseded_at.is_(None),
                )
                .order_by(AgencySemanticOverride.config_key)
            )
            if self.require_approval:
                q = q.filter(AgencySemanticOverride.approved_at.is_not(None))
            return [(r.config_key, r.config_value) for r in q.all()]

        if session is not None:
            return _query(session)
        with session_scope() as managed:
            return _query(managed)
