# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Alert disposition service.

One entry point: ``record_disposition``. Writes one append-only
``alert_dispositions`` row, updates the alert's denormalised
``current_status``, and (for ``promote``) instantiates a governed
Decision via :mod:`reasonbook.promotion.service`.

DB-level CHECK constraints enforce most invariants (rationale length,
reason_code-on-dismiss, decision-on-promote, actor_tier enum). This
service adds the application-level validations and the cross-table
write coordination.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any, Literal

from sqlalchemy.orm import Session

from reasonbook.models import Alert, AlertDisposition, User
from reasonbook.promotion.service import record_determination as _record_determination

DecisionFactory = Callable[[dict[str, Any], Session], uuid.UUID]

DispositionAction = Literal["promote", "dismiss", "hold", "reopen"]
DismissReason = Literal[
    "false_positive",
    "not_actionable",
    "duplicate",
    "resolved_elsewhere",
]

_DISMISS_REASONS: frozenset[str] = frozenset(
    {"false_positive", "not_actionable", "duplicate", "resolved_elsewhere"}
)
_MIN_RATIONALE_LEN = 8


# Status transitions per disposition. Maps (current_status, action) ->
# resulting_status. Anything not in the table is rejected as an invalid
# state change.
_TRANSITIONS: dict[tuple[str, str], str] = {
    # From 'new' — any of the four close paths.
    ("new", "promote"): "promoted",
    ("new", "dismiss"): "dismissed",
    ("new", "hold"): "triaged",
    # From 'triaged' (on hold) — still resolvable.
    ("triaged", "promote"): "promoted",
    ("triaged", "dismiss"): "dismissed",
    ("triaged", "hold"): "triaged",
    # Reopen brings a closed alert back to actionable.
    ("dismissed", "reopen"): "reopened",
    ("promoted", "reopen"): "reopened",
    # From 'reopened' — same outbound paths as 'new'.
    ("reopened", "promote"): "promoted",
    ("reopened", "dismiss"): "dismissed",
    ("reopened", "hold"): "triaged",
}


class DispositionError(ValueError):
    """Application-level validation failure on a disposition write.

    Raised as ValueError so Flask error handlers can map it to 4xx
    without special-casing.
    """


def record_disposition(
    *,
    alert_id: uuid.UUID,
    action: DispositionAction,
    rationale: str,
    actor: User,
    session: Session,
    reason_code: DismissReason | None = None,
    metadata: dict[str, Any] | None = None,
) -> AlertDisposition:
    """Append one disposition; update alert.current_status; promote if needed.

    Single chokepoint for all alert closure paths. Callers MUST go
    through this function — direct inserts into ``alert_dispositions``
    bypass the cross-table coordination and the lifecycle validation.

    Raises ``DispositionError`` for application-level rule violations
    (bad transition, missing reason_code for dismiss, rationale too short).
    DB-level CHECKs catch anything that slips through.
    """
    rationale = (rationale or "").strip()
    if len(rationale) < _MIN_RATIONALE_LEN:
        raise DispositionError(
            f"rationale must be at least {_MIN_RATIONALE_LEN} characters"
        )

    if action == "dismiss":
        if not reason_code:
            raise DispositionError("dismiss requires reason_code")
        if reason_code not in _DISMISS_REASONS:
            raise DispositionError(
                f"reason_code must be one of {sorted(_DISMISS_REASONS)}"
            )
    elif reason_code is not None:
        raise DispositionError(
            f"reason_code is only valid for action='dismiss', not {action!r}"
        )

    alert = session.get(Alert, alert_id)
    if alert is None:
        raise DispositionError(f"alert {alert_id} not found")

    transition_key = (alert.current_status, action)
    if transition_key not in _TRANSITIONS:
        raise DispositionError(
            f"cannot {action} an alert in status {alert.current_status!r}"
        )
    resulting_status = _TRANSITIONS[transition_key]

    resulting_decision_id: uuid.UUID | None = None
    if action == "promote":
        resulting_decision_id = _promote_to_decision(
            alert=alert,
            actor=actor,
            rationale=rationale,
            session=session,
        )

    disposition = AlertDisposition(
        alert_id=alert.id,
        action=action,
        reason_code=reason_code,
        rationale=rationale,
        actor_user_id=actor.id,
        actor_tier=_tier_of(actor),
        resulting_decision_id=resulting_decision_id,
        resulting_status=resulting_status,
        event_metadata=metadata or {},
    )
    session.add(disposition)
    alert.current_status = resulting_status
    session.flush()
    return disposition


def _promote_to_decision(
    *,
    alert: Alert,
    actor: User,
    rationale: str,
    session: Session,
) -> uuid.UUID:
    """Run the alert through the existing promotion service.

    The alert's ``target_program_id`` is the routing key. Inputs carry
    the alert id + signal_ref so the resulting Decision's metadata names
    its origin (Decision Detail surfaces "Origin: AL-…" by reading these).
    """
    create_decision = _make_decision_factory(actor=actor, alert=alert)

    result = _record_determination(
        tenant_id=alert.tenant_id,
        program_id=alert.target_program_id,
        inputs={
            "from_alert": True,
            "alert_id": str(alert.id),
            "signal_ref": alert.signal_ref,
            "subject_entity": alert.subject_entity,
        },
        basis_result={"promoted_by_actor": True, "rationale": rationale},
        actor={
            "kind": "user",
            "id": str(actor.id),
            "role": "alert_triage",
        },
        outcome=None,
        rule_version="alert-triage-v1",
        promotion_trigger=None,
        session=session,
        create_decision=create_decision,
    )
    if result.decision_id is None:
        raise DispositionError(
            f"program {alert.target_program_id!r} did not promote to a Decision "
            "(check archetype.promotes / promotion_triggers)"
        )
    return result.decision_id


def _make_decision_factory(*, actor: User, alert: Alert) -> DecisionFactory:
    """Build the create_decision callback the promotion service invokes.

    Mirrors the seed-time factory in ``scripts.seed_dev`` — a minimal
    real Decision row with status='assigned' (owner is the actor, so
    the Decision lands in their Inbox immediately) and a title derived
    from the alert. The promotion-service contract is
    ``(payload: dict, session: Session) -> uuid.UUID``.
    """

    def callback(payload: dict[str, Any], s: Session) -> uuid.UUID:
        from datetime import UTC, datetime

        from reasonbook.models import Decision

        decision_id = uuid.uuid4()
        s.add(
            Decision(
                id=decision_id,
                tenant_id=alert.tenant_id,
                decision_number=f"PI-{decision_id.hex[:8].upper()}",
                workflow_id=payload["program_id"],
                decision_type=payload["archetype_id"],
                title=_decision_title_from_alert(alert),
                priority="high",
                severity="high",
                status="assigned",
                owner_id=actor.id,
                created_by=actor.id,
                assigned_at=datetime.now(UTC),
            )
        )
        s.flush()
        return decision_id

    return callback


def _decision_title_from_alert(alert: Alert) -> str:
    """Derive a human-readable Decision title from the originating alert."""
    return f"Review from alert: {alert.title}"


def _tier_of(actor: User) -> str:
    """Resolve the actor's tier for the disposition snapshot.

    Tenancy work (TENANCY-MODEL §2.2) adds a ``tier`` column to users.
    Until that migration lands, every actor is federal — alerts ship
    federal-only as documented in ALERTS-SPEC §5.
    """
    return getattr(actor, "tier", None) or "federal"
