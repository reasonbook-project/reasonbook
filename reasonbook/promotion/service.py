# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Promotion service — ledger + Decision dispatch.

Single entry point: :func:`record_determination`. Callers pass the
program a determination ran against, the inputs, the basis result, and
optionally a promotion trigger. The service:

  1. Resolves the archetype from the engine.
  2. Writes the ledger row (always).
  3. Decides whether to materialise a Decision:
     - ``promotes: every_case`` -> always promote
     - ``promotes: on_trigger`` -> promote only if trigger supplied and
       it is one of the archetype's ``promotion_triggers``
  4. If promoting, resolves any ``gate: conditional`` stages to
     ``authority`` before the Decision payload reaches the lifecycle.
  5. Returns the ledger row id, the promotion outcome, and the Decision
     id (when promoted) or None.

The Decision write itself is left to the existing decision manager —
the service exposes a hook (``create_decision_callback``) so it can be
threaded for tests without coupling to the full DecisionManager surface.

This module does NOT enforce that callers actually ran the basis. The
contract is: caller has run the basis and is reporting the outcome;
the service writes the audit trail and decides governance dispatch.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.models import DeterminationLedger
from reasonbook.semantic.archetype import Archetype, Program
from reasonbook.semantic.engine import SemanticEngine, get_engine

log = logging.getLogger(__name__)


class PromotionOutcome(StrEnum):
    """Three possible outcomes of running ``record_determination``.

    ``LEDGER_ONLY`` covers the high-volume entitlement path; the
    promotion service stops at the ledger write and no Decision is
    spawned. ``PROMOTED_EVERY_CASE`` covers every_case archetypes,
    where a Decision always follows. ``PROMOTED_ON_TRIGGER`` is the
    interesting case — an on_trigger archetype received a recognised
    trigger and a Decision was created.
    """

    LEDGER_ONLY = "ledger_only"
    PROMOTED_EVERY_CASE = "promoted_every_case"
    PROMOTED_ON_TRIGGER = "promoted_on_trigger"


@dataclass(frozen=True)
class PromotionResult:
    """Return value from :func:`record_determination`."""

    ledger_id: uuid.UUID
    outcome: PromotionOutcome
    decision_id: uuid.UUID | None = None
    promotion_trigger: str | None = None

    @property
    def promoted(self) -> bool:
        return self.outcome is not PromotionOutcome.LEDGER_ONLY


# Callable that takes the resolved Decision payload and returns the
# created Decision's id. Implementations call the existing decision
# manager (or a test stub). Kept as an injectable hook so the service
# stays decoupled from the full reasonbook.decisions surface.
CreateDecisionCallback = Callable[[dict[str, Any], Session], uuid.UUID]


class PromotionService:
    """Sits between archetype determinations and governed Decisions.

    The service owns three things:
      * Resolving the archetype + program from the engine.
      * Writing ledger rows.
      * Deciding whether to materialise a Decision (and resolving any
        ``gate: conditional`` stages to ``authority`` upstream so
        reasonbook.decisions stays unaware of the new enum value).
    """

    def __init__(
        self,
        *,
        engine: SemanticEngine | None = None,
        create_decision: CreateDecisionCallback | None = None,
    ) -> None:
        # Engine lookup is lazy by default — callers in test contexts
        # often pass an engine they constructed by hand. Production
        # callers inherit the module-singleton.
        self._engine = engine
        self._create_decision = create_decision

    # ------------------------------------------------------------------

    def engine(self) -> SemanticEngine:
        return self._engine or get_engine()

    def resolve_program(self, program_id: str) -> tuple[Program, Archetype]:
        prog = self.engine().get_program(program_id)
        arch = self.engine().archetype_for_program(program_id)
        return prog, arch

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def record_determination(
        self,
        *,
        tenant_id: str,
        program_id: str,
        inputs: dict[str, Any],
        basis_result: dict[str, Any],
        actor: dict[str, Any],
        outcome: str | None = None,
        rule_version: str | None = None,
        flow_refs: list[dict[str, Any]] | None = None,
        promotion_trigger: str | None = None,
        parent_ledger_id: uuid.UUID | None = None,
        session: Session | None = None,
    ) -> PromotionResult:
        """Run one determination through the promotion pipeline.

        Always writes a ledger row. May additionally create a Decision
        depending on the archetype's ``promotes`` value and (for
        ``on_trigger`` archetypes) whether ``promotion_trigger`` is
        one of the archetype's ``promotion_triggers``.

        ``parent_ledger_id`` links the new determination back to a prior
        ledger row — used by ``adverse_action`` appeals and any future
        re-decision flow. The parent stays closed; the child runs as a
        fresh archetype on the untouched lifecycle.

        Raises ``ValueError`` if the program is unknown or if a
        promotion trigger is supplied that the archetype does not
        recognise.
        """
        program, archetype = self.resolve_program(program_id)

        if promotion_trigger is not None:
            allowed = set(archetype.promotion_triggers)
            if promotion_trigger not in allowed:
                raise ValueError(
                    f"promotion_trigger={promotion_trigger!r} not in "
                    f"archetype.promotion_triggers={sorted(allowed)}"
                )

        # Decide whether to promote BEFORE writing the ledger row so we
        # can record `promoted=true` in the same row. The ledger row is
        # the system of record; we never come back and mutate it.
        promote, source = self._should_promote(archetype, promotion_trigger)

        def _do_work(s: Session) -> PromotionResult:
            row = DeterminationLedger(
                tenant_id=tenant_id,
                program_id=program.profile.id,
                archetype_id=archetype.archetype.id,
                promotes=archetype.archetype.promotes,
                inputs=inputs,
                rule_version=rule_version,
                basis_result=basis_result,
                outcome=outcome,
                actor=actor,
                flow_refs=flow_refs or [],
                promoted=promote,
                promotion_trigger=promotion_trigger if promote else None,
                parent_ledger_id=parent_ledger_id,
            )
            s.add(row)
            s.flush()

            decision_id: uuid.UUID | None = None
            if promote:
                payload = self._build_decision_payload(
                    archetype=archetype,
                    program=program,
                    inputs=inputs,
                    basis_result=basis_result,
                    actor=actor,
                    outcome=outcome,
                    promotion_trigger=promotion_trigger,
                    ledger_id=row.id,
                )
                decision_id = self._materialize_decision(payload, session=s)
                if decision_id is not None:
                    row.promoted_decision_id = decision_id

            log.info(
                "determination recorded: tenant=%s program=%s archetype=%s "
                "promoted=%s outcome=%s trigger=%s",
                tenant_id,
                program.profile.id,
                archetype.archetype.id,
                promote,
                outcome,
                promotion_trigger,
            )
            return PromotionResult(
                ledger_id=row.id,
                outcome=source,
                decision_id=decision_id,
                promotion_trigger=promotion_trigger if promote else None,
            )

        if session is not None:
            return _do_work(session)
        with session_scope() as managed:
            return _do_work(managed)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _should_promote(
        archetype: Archetype,
        promotion_trigger: str | None,
    ) -> tuple[bool, PromotionOutcome]:
        """The promotion gate. Returns (promote?, outcome enum)."""
        if archetype.archetype.promotes == "every_case":
            return True, PromotionOutcome.PROMOTED_EVERY_CASE
        # on_trigger: promote only if an allowed trigger was supplied.
        if promotion_trigger is not None:
            return True, PromotionOutcome.PROMOTED_ON_TRIGGER
        return False, PromotionOutcome.LEDGER_ONLY

    def _build_decision_payload(
        self,
        *,
        archetype: Archetype,
        program: Program,
        inputs: dict[str, Any],
        basis_result: dict[str, Any],
        actor: dict[str, Any],
        outcome: str | None,
        promotion_trigger: str | None,
        ledger_id: uuid.UUID,
    ) -> dict[str, Any]:
        """Build the payload handed to reasonbook.decisions for materialisation.

        Resolves ``gate: conditional`` stages to ``authority`` here so
        the downstream lifecycle code only ever sees ``none`` /
        ``authority``. The resolved stages are returned as a list, the
        same shape reasonbook.decisions consumes today.
        """
        resolved_stages: list[dict[str, Any]] = []
        # Conditional gates carry the authority gate at the moment of
        # promotion. By construction we only build a payload when the
        # determination is being promoted, so any ``conditional`` stage
        # resolves to ``authority`` here.
        for stage in archetype.stages:
            resolved_gate = "authority" if stage.gate == "conditional" else stage.gate
            resolved_stages.append(
                {
                    "id": stage.id,
                    "maps_to": stage.maps_to,
                    "label": program.vocabulary.get(stage.id, stage.label),
                    "gate": resolved_gate,
                    "required_evidence": list(stage.required_evidence),
                    "sla_hint_hours": stage.sla_hint_hours,
                }
            )

        return {
            "tenant_id": None,  # caller supplies via decision manager kwargs
            "archetype_id": archetype.archetype.id,
            "program_id": program.profile.id,
            "agency": program.profile.agency,
            "inputs": inputs,
            "basis_result": basis_result,
            "actor": actor,
            "outcome": outcome,
            "promotion_trigger": promotion_trigger,
            "ledger_id": str(ledger_id),
            "stages": resolved_stages,
            "decision_logic_type": program.decision_logic.get("type"),
            "role_assignments": dict(program.role_assignments),
            "authority": dict(program.authority),
        }

    def _materialize_decision(
        self,
        payload: dict[str, Any],
        *,
        session: Session,
    ) -> uuid.UUID | None:
        """Hand the payload off to the registered create_decision callback.

        Returns the new Decision's id, or None if no callback is
        registered (the ledger row is still written either way — this
        is what makes the on_trigger path correctly idempotent during
        tests that don't wire the decision manager).
        """
        if self._create_decision is None:
            return None
        return self._create_decision(payload, session)


# ---------------------------------------------------------------------------
# Module-level convenience function — most callers will reach for this.
# ---------------------------------------------------------------------------


def record_determination(
    *,
    tenant_id: str,
    program_id: str,
    inputs: dict[str, Any],
    basis_result: dict[str, Any],
    actor: dict[str, Any],
    outcome: str | None = None,
    rule_version: str | None = None,
    flow_refs: list[dict[str, Any]] | None = None,
    promotion_trigger: str | None = None,
    parent_ledger_id: uuid.UUID | None = None,
    session: Session | None = None,
    create_decision: CreateDecisionCallback | None = None,
    engine: SemanticEngine | None = None,
) -> PromotionResult:
    """Stateless convenience wrapper around :class:`PromotionService`.

    Most production call sites will use this; tests that want a long-
    lived service with a fixed callback can instantiate
    ``PromotionService`` directly.
    """
    service = PromotionService(engine=engine, create_decision=create_decision)
    return service.record_determination(
        tenant_id=tenant_id,
        program_id=program_id,
        inputs=inputs,
        basis_result=basis_result,
        actor=actor,
        outcome=outcome,
        rule_version=rule_version,
        flow_refs=flow_refs,
        promotion_trigger=promotion_trigger,
        parent_ledger_id=parent_ledger_id,
        session=session,
    )
