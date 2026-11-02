# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Ingestion orchestration.

For each tenant + entitled workflow:

1. Read the most recent pipe-data row from the local pipe_* staging tables.
2. For each decision_type defined in the workflow YAML, evaluate every
   trigger expression against the corresponding metric value.
3. If a trigger fires AND there isn't already an open decision with the
   same fingerprint, create a new decision via the DecisionManager.

Dedup fingerprint: ``ingest.{workflow_id}.{decision_type_id}.{metric_id}``
written to ``decisions.signal_source``. A non-closed/non-deferred decision
with this signal_source for the same tenant blocks new creation. Once it's
closed, a subsequent firing creates a fresh decision.

Idempotent — running twice in a row with no data change creates no rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.decisions import manager
from reasonbook.ingestion.evaluator import evaluate, metric_value
from reasonbook.ingestion.pipe_reader import (
    PIPE_TABLE_NAMES,
    PipeReading,
    latest_reading,
)
from reasonbook.models import Decision, Tenant
from reasonbook.semantic.engine import get_engine
from reasonbook.semantic.schema import DecisionType, WorkflowConfig

log = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    tenants_evaluated: int = 0
    workflows_evaluated: int = 0
    triggers_evaluated: int = 0
    triggers_fired: int = 0
    decisions_created: int = 0
    decisions_skipped_dedup: int = 0
    errors: list[str] = field(default_factory=list)


def _signal_source(workflow_id: str, decision_type_id: str, metric_id: str) -> str:
    return f"ingest.{workflow_id}.{decision_type_id}.{metric_id}"


def _has_open_decision_for_signal(
    *,
    session: Session,
    tenant_id: str,
    workflow_id: str,
    signal_source: str,
) -> bool:
    """Dedup gate — any active decision with this signal_source already?

    Phase 7.5 Gate 4: ``manual.*`` signal_source values are server-generated
    per-creation in ``api/decisions.py`` and are guaranteed unique by the
    embedded uuid. Skip the dedup query for them — the dedup invariant is
    engine-only by definition, and matching a fresh ``manual.{user_id}.{uuid}``
    against existing rows can never collide. This guard documents intent and
    avoids a round-trip in the (rare) case the runner ever sees one.
    """
    if signal_source.startswith("manual."):
        return False

    stmt = (
        select(Decision.id)
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id == workflow_id)
        .where(Decision.signal_source == signal_source)
        .where(Decision.status.notin_(["closed", "deferred"]))
        .limit(1)
    )
    return session.execute(stmt).first() is not None


def _evaluate_decision_type(
    *,
    session: Session,
    cfg: WorkflowConfig,
    decision_type: DecisionType,
    reading: PipeReading,
    stats: IngestionStats,
) -> None:
    for trigger in decision_type.triggers:
        if not trigger.metric or not trigger.condition:
            continue
        stats.triggers_evaluated += 1

        value = metric_value(reading.data, trigger.metric)
        if value is None:
            continue
        if not evaluate(trigger.condition, value):
            continue

        stats.triggers_fired += 1
        signal_source = _signal_source(cfg.workflow.id, decision_type.id, trigger.metric)

        if _has_open_decision_for_signal(
            session=session,
            tenant_id=reading.tenant_id,
            workflow_id=cfg.workflow.id,
            signal_source=signal_source,
        ):
            stats.decisions_skipped_dedup += 1
            log.info(
                "skip dedup tenant=%s workflow=%s type=%s metric=%s",
                reading.tenant_id,
                cfg.workflow.id,
                decision_type.id,
                trigger.metric,
            )
            continue

        title = decision_type.name
        summary = (
            f"{trigger.description} (current {trigger.metric}={value})"
            if trigger.description
            else f"{trigger.metric} = {value}"
        )

        manager.create_decision(
            tenant_id=reading.tenant_id,
            workflow_id=cfg.workflow.id,
            decision_type=decision_type.id,
            title=title,
            description=decision_type.description,
            priority=decision_type.priority,
            sla_hours=decision_type.sla_hours,
            trigger_data={
                "metric": trigger.metric,
                "value": value,
                "condition": trigger.condition,
                "period_date": reading.period_date.isoformat(),
            },
            signal_source=signal_source,
            signal_summary=summary,
            session=session,
        )
        stats.decisions_created += 1
        log.info(
            "created decision tenant=%s workflow=%s type=%s metric=%s value=%s",
            reading.tenant_id,
            cfg.workflow.id,
            decision_type.id,
            trigger.metric,
            value,
        )


def run_ingestion(
    *,
    tenant_ids: list[str] | None = None,
) -> IngestionStats:
    """Walk every tenant × entitled workflow × decision type, fire matching triggers.

    ``tenant_ids`` defaults to every tenant in the database. Decisions are
    created with no owner and no `created_by` — the schema permits both.
    """
    stats = IngestionStats()
    engine = get_engine()

    with session_scope() as session:
        if tenant_ids is None:
            tenants = [t.tenant_id for t in session.query(Tenant).all()]
        else:
            tenants = list(tenant_ids)

        for tenant_id in tenants:
            stats.tenants_evaluated += 1
            # Single-tenant DP has no per-tenant entitlement gating; walk
            # every workflow that has a backing pipe_* table and is
            # registered in the semantic engine.
            for workflow_id in PIPE_TABLE_NAMES:
                if not engine.has(workflow_id):
                    continue
                stats.workflows_evaluated += 1

                reading = latest_reading(
                    session=session, tenant_id=tenant_id, workflow_id=workflow_id
                )
                if reading is None:
                    continue

                cfg = engine.get_config(workflow_id)
                for decision_type in cfg.decision_types:
                    try:
                        _evaluate_decision_type(
                            session=session,
                            cfg=cfg,
                            decision_type=decision_type,
                            reading=reading,
                            stats=stats,
                        )
                    except Exception as exc:  # noqa: BLE001
                        msg = (
                            f"failed evaluating tenant={tenant_id} "
                            f"workflow={workflow_id} type={decision_type.id}: {exc}"
                        )
                        stats.errors.append(msg)
                        log.exception(msg)

    return stats
