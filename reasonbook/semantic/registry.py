# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Decision-type registry sync.

At app boot, walk the loaded workflow configs and upsert rows into
``platform.decision_types`` per schema doc §3.3. The YAMLs are the source of
truth; the table exists for FK references and for surfaces that need cheap
joins (e.g., the Inbox's `decision_type` column on `decisions`).

Idempotent. Decision types removed from a YAML are *not* deleted — historical
decisions reference them — they're flagged ``active = false``.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select

from reasonbook.db import session_scope
from reasonbook.models import DecisionType
from reasonbook.semantic.engine import SemanticEngine

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def sync_decision_types(engine: SemanticEngine) -> dict[str, int]:
    """Upsert decision_types from loaded YAMLs. Returns {inserted, updated, deactivated}."""
    counts = {"inserted": 0, "updated": 0, "deactivated": 0}

    with session_scope() as session:
        for workflow_id in engine.workflow_ids():
            cfg = engine.get_config(workflow_id)
            yaml_type_ids = {d.id for d in cfg.decision_types}

            # Upsert each YAML-defined decision type.
            for d in cfg.decision_types:
                _upsert_one(
                    session=session,
                    workflow_id=workflow_id,
                    workflow_version=cfg.workflow.version,
                    yaml_type=d,
                    counts=counts,
                )

            # Deactivate rows whose type_id no longer appears in the YAML.
            stmt = (
                select(DecisionType)
                .where(DecisionType.workflow_id == workflow_id)
                .where(DecisionType.active.is_(True))
            )
            for row in session.execute(stmt).scalars():
                if row.type_id not in yaml_type_ids:
                    row.active = False
                    counts["deactivated"] += 1
                    log.info(
                        "deactivated decision_type workflow=%s type_id=%s",
                        workflow_id,
                        row.type_id,
                    )

        session.flush()

    log.info(
        "decision_types sync: inserted=%(inserted)d updated=%(updated)d "
        "deactivated=%(deactivated)d",
        counts,
    )
    return counts


def _upsert_one(
    *,
    session: Session,
    workflow_id: str,
    workflow_version: str,
    yaml_type: object,
    counts: dict[str, int],
) -> None:
    # yaml_type is a DecisionType pydantic model — use attribute access.
    existing = (
        session.query(DecisionType)
        .filter(
            DecisionType.workflow_id == workflow_id,
            DecisionType.type_id == yaml_type.id,  # type: ignore[attr-defined]
        )
        .one_or_none()
    )

    fields = {
        "name": yaml_type.name,  # type: ignore[attr-defined]
        "description": yaml_type.description,  # type: ignore[attr-defined]
        "domain": yaml_type.domain,  # type: ignore[attr-defined]
        "default_priority": yaml_type.priority,  # type: ignore[attr-defined]
        "sla_hours": yaml_type.sla_hours,  # type: ignore[attr-defined]
        "default_owner_role": yaml_type.default_owner_role,  # type: ignore[attr-defined]
        "trigger_metric": _first_trigger_metric(yaml_type),
        "trigger_threshold": _first_trigger_threshold(yaml_type),
        "payload_schema": yaml_type.payload_schema,  # type: ignore[attr-defined]
        "oversight_evidence_eligible": yaml_type.oversight_evidence_eligible,  # type: ignore[attr-defined]
        "workflow_version": workflow_version,
        "active": True,
    }

    if existing is None:
        session.add(
            DecisionType(
                id=uuid.uuid4(),
                workflow_id=workflow_id,
                type_id=yaml_type.id,  # type: ignore[attr-defined]
                **fields,
            )
        )
        counts["inserted"] += 1
    else:
        changed = False
        for k, v in fields.items():
            if getattr(existing, k) != v:
                setattr(existing, k, v)
                changed = True
        if changed:
            counts["updated"] += 1


def _first_trigger_metric(yaml_type: object) -> str | None:
    triggers = getattr(yaml_type, "triggers", []) or []
    return triggers[0].metric if triggers else None


def _first_trigger_threshold(yaml_type: object) -> dict[str, str] | None:
    triggers = getattr(yaml_type, "triggers", []) or []
    if not triggers:
        return None
    return {"condition": triggers[0].condition or ""}
