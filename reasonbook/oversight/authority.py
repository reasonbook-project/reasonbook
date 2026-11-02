# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight authority resolution.

The oversight tier's authority model is structurally distinct from
operational workflows: authority is topical (which decision domains
the user owns) and procedural (executive vs committee), not
dollar-scoped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from reasonbook.models import UserWorkflowAuthority
from reasonbook.oversight import OVERSIGHT_WORKFLOW_ID


@dataclass(frozen=True)
class OversightCapabilities:
    oversight_role: str | None
    domains_owned: tuple[str, ...]
    can_record_committee_action: bool
    level: int

    @property
    def is_executive(self) -> bool:
        # Executive personas can own decisions; oversight committee /
        # IG personas endorse but don't own.
        return self.oversight_role in {"agency_head", "cfo", "cpio", "cco", "coo", "gc"}

    @property
    def is_committee(self) -> bool:
        """True for personas that endorse but don't own oversight decisions:
        the audit committee chair (internal) and the Inspector General
        (statutorily independent). The oversight_liaison is a staff role
        and is not included here.
        """
        return self.oversight_role in {
            "audit_committee_chair",
            "inspector_general",
        }


def resolve_oversight_capabilities(
    session: Session, *, user_id: uuid.UUID
) -> OversightCapabilities | None:
    """Return the user's oversight capabilities, or ``None`` if no active grant."""
    auth = (
        session.query(UserWorkflowAuthority)
        .filter(
            UserWorkflowAuthority.user_id == user_id,
            UserWorkflowAuthority.workflow_id == OVERSIGHT_WORKFLOW_ID,
            UserWorkflowAuthority.revoked_at.is_(None),
        )
        .one_or_none()
    )
    if auth is None:
        return None
    return OversightCapabilities(
        oversight_role=auth.oversight_role,
        domains_owned=tuple(auth.oversight_domains_owned or ()),
        can_record_committee_action=bool(auth.oversight_can_record_committee_action),
        level=auth.level,
    )


def can_own_domain(caps: OversightCapabilities | None, domain: str) -> bool:
    if caps is None or not caps.is_executive:
        return False
    if caps.oversight_role == "agency_head":
        # Agency head can own any domain — parallels the legacy CEO
        # ranging across all domains in the corporate framing.
        return True
    return domain in caps.domains_owned


def can_record_committee_action(caps: OversightCapabilities | None) -> bool:
    """True for personas that endorse oversight decisions on behalf of
    an oversight body (audit committee chair, Inspector General)."""
    return bool(caps and caps.can_record_committee_action)
