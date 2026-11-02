# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Authority enforcement and escalation-path computation.

Decision-level checks live here:

- ``current_authority_level``: latest non-revoked level for a (user, workflow).
- ``required_level_for_action``: looks up the action's authority_required in
  the workflow YAML and returns its numeric level.
- ``user_can_approve_action``: gate used at finalize time.
- ``compute_escalation_path``: walks ``user_supervisors`` from the owner up
  through their chain of supervisors at claim time, snapshotting the path
  onto the decision row.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.models import User, UserSupervisor, UserWorkflowAuthority
from reasonbook.semantic.engine import get_engine

log = logging.getLogger(__name__)

MAX_ESCALATION_DEPTH = 6


def current_authority_level(
    *, session: Session, user_id: uuid.UUID, workflow_id: str
) -> int | None:
    """Latest active authority level for (user, workflow), or None if none."""
    row = (
        session.query(UserWorkflowAuthority)
        .filter(
            UserWorkflowAuthority.user_id == user_id,
            UserWorkflowAuthority.workflow_id == workflow_id,
            UserWorkflowAuthority.revoked_at.is_(None),
        )
        .order_by(UserWorkflowAuthority.granted_at.desc())
        .first()
    )
    return int(row.level) if row else None


def required_level_for_action(workflow_id: str, action_id: str) -> int | None:
    """Numeric level of the authority_level that owns ``action_id``.

    Pulled from the workflow YAML — every action's ``authority_required``
    points at an authority_level ``id``, and that level has a ``level`` int.
    Returns None if the action isn't in the workflow.
    """
    cfg = get_engine().get_config(workflow_id)
    # Build action_id → required_authority_id map.
    action_to_authority: dict[str, str] = {}
    for d in cfg.decision_types:
        for a in d.available_actions:
            action_to_authority[a.id] = a.authority_required

    auth_id = action_to_authority.get(action_id)
    if auth_id is None:
        return None
    for level in cfg.authority_levels:
        if level.id == auth_id:
            return int(level.level)
    return None


def _is_program_id(workflow_id: str) -> bool:
    """``workflow_id`` is a federal program profile id (smuggled into the
    workflow_id column today — see G1)."""
    return workflow_id in get_engine().program_ids()


def _tenant_can_originate_on_program(
    *,
    session: Session,
    user_id: uuid.UUID,
    program_id: str,  # noqa: ARG001 — reserved for archetype-role check (G5b)
) -> tuple[bool, str | None]:
    """Federal program path for authority checks (G5 lite).

    Honest scope: this only verifies the user exists in *some* tenant — it
    does NOT enforce the archetype's role gate (e.g. competitive_award's
    `authority_decision` requires the program-mapped `approving_official`
    role like `ic_director`). That role-resolution layer is the follow-up
    workstream (G5b / part of G1's first-class entitlements rework).

    Returning permissive here unblocks the BUILD-SPEC Phase 1 lifecycle
    end-to-end demonstration; role-based gating lands in the next pass.
    """
    user = session.get(User, user_id)
    if user is None:
        return False, f"user {user_id} not found"
    return True, None


def user_can_approve_action(
    *,
    session: Session,
    user_id: uuid.UUID,
    workflow_id: str,
    action_id: str,
) -> tuple[bool, str | None]:
    """Returns (allowed, reason_if_not). Reason is for error messages.

    Workflows with ``kind: user_configuration`` (per
    decision-governance-self-assessment-platform-variant-v1_0.md §8.5.3) bypass
    the standard authority-level check because their decisions are owned by
    the receiving user — ownership is the real gate, not workflow-level
    authority. The dedicated admin override endpoint handles its own
    privilege check before reaching the manager.
    """
    if _is_program_id(workflow_id):
        return _tenant_can_originate_on_program(
            session=session, user_id=user_id, program_id=workflow_id
        )

    cfg = get_engine().get_config(workflow_id)
    if cfg.workflow.kind == "user_configuration":
        return True, None

    user_level = current_authority_level(session=session, user_id=user_id, workflow_id=workflow_id)
    if user_level is None:
        return False, f"no active authority for workflow '{workflow_id}'"

    required = required_level_for_action(workflow_id, action_id)
    if required is None:
        return False, f"action '{action_id}' is not defined in '{workflow_id}'"

    if user_level < required:
        return False, (
            f"user authority level {user_level} is below the required {required} "
            f"for action '{action_id}'"
        )
    return True, None


def user_can_create_decision_type(
    *,
    session: Session,
    user_id: uuid.UUID,
    workflow_id: str,
    decision_type_id: str,
) -> tuple[bool, str | None]:
    """Phase 7.5 Gate 4 — gate for manual decision creation.

    Reads the workflow YAML's decision type and:
      - rejects if the type is not ``manually_creatable``
      - looks up its ``authoring_authority_level`` (a role id) and
        compares against the user's level on this workflow

    Distinct from ``user_can_approve_action`` which gates per-action
    transitions on existing decisions; this one gates whether a user
    can originate a new decision in the first place.
    """
    if _is_program_id(workflow_id):
        return _tenant_can_originate_on_program(
            session=session, user_id=user_id, program_id=workflow_id
        )

    cfg = get_engine().get_config(workflow_id)

    decision_type = next((d for d in cfg.decision_types if d.id == decision_type_id), None)
    if decision_type is None:
        return False, (f"decision type '{decision_type_id}' is not defined in '{workflow_id}'")

    if not decision_type.manually_creatable:
        return False, (f"decision type '{decision_type_id}' is not manually creatable")

    auth_role = decision_type.authoring_authority_level
    if not auth_role:
        # Pydantic enforces this post-Gate-6, but defend against legacy YAMLs.
        return False, (
            f"decision type '{decision_type_id}' is manually_creatable but has "
            f"no authoring_authority_level"
        )

    required_level: int | None = None
    for level in cfg.authority_levels:
        if level.id == auth_role:
            required_level = int(level.level)
            break
    if required_level is None:
        return False, (
            f"authoring_authority_level '{auth_role}' is not declared on workflow '{workflow_id}'"
        )

    user_level = current_authority_level(session=session, user_id=user_id, workflow_id=workflow_id)
    if user_level is None:
        return False, f"no active authority for workflow '{workflow_id}'"

    if user_level < required_level:
        return False, (
            f"user authority level {user_level} is below the required "
            f"{required_level} ('{auth_role}') for creating decision type "
            f"'{decision_type_id}'"
        )

    return True, None


def compute_escalation_path(
    *,
    session: Session,
    user_id: uuid.UUID,
    tenant_id: str,
    workflow_id: str,
) -> list[dict[str, Any]]:
    """Walk ``user_supervisors`` upward from ``user_id`` to build the chain.

    Returns a list of ``{user_id, name, level}`` dicts, ordered from the
    immediate supervisor to the topmost supervisor reachable. Workflow-scoped
    supervisor rows beat workflow-agnostic rows where both exist.
    """
    path: list[dict[str, Any]] = []
    current: uuid.UUID | None = user_id
    seen: set[uuid.UUID] = {user_id}

    for _ in range(MAX_ESCALATION_DEPTH):
        if current is None:
            break
        sup_row = (
            session.query(UserSupervisor)
            .filter(
                UserSupervisor.tenant_id == tenant_id,
                UserSupervisor.user_id == current,
                UserSupervisor.effective_to.is_(None),
            )
            .filter(
                # Prefer workflow-scoped row if both exist; SQLAlchemy can't
                # express "prefer X else Y" in one query cleanly, so we order
                # by whether workflow_id matches.
                (UserSupervisor.workflow_id == workflow_id) | (UserSupervisor.workflow_id.is_(None))
            )
            .order_by(UserSupervisor.workflow_id.is_(None))  # non-null first
            .first()
        )
        if sup_row is None or sup_row.supervisor_id in seen:
            break

        sup_user = session.get(User, sup_row.supervisor_id)
        if sup_user is None:
            break
        sup_level = current_authority_level(
            session=session, user_id=sup_user.id, workflow_id=workflow_id
        )
        path.append(
            {
                "user_id": str(sup_user.id),
                "name": sup_user.name,
                "level": sup_level,
            }
        )
        seen.add(sup_user.id)
        current = sup_user.id

    return path
