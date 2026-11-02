# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Oversight evidence linkage — link, supersede, query.

Each link records an operational decision (federal determination,
program activity, alert disposition) as evidence for an oversight
decision in a specific role (primary, supporting, counter, etc.).
Append-only: replacing a link sets ``superseded_at`` on the old row
and creates a new active row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from reasonbook.models import Decision, OversightEvidenceLink
from reasonbook.oversight import EVIDENCE_ROLES, OVERSIGHT_WORKFLOW_ID


class EvidenceError(ValueError):
    """Raised when evidence linkage fails business rules."""


def link_evidence(
    session: Session,
    *,
    oversight_decision_id: uuid.UUID,
    operational_decision_id: uuid.UUID,
    evidence_role: str,
    linked_by: uuid.UUID,
    rationale: str | None = None,
) -> OversightEvidenceLink:
    """Create a fresh oversight evidence link.

    Validates that:
      - the oversight decision is on workflow 10-oversight
      - the operational decision is *not* on 10-oversight (oversight
        doesn't cite oversight)
      - both decisions belong to the same tenant
      - evidence_role is recognised
      - no active link with the same (oversight, operational, role)
        already exists
    """
    if evidence_role not in EVIDENCE_ROLES:
        raise EvidenceError(f"unknown evidence_role: {evidence_role}")
    if oversight_decision_id == operational_decision_id:
        raise EvidenceError("oversight decision cannot evidence itself")

    oversight = session.get(Decision, oversight_decision_id)
    if oversight is None or oversight.workflow_id != OVERSIGHT_WORKFLOW_ID:
        raise EvidenceError("oversight_decision_id is not an oversight decision")
    op = session.get(Decision, operational_decision_id)
    if op is None:
        raise EvidenceError("operational_decision_id not found")
    if op.workflow_id == OVERSIGHT_WORKFLOW_ID:
        raise EvidenceError("operational_decision_id refers to an oversight decision")
    if op.tenant_id != oversight.tenant_id:
        raise EvidenceError("evidence and oversight decision must belong to the same tenant")

    existing = (
        session.query(OversightEvidenceLink)
        .filter(
            OversightEvidenceLink.oversight_decision_id == oversight_decision_id,
            OversightEvidenceLink.operational_decision_id == operational_decision_id,
            OversightEvidenceLink.evidence_role == evidence_role,
            OversightEvidenceLink.superseded_at.is_(None),
        )
        .one_or_none()
    )
    if existing is not None:
        raise EvidenceError("active link already exists for this triple")

    link = OversightEvidenceLink(
        id=uuid.uuid4(),
        tenant_id=oversight.tenant_id,
        oversight_decision_id=oversight_decision_id,
        operational_decision_id=operational_decision_id,
        evidence_role=evidence_role,
        link_rationale=rationale,
        linked_by=linked_by,
    )
    session.add(link)
    session.flush()
    return link


def supersede_evidence(
    session: Session,
    *,
    link_id: uuid.UUID,
    replacement: OversightEvidenceLink | None = None,
) -> OversightEvidenceLink:
    """Mark an evidence link as superseded.

    If ``replacement`` is provided (a freshly-created link), its id is
    recorded on the old row's ``superseded_by_link_id`` so the audit
    trail walks both ways.
    """
    link = session.get(OversightEvidenceLink, link_id)
    if link is None:
        raise EvidenceError("evidence link not found")
    if link.superseded_at is not None:
        raise EvidenceError("evidence link already superseded")
    link.superseded_at = datetime.now(UTC)
    if replacement is not None:
        link.superseded_by_link_id = replacement.id
    session.flush()
    return link


def list_active_evidence(
    session: Session,
    *,
    oversight_decision_id: uuid.UUID,
) -> list[OversightEvidenceLink]:
    """Return all currently-active evidence links for an oversight decision."""
    return (
        session.query(OversightEvidenceLink)
        .filter(
            OversightEvidenceLink.oversight_decision_id == oversight_decision_id,
            OversightEvidenceLink.superseded_at.is_(None),
        )
        .order_by(OversightEvidenceLink.linked_at.asc())
        .all()
    )


def evidence_diversity(
    session: Session,
    *,
    oversight_decision_id: uuid.UUID,
) -> tuple[int, int]:
    """Return ``(evidence_count, distinct_workflow_count)`` for an
    oversight decision. Used by the per-decision insight templates.
    Counts only active (non-superseded) links.
    """
    rows = (
        session.query(Decision.workflow_id)
        .join(
            OversightEvidenceLink,
            OversightEvidenceLink.operational_decision_id == Decision.id,
        )
        .filter(
            OversightEvidenceLink.oversight_decision_id == oversight_decision_id,
            OversightEvidenceLink.superseded_at.is_(None),
        )
        .all()
    )
    workflow_ids = [r[0] for r in rows]
    return len(workflow_ids), len(set(workflow_ids))
