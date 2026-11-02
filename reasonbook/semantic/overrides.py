# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""OverrideManager — append-only tenant-override write path.

Ports `_legacy/cu-saas/settings/overrides.py` simplified for Reasonbook:

- Allowlist now derives from each workflow YAML's ``overridable_keys`` section
  via the loaded ``SemanticEngine`` rather than a hand-maintained Python
  registry.
- Vocabulary updated to ``tenant_id`` / ``workflow_id``.
- The append-only history pattern (``superseded_at`` markers) is preserved.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.models import AgencySemanticOverride
from reasonbook.semantic.config_merger import validate_override
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)


class OverrideError(ValueError):
    """Raised on invalid override write attempts."""


def set_override(
    *,
    tenant_id: str,
    workflow_id: str,
    config_key: str,
    config_value: Any,
    modified_by: uuid.UUID,
    change_note: str | None = None,
    approved_by: uuid.UUID | None = None,
    session: Session | None = None,
) -> AgencySemanticOverride:
    """Write an override with append-only semantics (supersedes any current row)."""
    engine = get_engine()
    cfg = engine.get_config(workflow_id)
    ok, err = validate_override(config_key, config_value, cfg.overridable_keys)
    if not ok:
        raise OverrideError(err or "override rejected")

    def _do(s: Session) -> AgencySemanticOverride:
        now = datetime.now(UTC)
        # Supersede any current row for this (tenant, workflow, key).
        current = (
            s.query(AgencySemanticOverride)
            .filter(
                AgencySemanticOverride.tenant_id == tenant_id,
                AgencySemanticOverride.workflow_id == workflow_id,
                AgencySemanticOverride.config_key == config_key,
                AgencySemanticOverride.superseded_at.is_(None),
            )
            .one_or_none()
        )
        if current is not None:
            current.superseded_at = now

        row = AgencySemanticOverride(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            workflow_id=workflow_id,
            config_key=config_key,
            config_value=config_value,
            modified_by=modified_by,
            modified_at=now,
            approved_by=approved_by,
            approved_at=now if approved_by else None,
            change_note=change_note,
        )
        s.add(row)
        s.flush()
        return row

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        row = _do(managed)
        managed.expunge(row)
        return row


def supersede_override(
    *,
    tenant_id: str,
    workflow_id: str,
    config_key: str,
    session: Session | None = None,
) -> bool:
    """Mark the current row for a key as superseded with no replacement."""

    def _do(s: Session) -> bool:
        current = (
            s.query(AgencySemanticOverride)
            .filter(
                AgencySemanticOverride.tenant_id == tenant_id,
                AgencySemanticOverride.workflow_id == workflow_id,
                AgencySemanticOverride.config_key == config_key,
                AgencySemanticOverride.superseded_at.is_(None),
            )
            .one_or_none()
        )
        if current is None:
            return False
        current.superseded_at = datetime.now(UTC)
        s.flush()
        return True

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        return _do(managed)


def get_override_history(
    *, tenant_id: str, workflow_id: str, session: Session | None = None
) -> list[AgencySemanticOverride]:
    """Full append-only timeline for one tenant + workflow, newest first."""

    def _do(s: Session) -> list[AgencySemanticOverride]:
        rows = (
            s.query(AgencySemanticOverride)
            .filter(
                AgencySemanticOverride.tenant_id == tenant_id,
                AgencySemanticOverride.workflow_id == workflow_id,
            )
            .order_by(AgencySemanticOverride.modified_at.desc())
            .all()
        )
        return list(rows)

    if session is not None:
        return _do(session)
    with session_scope() as managed:
        rows = _do(managed)
        for r in rows:
            managed.expunge(r)
        return rows
