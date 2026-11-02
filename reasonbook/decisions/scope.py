# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Inbox query helpers — scope, density, stage, workflow, sort, paginate.

These functions take an existing SQLAlchemy ``Query`` for ``Decision`` and
return a narrowed query. They never execute. The route handler stitches
them together based on URL search params.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, literal, select, true
from sqlalchemy.orm import Query, Session

from reasonbook.db import GUID
from reasonbook.models import Agency, Decision, DecisionEvent, UserAgencyScope, UserSupervisor

OVERSIGHT_WORKFLOW_ID = "10-oversight"

# ---------------------------------------------------------------------------
# Shared status + at-risk helpers
# ---------------------------------------------------------------------------
#
# `OPEN_STATUSES` was previously a module-private constant in
# ``dgp/api/dashboard.py``. Hoisted here because the P17 decision-queue
# endpoint shares the same "what counts as open / at-risk" predicate and
# we don't want two definitions to drift.

OPEN_STATUSES: tuple[str, ...] = ("open", "assigned", "in_progress")


# Oversight decisions in ``decided`` aren't "done" the way operational
# ``decided`` decisions are — the next gate is committee endorsement, not
# action. Committee endorsement is a `decision_events` row with
# action='endorsed_by_committee' / 'noted_by_committee' / legacy
# 'ratified_by_board' / 'ratified_by_committee' carryovers. Until that
# row exists, the decision is "awaiting committee" and should surface as
# such. Once endorsed, it falls into the standard operational flow
# (Action → Outcome → Closed).
def _endorsed_oversight_decision_ids_subquery() -> Any:
    """Subquery: ids of oversight decisions that have a committee-endorsement
    event. Used to exclude already-endorsed oversight decisions from the
    awaiting-committee population."""
    return (
        select(DecisionEvent.decision_id)
        .where(
            DecisionEvent.action.in_(
                (
                    "endorsed_by_committee",
                    "noted_by_committee",
                    "ratified_by_committee",
                    "ratified_by_board",  # legacy carryover from banking era
                )
            )
        )
        .scalar_subquery()
    )


def oversight_awaiting_committee_filter() -> Any:
    """Predicate: oversight decision is ``decided`` and has no committee
    endorsement event.

    Operational decisions never match. Once an endorsement event exists,
    the decision falls out of this population and follows the standard
    Action → Outcome path.
    """
    return (
        (Decision.workflow_id == OVERSIGHT_WORKFLOW_ID)
        & (Decision.status == "decided")
        & (~Decision.id.in_(_endorsed_oversight_decision_ids_subquery()))
    )


def open_filter() -> Any:
    """Predicate: decision is currently in the open population (open,
    assigned, or in_progress). Mirrors ``OPEN_STATUSES``; lifted into a
    function for symmetry with ``at_risk_filter()``."""
    return Decision.status.in_(OPEN_STATUSES)


def at_risk_filter() -> Any:
    """Predicate: decision is in ``OPEN_STATUSES`` AND its SLA deadline
    is ≤ 24 hours away (or already past).

    Intersecting status with ``OPEN_STATUSES`` maintains the invariant
    ``at_risk ≤ open`` — an at-risk decision is by definition still in
    the open population. Decisions in ``decided`` that haven't yet been
    closed are NOT at-risk: their decision-gate SLA was either met or
    has already breached, but they aren't currently in danger.
    """
    cutoff = datetime.now(UTC) + timedelta(hours=24)
    return (Decision.sla_deadline.isnot(None)) & (Decision.sla_deadline <= cutoff) & open_filter()


# At-risk strategic-domain map: workflow_id → category label used by the
# dashboard top-rail breakdown pills AND the P17 decision-queue endpoint's
# ``category`` filter. Three buckets ("credit", "compliance", "ops") chosen
# because a CEO scan benefits from coarse grouping over per-workflow
# specificity. Mapping lives here (not in a workflow YAML) because it's a
# deliberate cross-workflow product concern, not a per-workflow config.

AT_RISK_CATEGORY_BY_WORKFLOW: dict[str, str] = {
    "01-regulatory-compliance": "compliance",
    "10-oversight": "compliance",
}

ScopeLiteral = Literal["mine", "team", "all_entitled"]
DensityLiteral = Literal["active", "all"]
StageLiteral = Literal[
    "signals",
    "decisions",
    "actions",
    "awaiting_committee",
    "outcomes",
    "closed",
]
SortLiteral = Literal["newest", "oldest", "sla_deadline", "priority"]


# ---------------------------------------------------------------------------
# Stage mapping (the four-bucket StageStrip in the Inbox)
# ---------------------------------------------------------------------------


def apply_stage(query: Query[Decision], stage: str | None) -> Query[Decision]:
    if stage is None:
        return query
    if stage == "signals":
        return query.filter(Decision.status == "open")
    if stage == "decisions":
        return query.filter(Decision.status.in_(["assigned", "in_progress"]))
    if stage == "actions":
        # Oversight decisions in `decided` belong in the `awaiting_committee`
        # stage until committee endorsement — exclude them so the Actions
        # tile reads honestly (operational decisions only).
        return query.filter(
            Decision.status == "decided",
            Decision.action_completed_at.is_(None),
            ~oversight_awaiting_committee_filter(),
        )
    if stage == "awaiting_committee":
        return query.filter(oversight_awaiting_committee_filter())
    if stage == "outcomes":
        return query.filter(
            Decision.status == "decided",
            Decision.action_completed_at.is_not(None),
            Decision.outcome_recorded_at.is_(None),
        )
    if stage == "closed":
        return query.filter(Decision.status == "closed")
    return query


# ---------------------------------------------------------------------------
# Density (active vs include closed/deferred)
# ---------------------------------------------------------------------------


def apply_density(query: Query[Decision], density: str | None) -> Query[Decision]:
    if density == "all":
        return query
    # default = active: hide closed and deferred
    return query.filter(Decision.status.notin_(["closed", "deferred"]))


# ---------------------------------------------------------------------------
# Scope (Mine / Team / All entitled)
# ---------------------------------------------------------------------------


def tier_scope_where(
    *,
    tier: str,
    participant_org_id: uuid.UUID | None,
) -> Any:
    """Return a boolean column expression for row-level tier scope, for
    use in SQLAlchemy Core ``select().where(...)`` aggregates.

    Federal returns SQL ``TRUE`` — safe to pass to ``.where()``
    unconditionally. Every other tier returns a concrete expression:

    - state: fund_flow_path contains the user's participant_org_id
    - recipient: contains AND is the leaf
    - missing org or unknown tier: ``Decision.id == zero UUID`` (default-deny)

    Twin of ``apply_tier_scope`` for ``session.query()`` callers — both
    encode the same policy. Use ``apply_tier_scope`` whenever you have a
    Query object; reach for this only when working with Core selects
    (the dashboard aggregates do, per TENANCY-AGGREGATE-QUERY-AUDIT.md).
    """
    if tier == "federal":
        return true()
    if participant_org_id is None:
        return Decision.id == uuid.UUID(int=0)
    org_literal = literal(participant_org_id, type_=GUID)
    if tier == "state":
        return Decision.fund_flow_path.any(org_literal)
    if tier == "recipient":
        path_length = func.array_length(Decision.fund_flow_path, 1)
        return (Decision.fund_flow_path.any(org_literal)) & (
            Decision.fund_flow_path[path_length] == org_literal
        )
    return Decision.id == uuid.UUID(int=0)


def apply_tier_scope(
    query: Query[Any],
    *,
    tier: str,
    participant_org_id: uuid.UUID | None,
) -> Query[Any]:
    """Row-level enforcement of the tenancy model — TENANCY-MODEL.md §3.

    Federal is the only unscoped tier (sees the full chain). State sees
    every decision whose fund_flow_path includes its participant_org_id.
    Recipient sees only its own slice — fund_flow_path's leaf must match.
    Any other tier collapses to default-deny.

    Federal-root decisions have empty fund_flow_path; state and recipient
    tiers correctly never see them through this filter.

    This is the single chokepoint. Called inside ``apply_scope`` so every
    Decision query routes through it. Aggregate / raw-SQL paths that
    can't enforce row-level scope must flag and refactor, never weaken
    the boundary (per §3).
    """
    if tier == "federal":
        return query

    if participant_org_id is None:
        # tier ∈ {state, recipient} but no org — DB CHECK forbids this on
        # the users table, but defend in depth: default-deny.
        return query.filter(Decision.id == uuid.UUID(int=0))

    org_literal = literal(participant_org_id, type_=GUID)

    if tier == "state":
        return query.filter(Decision.fund_flow_path.any(org_literal))

    if tier == "recipient":
        # Indexed-prefix filter via .any(), then narrow to "is the leaf".
        # array_length returns NULL on empty arrays (PG quirk) — that
        # leaf check naturally rejects empty paths.
        path_length = func.array_length(Decision.fund_flow_path, 1)
        return query.filter(
            Decision.fund_flow_path.any(org_literal),
            Decision.fund_flow_path[path_length] == org_literal,
        )

    # Unknown tier — default-deny.
    return query.filter(Decision.id == uuid.UUID(int=0))


def accessible_agency_ids(
    session: Session,
    *,
    user_id: uuid.UUID,
    primary_agency_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """Return every agency id a user can see per the DP visibility rules.

    Visibility is **explicit** in DP: the user's primary agency is always
    in the set (if set), but descendants of the primary agency are NOT
    implicitly included. Cross-agency grants in ``user_agency_scopes``
    are the mechanism — a grant with ``includes_descendants=True``
    expands into the full sub-tree of the granted agency.

    Result includes:
      - The user's primary agency (if not null), without descendants.
      - Each active cross-grant target, expanded to include the granted
        agency's descendants when ``includes_descendants`` is true.

    Returns [] when the user has no primary and no active grants — the
    caller should treat that as "no federal-tier visibility."
    """
    accessible: set[uuid.UUID] = set()

    if primary_agency_id is not None:
        accessible.add(primary_agency_id)

    grants = (
        session.query(UserAgencyScope.agency_id, UserAgencyScope.includes_descendants)
        .filter(
            UserAgencyScope.user_id == user_id,
            UserAgencyScope.revoked_at.is_(None),
        )
        .all()
    )
    for agency_id, includes_descendants in grants:
        accessible.add(agency_id)
        if includes_descendants:
            accessible.update(_descendant_agency_ids(session, root_id=agency_id))

    return list(accessible)


def _descendant_agency_ids(session: Session, *, root_id: uuid.UUID) -> set[uuid.UUID]:
    """Recursive CTE walk of the agency tree from ``root_id`` (exclusive).

    Postgres-only — SQLAlchemy's ``recursive`` CTE support wraps native
    ``WITH RECURSIVE``. For the tiny hierarchies DP deals with (a few
    departments × a few bureaus × a few program offices) this is O(N)
    and lands in a single query.
    """
    agencies_table = Agency.__table__
    base = (
        select(agencies_table.c.id)
        .where(agencies_table.c.parent_agency_id == root_id)
        .cte(name="descendants", recursive=True)
    )
    recursive = select(agencies_table.c.id).where(
        agencies_table.c.parent_agency_id == base.c.id
    )
    walk = base.union_all(recursive)
    rows = session.execute(select(walk.c.id)).scalars().all()
    return set(rows)


def apply_scope(
    query: Query[Decision],
    *,
    scope: str | None,
    user_id: uuid.UUID,
    tenant_id: str,
    session: Session,
    tier: str = "federal",
    participant_org_id: uuid.UUID | None = None,
    primary_agency_id: uuid.UUID | None = None,
) -> Query[Decision]:
    """Filter decisions by who's expected to act on them.

    - ``mine``: owner_id = user_id
    - ``team``: owner is a direct report of user_id (per user_supervisors)
    - ``all_entitled`` (default): every decision the caller's agency
      access grants

    Row-level tenancy scope is applied first via ``apply_tier_scope``
    (TENANCY-MODEL.md §3): federal sees the full chain; state sees its
    state's slice; recipient sees only its leaf. The mine/team/all axis
    is the orthogonal *who-acts* filter on top of that. Defaults preserve
    backwards compatibility (federal / no org) for callers that haven't
    yet been threaded.

    For federal-tier users, agency visibility is layered on top:
    ``primary_agency_id`` + explicit cross-grants (see
    ``accessible_agency_ids``) narrow the decision set to the agencies
    the user can see. State/recipient tier users are unaffected —
    ``apply_tier_scope`` already narrows their view by fund-flow tier.

    Entitlements were retired in the DG-substrate cleanup — DP is
    single-tenant, so per-workflow gating is meaningless. The scope
    "all_entitled" name is kept for API surface compatibility.
    """
    # Tenancy row-level scope — single chokepoint per §3.
    query = apply_tier_scope(query, tier=tier, participant_org_id=participant_org_id)

    # Scope to the tenant (US Federal Government singleton).
    query = query.filter(Decision.tenant_id == tenant_id)

    # Agency scope for federal-tier users. State / recipient users
    # aren't agency-scoped — their access is fund-flow-tier-limited by
    # apply_tier_scope above. Rows without an agency_id (legacy /
    # pre-backfill) fall through so the seed can plant them and then
    # backfill in a follow-up migration.
    if tier == "federal":
        agency_ids = accessible_agency_ids(
            session, user_id=user_id, primary_agency_id=primary_agency_id
        )
        if agency_ids:
            query = query.filter(
                (Decision.agency_id.in_(agency_ids)) | (Decision.agency_id.is_(None))
            )

    if scope == "mine":
        return query.filter(Decision.owner_id == user_id)

    if scope == "team":
        report_ids = [
            row.user_id
            for row in (
                session.query(UserSupervisor.user_id)
                .filter(
                    UserSupervisor.tenant_id == tenant_id,
                    UserSupervisor.supervisor_id == user_id,
                    UserSupervisor.effective_to.is_(None),
                )
                .all()
            )
        ]
        if not report_ids:
            return query.filter(Decision.id == uuid.UUID(int=0))  # empty
        return query.filter(Decision.owner_id.in_(report_ids))

    return query  # all_entitled (default)


# ---------------------------------------------------------------------------
# Workflow filter + sort + paginate
# ---------------------------------------------------------------------------


def apply_workflow_filter(query: Query[Decision], workflow_id: str | None) -> Query[Decision]:
    if workflow_id:
        return query.filter(Decision.workflow_id == workflow_id)
    return query


def apply_archetype_filter(query: Query[Decision], archetype_id: str | None) -> Query[Decision]:
    """Narrow to decisions whose ``workflow_id`` belongs to ``archetype_id``.

    Resolves the archetype to its bound programs via the SemanticEngine,
    then filters ``Decision.workflow_id`` against that program-id set.
    An unknown archetype id or one with zero bound programs collapses
    to an empty result — caller surfaces this as "0 decisions in that
    Caseload bucket" rather than 404, since the URL is reachable from
    the Caseload rail and we want graceful empty-states.
    """
    if not archetype_id:
        return query
    from reasonbook.semantic.engine import get_engine

    programs = get_engine().list_programs_by_archetype(archetype_id)
    if not programs:
        return query.filter(Decision.id == uuid.UUID(int=0))  # empty
    return query.filter(Decision.workflow_id.in_([p.profile.id for p in programs]))


_PRIORITY_RANK = {
    "critical": 0,
    "urgent": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
}

# Severity rank for inbox sort. Lower number = higher severity, so
# ASC ordering yields critical → high → medium → low (the user's
# spec phrasing of "severity descending").
_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


def apply_sort(query: Query[Decision], sort: str | None) -> Query[Decision]:
    if sort == "oldest":
        return query.order_by(Decision.created_at.asc())
    if sort == "sla_deadline":
        return query.order_by(Decision.sla_deadline.asc().nullslast())
    if sort == "newest":
        return query.order_by(Decision.created_at.desc())
    if sort == "priority":
        # Priority is a string; sorting alphabetically is wrong, so use a
        # CASE expression. SQLAlchemy's `case()` keeps this DB-agnostic.
        from sqlalchemy import case

        order = case(_PRIORITY_RANK, value=Decision.priority, else_=99)
        return query.order_by(order, Decision.created_at.desc())
    # Default — severity-first inbox sort per Inbox UX round 2:
    #   1. severity DESC (critical → high → medium → low) via rank ASC
    #   2. sla_deadline ASC (nulls last) within each tier
    #   3. created_at DESC tiebreak
    # The "due today" client-side pin from round 1 was removed — the
    # severity-first sort makes it redundant.
    from sqlalchemy import case

    severity_order = case(_SEVERITY_RANK, value=Decision.severity, else_=99)
    return query.order_by(
        severity_order,
        Decision.sla_deadline.asc().nullslast(),
        Decision.created_at.desc(),
    )


def apply_paginate(query: Query[Decision], *, limit: int = 50, offset: int = 0) -> Query[Decision]:
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    return query.limit(limit).offset(offset)
