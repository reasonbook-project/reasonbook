# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter aggregate read API.

GET /api/matters                  list matters visible to caller's tier
GET /api/matters/:matter_id       full matter: fields + nodes + originating decision

Tier scope is enforced via the nodes' participant_org_id: federal sees
all matters; state/recipient see only matters whose tree includes a
node at their participant_org_id.

Matter reads sit alongside the Decisions Inbox — the matter IS a
matter, and the matter list (Register) is the matter list under the
hood (ADR-11 / TENANCY-MODEL §10 step 6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from flask import Blueprint, Response, g, jsonify, make_response, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.decisions.scope import OPEN_STATUSES
from reasonbook.matters.amendment import (
    AmendmentAuthorityError,
    AmendmentError,
    add_recipient_node,
    add_state_node,
    amend_matter_fields,
    amend_node_active_archetypes,
    remove_recipient_node,
    remove_state_node,
)
from reasonbook.matters.service import (
    MatterCreateError,
    RecipientSpec,
    StakeholderSpec,
    create_matter,
)
from reasonbook.models import (
    Decision,
    Matter,
    MatterNode,
    ParticipantOrg,
    RequestForResponse,
    User,
    UserSupervisor,
)

bp = Blueprint("matters", __name__)


def _scope_matter_ids(
    session: Session, *, tier: str, participant_org_id: uuid.UUID | None
) -> set[uuid.UUID] | None:
    """Return the set of matter ids visible to the caller, or None for
    federal (no restriction). state/recipient default-deny on missing
    org per the same chokepoint logic in apply_tier_scope.
    """
    if tier == "federal":
        return None
    if participant_org_id is None:
        return set()
    # Matter is visible if ANY active node in its tree carries the
    # caller's participant_org_id. For recipient, we additionally
    # require the node tier='recipient' (their leaf), but state-tier
    # users see all of their state's chain anyway because they're
    # higher up the tree.
    stmt = (
        select(MatterNode.matter_id)
        .where(
            MatterNode.participant_org_id == participant_org_id,
            MatterNode.removed_at.is_(None),
        )
        .distinct()
    )
    return {row[0] for row in session.execute(stmt).all()}


def _node_dict(node: MatterNode, org_lookup: dict[uuid.UUID, ParticipantOrg]) -> dict[str, Any]:
    org = (
        org_lookup.get(node.participant_org_id)
        if node.participant_org_id is not None
        else None
    )
    return {
        "id": str(node.id),
        "tier": node.tier,
        "parent_node_id": str(node.parent_node_id) if node.parent_node_id else None,
        "participant_org_id": str(node.participant_org_id) if node.participant_org_id else None,
        "participant_org_name": org.display_name if org else None,
        "participant_org_code": org.code if org else None,
        "active_archetypes": list(node.active_archetypes),
        "authority_role": node.authority_role,
        "added_at": node.added_at.isoformat() if node.added_at else None,
        "removed_at": node.removed_at.isoformat() if node.removed_at else None,
        # Per-node funding amount (migration 0042). NULL when not known
        # (synthetic matters) — renderers should hide the edge label.
        "amount": str(node.amount) if node.amount is not None else None,
    }


def _path_preview(
    session: Session,
    matter: Matter,
    nodes: list[MatterNode],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Federal → state → recipient walk for the Register's compact chip line.

    Returns ``(preview, search_labels)``:
      * ``preview`` — 1–3 nodes (in tier order) with the dollar amount
        that arrived at each, sourced from ``MatterNode.amount``.
        The federal node's label is the matter's awarding_agency string.
      * ``search_labels`` — flat list of ALL recipient display_names on
        the matter (prime + every sub). The Register UI joins these into
        the search hay so a sub-recipient name finds the matter even
        when the chip shows the prime.
    """
    by_parent: dict[uuid.UUID, list[MatterNode]] = {}
    federal_root: MatterNode | None = None
    for n in nodes:
        if n.parent_node_id is None and n.tier == "federal":
            federal_root = n
        elif n.parent_node_id is not None:
            by_parent.setdefault(n.parent_node_id, []).append(n)

    if federal_root is None:
        return [], []

    out: list[dict[str, Any]] = [
        {
            "tier": "federal",
            "label": matter.awarding_agency,
            "amount": (
                str(federal_root.amount) if federal_root.amount is not None else None
            ),
        }
    ]

    states = by_parent.get(federal_root.id, [])
    if not states:
        return out, []
    state = states[0]

    recipients = by_parent.get(state.id, [])
    # Sort so the prime recipient (which carries the matter amount per
    # the matters loader's invariant) lands at recipients[0]. Subs have
    # amount=NULL and tie-break by id for determinism.
    recipients = sorted(
        recipients,
        key=lambda n: (
            0 if n.amount is not None else 1,
            -float(n.amount) if n.amount is not None else 0.0,
            str(n.id),
        ),
    )

    # Bulk-load every participant_org we touch (state + all recipients).
    org_ids: set[uuid.UUID] = set()
    if state.participant_org_id:
        org_ids.add(state.participant_org_id)
    for r in recipients:
        if r.participant_org_id:
            org_ids.add(r.participant_org_id)
    org_lookup: dict[uuid.UUID, ParticipantOrg] = {}
    if org_ids:
        org_lookup = {
            o.id: o
            for o in session.query(ParticipantOrg)
            .filter(ParticipantOrg.id.in_(org_ids))
            .all()
        }

    state_org = org_lookup.get(state.participant_org_id) if state.participant_org_id else None
    out.append(
        {
            "tier": "state",
            "label": state_org.display_name if state_org else "State",
            "amount": str(state.amount) if state.amount is not None else None,
        }
    )

    search_labels: list[str] = []
    if recipients:
        r0 = recipients[0]
        r0_org = org_lookup.get(r0.participant_org_id) if r0.participant_org_id else None
        out.append(
            {
                "tier": "recipient",
                "label": r0_org.display_name if r0_org else "Recipient",
                "amount": str(r0.amount) if r0.amount is not None else None,
            }
        )
        for r in recipients:
            if r.participant_org_id:
                org = org_lookup.get(r.participant_org_id)
                if org and org.display_name:
                    search_labels.append(org.display_name)

    return out, search_labels


def _open_signals_by_matter(
    session: Session, matter_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Fetch open alerts grouped by matter_id, highest-severity-first.

    Returns ``{matter_id: [{alert_id, kind, severity, title, body,
    skipped_tier, expected_parent, subject_participant_org_id, source},
    ...]}``. A matter with no open alerts is absent from the dict. Used
    by both the list and detail endpoints so a flagged matter reads
    consistently across surfaces.

    Per docs/architecture/fund-flow-visual-rules.md: the fund-flow
    renderer needs per-signal attribution to a specific node or edge,
    not a single matter-level fault boolean. Returning the full list
    (highest-severity first) lets the frontend paint red on the exact
    element each signal names, while other consumers can still pick
    ``[0]`` for the "highest-severity" summary they want.
    """
    from reasonbook.models import Alert

    if not matter_ids:
        return {}

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    rows = (
        session.query(Alert)
        .filter(Alert.matter_id.in_(matter_ids))
        .filter(Alert.current_status.in_(("new", "reopened")))
        .all()
    )
    by_matter: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for r in rows:
        if r.matter_id is None:
            continue
        signal_ref = r.signal_ref or {}
        subject = r.subject_entity or {}
        # Identity signals (and any other per-node signal) carry the
        # named participant in subject_entity.id — the frontend uses it
        # to attribute the red border to the specific node.
        subject_id = subject.get("id") if isinstance(subject, dict) else None
        by_matter.setdefault(r.matter_id, []).append(
            {
                "alert_id": str(r.id),
                "source": r.source,
                "kind": signal_ref.get("kind"),
                "severity": r.severity,
                "title": r.title,
                "body": r.body,
                "skipped_tier": signal_ref.get("skipped_tier"),
                "expected_parent": signal_ref.get("expected_parent"),
                "subject_participant_org_id": (
                    str(subject_id)
                    if subject_id and subject.get("kind") == "participant_org"
                    else None
                ),
            }
        )

    for sigs in by_matter.values():
        sigs.sort(key=lambda s: severity_order.get(s["severity"], 9))
    return by_matter


def _stages_and_owners_by_matter(
    session: Session, matter_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Batch-derive stage + primary owner for a page of matters.

    Stage priority (a matter carries the most-urgent applicable label):

      1. ``awaiting_response`` — matter has an open RFR
      2. ``in_progress``       — at least one decision in assigned/in_progress
      3. ``awaiting_owner``    — at least one decision with owner_id NULL
                                 OR no decisions at all
      4. ``cleared``           — every decision decided/closed, no open RFR

    Primary owner is the owner of any current in-progress/assigned decision
    on the matter (if any); falls back to the earliest decision's owner.
    Returns ``{matter_id: {stage, owner_id, owner_name}}``.
    """
    if not matter_ids:
        return {}

    decision_rows = session.execute(
        select(
            Decision.matter_id,
            Decision.status,
            Decision.owner_id,
            Decision.created_at,
        ).where(Decision.matter_id.in_(matter_ids))
    ).all()

    per_matter: dict[uuid.UUID, dict[str, Any]] = {}
    for mid, status, owner_id, created_at in decision_rows:
        if mid is None:
            continue
        info = per_matter.setdefault(
            mid,
            {
                "statuses": [],
                "active_owner": None,  # owner of any in_progress/assigned
                "earliest_owner": None,
                "earliest_created": None,
            },
        )
        info["statuses"].append(status)
        if status in ("assigned", "in_progress") and owner_id is not None:
            info["active_owner"] = owner_id
        if owner_id is not None and (
            info["earliest_created"] is None
            or (created_at is not None and created_at < info["earliest_created"])
        ):
            info["earliest_owner"] = owner_id
            info["earliest_created"] = created_at

    # Open RFRs — matter is "awaiting response" if any RFR is open.
    rfr_rows = session.execute(
        select(RequestForResponse.matter_id).where(
            RequestForResponse.matter_id.in_(matter_ids),
            RequestForResponse.status == "open",
        )
    ).all()
    awaiting_rfr = {row[0] for row in rfr_rows if row[0] is not None}

    # Owner name lookup.
    owner_id_set: set[uuid.UUID] = set()
    for info in per_matter.values():
        if info["active_owner"] is not None:
            owner_id_set.add(info["active_owner"])
        elif info["earliest_owner"] is not None:
            owner_id_set.add(info["earliest_owner"])
    owner_names: dict[uuid.UUID, str] = {}
    if owner_id_set:
        rows = (
            session.query(User.id, User.name, User.username)
            .filter(User.id.in_(owner_id_set))
            .all()
        )
        for uid, name, uname in rows:
            owner_names[uid] = name or uname

    result: dict[uuid.UUID, dict[str, Any]] = {}
    for mid in matter_ids:
        info = per_matter.get(mid)
        if mid in awaiting_rfr:
            stage = "awaiting_response"
        elif info is None:
            stage = "awaiting_owner"
        else:
            statuses = info["statuses"]
            if any(s in ("assigned", "in_progress") for s in statuses):
                stage = "in_progress"
            elif any(s == "open" for s in statuses):
                stage = "awaiting_owner"
            elif statuses and all(
                s in ("decided", "closed") for s in statuses
            ):
                stage = "cleared"
            else:
                stage = "awaiting_owner"

        owner_id = None
        if info is not None:
            owner_id = info["active_owner"] or info["earliest_owner"]
        result[mid] = {
            "stage": stage,
            "owner_id": str(owner_id) if owner_id else None,
            "owner_name": owner_names.get(owner_id) if owner_id else None,
        }
    return result


def _matter_summary(
    matter: Matter,
    *,
    node_count: int | None = None,
    path_preview: list[dict[str, Any]] | None = None,
    search_labels: list[str] | None = None,
    signals: list[dict[str, Any]] | None = None,
    stage: str | None = None,
    owner_id: str | None = None,
    owner_name: str | None = None,
) -> dict[str, Any]:
    # Signals list is highest-severity first. `signal` (singular) is the
    # top of the list — preserved for callers that only want the primary
    # summary (Register chip color, list-view filters).
    signals = signals or []
    signal = signals[0] if signals else None
    return {
        "id": str(matter.id),
        "program_id": matter.program_id,
        "federal_archetype": matter.federal_archetype,
        "awarding_agency": matter.awarding_agency,
        "amount_obligated": (
            str(matter.amount_obligated) if matter.amount_obligated is not None else None
        ),
        "period_label": matter.period_label,
        "terms": matter.terms,
        "retention_months": matter.retention_months,
        "planned_disbursement_at": (
            matter.planned_disbursement_at.isoformat()
            if matter.planned_disbursement_at
            else None
        ),
        "originating_decision_id": (
            str(matter.originating_decision_id)
            if matter.originating_decision_id is not None
            else None
        ),
        "created_at": matter.created_at.isoformat() if matter.created_at else None,
        "node_count": node_count,
        # Denormalised path preview for compact Register rendering — the
        # 1-3 nodes that anchor the visual fund-flow chip line. Returns
        # `[{tier, label, amount}, ...]` in flow order. The full node
        # tree is on `GET /api/matters/<id>`.
        "path_preview": path_preview or [],
        # Every recipient display_name on the matter (prime + all subs)
        # — used by the Register's client-side search hay so a sub
        # name matches even when the chip shows the prime.
        "search_labels": search_labels or [],
        # Highest-severity open alert linked to this matter, or null.
        # Carries `kind` (e.g. "tier_skip"), `severity`, `title`, plus
        # tier-skip-specific metadata. Renderers use it for the red
        # badge + Signals-only filter. For fund-flow attribution (which
        # element each signal names), consumers should read `signals`.
        "signal": signal,
        # All open signals on the matter, highest-severity first. Powers
        # per-element fund-flow attribution per
        # docs/architecture/fund-flow-visual-rules.md. Empty list when
        # no signals are open.
        "signals": signals,
        # Batch-derived (see `_stages_and_owners_by_matter`) so the
        # /matters rail can render stage dot + owner initials on the
        # leaf, and Stage / Owner facets can narrow without a second
        # round-trip. Nullable for endpoints (single-item POST returns)
        # that skip the batch derivation.
        "stage": stage,
        "owner_id": owner_id,
        "owner_name": owner_name,
    }


@bp.get("/matters/meta")
@require_auth
def matter_meta() -> tuple[Response, int]:
    """Register meta bar — total matters, exposure, open signals.

    Federal tier sees all matters; state/recipient see only what their
    apply_tier_scope chokepoint resolves to. Counts respect that scope
    so the Register's headline numbers track what the caller can see.
    """
    from sqlalchemy import func as sql_func

    from reasonbook.models import Alert

    auth = g.auth
    with session_scope() as session:
        scope_ids = _scope_matter_ids(
            session,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
        )

        matters_q = session.query(Matter)
        if scope_ids is not None:
            if not scope_ids:
                return (
                    jsonify(
                        {
                            "matters": 0,
                            "exposure": "0",
                            "signals": 0,
                        }
                    ),
                    200,
                )
            matters_q = matters_q.filter(Matter.id.in_(scope_ids))

        total = matters_q.count()
        exposure = (
            matters_q.with_entities(
                sql_func.coalesce(sql_func.sum(Matter.amount_obligated), 0)
            )
            .scalar()
            or 0
        )

        # Open signals — "actionable" status alerts. Scope-filtered when
        # the alerts table later carries matter/node refs; for v1 we
        # report a tenant-wide count which matches the rail badge.
        signals = (
            session.query(Alert)
            .filter(Alert.tenant_id == auth.tenant)
            .filter(Alert.current_status.in_(("new", "reopened")))
            .count()
        )

        return (
            jsonify(
                {
                    "matters": int(total),
                    "exposure": str(exposure),
                    "signals": int(signals),
                }
            ),
            200,
        )


# ---------------------------------------------------------------------------
# Matters-first Inbox (MVP-BUILD-QUEUE P1)
# ---------------------------------------------------------------------------
#
# The Inbox groups every visible matter into one of three bands:
#
#   Incoming  — Planned disbursements arriving within the horizon window
#               (matters.planned_disbursement_at set, no open decisions,
#               not at risk).
#   Inflight  — Matters with at least one open decision. Not at risk.
#   At risk   — Wins ties. A matter appearing here does NOT also appear
#               in the other bands. Triggers:
#                 · structural gap in fund flow (tier_skip, ownership_gap)
#                 · an open adverse signal at severity high/critical
#                 · any open decision past its sla_deadline
#
# Bands are derived server-side so the rail's per-program counts and the
# main band counts use one classifier — no drift between the API and
# the frontend.

_AT_RISK_SIGNAL_KINDS = frozenset(
    {"tier_skip", "ownership_gap", "chain_integrity"}
)


def _horizon_window(horizon: str) -> timedelta:
    """Translate the horizon toggle into a lookahead window.

    30d / 90d are literal; ``fy`` approximates the remainder of the
    federal fiscal year with a generous 365-day cap so the Incoming band
    stays useful without an FY-boundary query.
    """
    if horizon == "30d":
        return timedelta(days=30)
    if horizon == "fy":
        return timedelta(days=365)
    return timedelta(days=90)  # default


def _scope_owner_ids(
    session: Session, *, scope: str, user_id: uuid.UUID, tenant_id: str
) -> list[uuid.UUID] | None:
    """Which owner_ids count for the given scope.

    * ``mine``  — just the caller.
    * ``team``  — caller + direct reports (inclusive; matches how
                  Linear / Asana / etc treat "team queue"). A lone
                  officer with no reports sees the same as mine.
                  Peer-inclusive team semantics ("everyone in my
                  agency") is a separate call — see backlog
                  ``team-scope-includes-peers``.
    * ``all_agency`` (default) — no owner filter; returns None.

    An empty list means "no visible matters" and short-circuits the
    endpoint.
    """
    if scope == "mine":
        return [user_id]
    if scope == "team":
        report_ids = [
            row.user_id
            for row in session.query(UserSupervisor.user_id)
            .filter(
                UserSupervisor.tenant_id == tenant_id,
                UserSupervisor.supervisor_id == user_id,
                UserSupervisor.effective_to.is_(None),
            )
            .all()
        ]
        # Include the caller so "your team's queue" reads the way users
        # expect — with your own contribution alongside your reports'.
        return [user_id, *report_ids]
    return None  # all_agency (default)


@bp.get("/matters/inbox")
@require_auth
def matters_inbox() -> tuple[Response, int]:
    """Matters-first Inbox — three bands + rail counts.

    Query params:
      scope    mine | team | all_agency (default: mine)
      horizon  30d | 90d | fy (default: 90d) — sets the Incoming lookahead
      program  optional program_id to narrow bands + counts

    Response shape:
      { horizon_end, band_counts, program_counts, bands }
    """
    auth = g.auth
    args = request.args
    scope = args.get("scope", "mine")
    horizon = args.get("horizon", "90d")
    program_filter = args.get("program") or None

    now = datetime.now(UTC)
    horizon_end = now + _horizon_window(horizon)

    with session_scope() as session:
        # Tier scope first — federal sees all; state/recipient constrained
        # to matters where their org has an active node.
        scope_ids = _scope_matter_ids(
            session,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
        )

        empty_response = {
            "horizon": horizon,
            "horizon_end": horizon_end.isoformat(),
            "band_counts": {"incoming": 0, "inflight": 0, "at_risk": 0},
            "program_counts": {},
            "bands": {"incoming": [], "inflight": [], "at_risk": []},
        }

        if scope_ids is not None and not scope_ids:
            return jsonify(empty_response), 200

        # Owner-scope filter — collect the matter ids where a scoped
        # owner owns at least one decision. Applied per-band below:
        # Inflight + At-risk narrow to owned matters; Incoming stays
        # unfiltered because it's the shared calendar of upcoming
        # disbursements, not a personal-ownership queue.
        owner_ids = _scope_owner_ids(
            session,
            scope=scope,
            user_id=uuid.UUID(auth.sub),
            tenant_id=auth.tenant,
        )
        owned_matter_ids: set[uuid.UUID] | None
        if owner_ids is None:
            owned_matter_ids = None  # all_agency — no filter
        elif not owner_ids:
            owned_matter_ids = set()
        else:
            owned_matter_ids = {
                row[0]
                for row in session.execute(
                    select(Decision.matter_id)
                    .where(
                        Decision.owner_id.in_(owner_ids),
                        Decision.matter_id.is_not(None),
                    )
                    .distinct()
                ).all()
                if row[0] is not None
            }

        # Base matter query — respects tier scope + owner scope + program.
        q = session.query(Matter)
        if scope_ids is not None:
            q = q.filter(Matter.id.in_(scope_ids))
        if program_filter:
            q = q.filter(Matter.program_id == program_filter)
        matters = q.all()
        matter_ids = [m.id for m in matters]

        if not matter_ids:
            return jsonify(empty_response), 200

        # Open decisions per matter — inflight signal + oldest-age +
        # stage pill for the row card.
        open_dec_rows = session.execute(
            select(
                Decision.matter_id,
                Decision.id,
                Decision.status,
                Decision.sla_deadline,
                Decision.created_at,
                Decision.owner_id,
                Decision.title,
            )
            .where(
                Decision.matter_id.in_(matter_ids),
                Decision.status.in_(OPEN_STATUSES),
            )
            .order_by(Decision.created_at.asc())
        ).all()
        open_by_matter: dict[uuid.UUID, list[dict[str, Any]]] = {}
        for row in open_dec_rows:
            open_by_matter.setdefault(row.matter_id, []).append(
                {
                    "id": row.id,
                    "status": row.status,
                    "sla_deadline": row.sla_deadline,
                    "created_at": row.created_at,
                    "owner_id": row.owner_id,
                    "title": row.title,
                }
            )

        # Owner name lookup for the Inflight owner-block.
        owner_id_set = {
            d["owner_id"]
            for decs in open_by_matter.values()
            for d in decs
            if d["owner_id"] is not None
        }
        owner_names: dict[uuid.UUID, str] = {}
        if owner_id_set:
            rows = (
                session.query(User.id, User.name, User.username)
                .filter(User.id.in_(owner_id_set))
                .all()
            )
            for uid, name, uname in rows:
                owner_names[uid] = name or uname

        # Highest-severity open alert per matter — reused for at-risk
        # classification + the row's risk_reason line.
        signals_by_matter = _open_signals_by_matter(session, matter_ids)

        # Node prefetch (path preview + count) — one query, group in-Python.
        node_rows = (
            session.query(MatterNode)
            .filter(MatterNode.matter_id.in_(matter_ids), MatterNode.removed_at.is_(None))
            .all()
        )
        nodes_by_matter: dict[uuid.UUID, list[MatterNode]] = {}
        for n in node_rows:
            nodes_by_matter.setdefault(n.matter_id, []).append(n)

        bands: dict[str, list[dict[str, Any]]] = {
            "incoming": [],
            "inflight": [],
            "at_risk": [],
        }
        program_counts: dict[str, int] = {}

        scope_owner_id_set: set[uuid.UUID] | None = (
            set(owner_ids) if owner_ids is not None else None
        )
        for matter in matters:
            open_decs = open_by_matter.get(matter.id, [])
            matter_signals = signals_by_matter.get(matter.id, [])
            top_signal = matter_signals[0] if matter_signals else None

            band, row_extras = _classify_matter(
                matter=matter,
                open_decisions=open_decs,
                signal=top_signal,
                now=now,
                horizon_end=horizon_end,
                owner_names=owner_names,
                scope_owner_ids=scope_owner_id_set,
            )
            if band is None:
                continue

            # Owner-scope narrows Inflight + At-risk only; Incoming is
            # the shared upcoming-disbursement calendar and isn't
            # personal-workload-filtered.
            if (
                band in ("inflight", "at_risk")
                and owned_matter_ids is not None
                and matter.id not in owned_matter_ids
            ):
                continue

            program_counts[matter.program_id] = (
                program_counts.get(matter.program_id, 0) + 1
            )

            nodes = nodes_by_matter.get(matter.id, [])
            preview, search_labels = _path_preview(session, matter, nodes)
            row = _matter_summary(
                matter,
                node_count=len(nodes),
                path_preview=preview,
                search_labels=search_labels,
                signals=matter_signals,
            )
            row["band"] = band
            row.update(row_extras)
            bands[band].append(row)

        # Order rows within each band for the demo path.
        bands["incoming"].sort(
            key=lambda r: r.get("planned_disbursement_at") or ""
        )
        bands["inflight"].sort(
            key=lambda r: r.get("oldest_open_age_days") or 0, reverse=True
        )
        bands["at_risk"].sort(
            key=lambda r: r.get("risk_age_days") or 0, reverse=True
        )

        return (
            jsonify(
                {
                    "horizon": horizon,
                    "horizon_end": horizon_end.isoformat(),
                    "band_counts": {
                        "incoming": len(bands["incoming"]),
                        "inflight": len(bands["inflight"]),
                        "at_risk": len(bands["at_risk"]),
                    },
                    "program_counts": program_counts,
                    "bands": bands,
                }
            ),
            200,
        )


def _classify_matter(
    *,
    matter: Matter,
    open_decisions: list[dict[str, Any]],
    signal: dict[str, Any] | None,
    now: datetime,
    horizon_end: datetime,
    owner_names: dict[uuid.UUID, str],
    scope_owner_ids: set[uuid.UUID] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Return (band, row_extras) for a single matter.

    band is one of 'incoming' | 'inflight' | 'at_risk' or None to skip
    the matter entirely (no open work + no calendar entry).

    At-risk wins ties — the queue doc's rule: "a Matter that qualifies
    here does not appear in the other bands".

    ``scope_owner_ids`` is the set of user_ids the caller's scope
    resolves to (Jamie for scope=mine; reports for scope=team; None for
    all_agency). When present, the Inflight card's "lead decision" is
    picked from decisions owned by that set — so "your queue" shows
    YOUR decision on shared matters instead of a teammate's older row.
    """
    # --- At-risk detection ---------------------------------------------------
    risk_reasons: list[str] = []
    risk_kind: str | None = None

    if signal is not None:
        kind = signal.get("kind")
        severity = signal.get("severity")
        if kind in _AT_RISK_SIGNAL_KINDS:
            risk_reasons.append(signal.get("title") or "Structural gap in fund flow")
            risk_kind = kind
        elif severity in ("critical", "high"):
            risk_reasons.append(signal.get("title") or f"Adverse signal ({severity})")
            risk_kind = "adverse_signal"

    overdue_decisions = [
        d for d in open_decisions if d["sla_deadline"] and d["sla_deadline"] < now
    ]
    if overdue_decisions:
        overdue_days = max(
            int((now - d["sla_deadline"]).total_seconds() // 86400)
            for d in overdue_decisions
        )
        risk_reasons.append(
            f"Decision past SLA by {overdue_days} day{'s' if overdue_days != 1 else ''}"
        )
        risk_kind = risk_kind or "sla_breach"

    if risk_reasons:
        oldest = min(d["created_at"] for d in open_decisions) if open_decisions else None
        risk_age_days = (
            int((now - oldest).total_seconds() // 86400) if oldest else 0
        )
        return "at_risk", {
            "risk_reason": {
                "kind": risk_kind,
                "text": " · ".join(risk_reasons),
            },
            "risk_age_days": risk_age_days,
        }

    # --- Inflight ------------------------------------------------------------
    if open_decisions:
        # Prefer decisions owned by the scope when picking the lead so
        # the row's stage + owner + age reflect the caller's work, not
        # a teammate's older row on a shared matter. Falls back to the
        # oldest overall when the scope owns no decision on the matter
        # (shouldn't happen at inflight because the endpoint already
        # narrowed to owned matters — defence-in-depth for future
        # callers that skip the pre-filter).
        scoped_decisions = (
            [d for d in open_decisions if d["owner_id"] in scope_owner_ids]
            if scope_owner_ids
            else open_decisions
        )
        pool = scoped_decisions if scoped_decisions else open_decisions
        lead = min(pool, key=lambda d: d["created_at"])
        oldest_age_days = int((now - lead["created_at"]).total_seconds() // 86400)
        stage = _stage_from_status(lead["status"])
        owner_name = owner_names.get(lead["owner_id"]) if lead["owner_id"] else None
        return "inflight", {
            "stage": stage,
            "owner_id": (str(lead["owner_id"]) if lead["owner_id"] else None),
            "owner_name": owner_name,
            "oldest_open_age_days": oldest_age_days,
            "lead_decision_title": lead["title"],
        }

    # --- Incoming ------------------------------------------------------------
    # Skip past-dated planned disbursements — those are inflight or
    # closed matters, not upcoming.
    if (
        matter.planned_disbursement_at is not None
        and now <= matter.planned_disbursement_at <= horizon_end
    ):
        # Readiness — for MVP: Ready if no open decisions AND no signal,
        # Pending otherwise. Real control-point readiness (mockup shows
        # "3 pre-payment controls pending") comes from ControlPoint state
        # in a follow-up.
        readiness = {"state": "ready", "pending_count": 0}
        if signal is not None:
            readiness = {"state": "pending", "pending_count": 1}
        return "incoming", {"readiness": readiness}

    return None, {}


def _stage_from_status(status: str) -> str:
    """Map decision status to the Inflight card's stage pill.

    'decision' — the operator still owes a decision (open / assigned /
                 in_progress before any action work).
    'action'   — the decision has been made; work is executing.
    'outcome'  — the action is done; outcome capture is pending.
    """
    if status in ("open", "assigned", "in_progress"):
        return "decision"
    if status == "decided":
        return "action"
    return "outcome"


@bp.get("/matters")
@require_auth
def list_matters() -> tuple[Response, int]:
    auth = g.auth
    with session_scope() as session:
        scope_ids = _scope_matter_ids(
            session,
            tier=auth.tier,
            participant_org_id=(
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            ),
        )
        q = session.query(Matter)
        if scope_ids is not None:
            if not scope_ids:
                return jsonify({"items": []}), 200
            q = q.filter(Matter.id.in_(scope_ids))

        matters = q.order_by(Matter.created_at.desc()).all()
        # Batch-fetch open signals for the whole page in one query.
        signals_by_matter = _open_signals_by_matter(
            session, [b.id for b in matters]
        )
        # Batch-derive stage + primary owner so the rail leaf renders
        # stage dot + owner initials and Stage/Owner facets can narrow
        # without a second round-trip.
        stages_by_matter = _stages_and_owners_by_matter(
            session, [b.id for b in matters]
        )
        # Batch-fetch decision numbers so the tree search hay picks up
        # DEC-* lookups (searching "DEC-0079" should find the matter
        # that contains that decision, not return "no matters match").
        matter_ids = [b.id for b in matters]
        decision_numbers_by_matter: dict[uuid.UUID, list[str]] = {}
        commitment_count_by_matter: dict[uuid.UUID, int] = {}
        if matter_ids:
            rows = session.execute(
                select(Decision.matter_id, Decision.decision_number)
                .where(Decision.matter_id.in_(matter_ids))
            ).all()
            for mid, dn in rows:
                if mid is None or not dn:
                    continue
                decision_numbers_by_matter.setdefault(mid, []).append(dn)
            # Commitment count powers the recipient watchlist's "Awaiting
            # / Recently submitted" partition on the frontend without a
            # second round-trip.
            from sqlalchemy import func as _sql_func

            commitment_rows = session.execute(
                select(Decision.matter_id, _sql_func.count(Decision.id))
                .where(
                    Decision.matter_id.in_(matter_ids),
                    Decision.is_commitment.is_(True),
                )
                .group_by(Decision.matter_id)
            ).all()
            for mid, count in commitment_rows:
                if mid is not None:
                    commitment_count_by_matter[mid] = int(count)

        items = []
        for b in matters:
            # Pull active nodes for the matter once — gives us both the
            # count + the path preview without a second query per row.
            nodes = (
                session.query(MatterNode)
                .filter_by(matter_id=b.id, removed_at=None)
                .all()
            )
            preview, search_labels = _path_preview(session, b, nodes)
            stage_info = stages_by_matter.get(b.id) or {}
            summary = _matter_summary(
                b,
                node_count=len(nodes),
                path_preview=preview,
                search_labels=search_labels,
                signals=signals_by_matter.get(b.id, []),
                stage=stage_info.get("stage"),
                owner_id=stage_info.get("owner_id"),
                owner_name=stage_info.get("owner_name"),
            )
            # Decision numbers extend the client-side search hay but
            # NOT the tree label. `search_labels` is also the source of
            # matterLabel(); overloading it with DEC-* strings would
            # relabel the tree leaf as a decision id instead of the
            # recipient name.
            summary["search_terms"] = decision_numbers_by_matter.get(b.id, [])
            summary["commitment_count"] = commitment_count_by_matter.get(b.id, 0)
            items.append(summary)
        return jsonify({"items": items}), 200


@bp.get("/matters/<matter_id>")
@require_auth
def get_matter(matter_id: str) -> tuple[Response, int]:
    auth = g.auth
    try:
        bid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "invalid matter_id"}), 400

    with session_scope() as session:
        matter = session.get(Matter, bid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404

        # Tier scope: state/recipient must have a node in the matter.
        if auth.tier != "federal":
            org_id = (
                uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
            )
            if org_id is None:
                return jsonify({"error": "forbidden"}), 403
            has_node = (
                session.query(MatterNode)
                .filter_by(
                    matter_id=matter.id,
                    participant_org_id=org_id,
                    removed_at=None,
                )
                .first()
                is not None
            )
            if not has_node:
                return jsonify({"error": "forbidden"}), 403

        nodes = (
            session.query(MatterNode)
            .filter_by(matter_id=matter.id)
            .order_by(MatterNode.added_at.asc())
            .all()
        )

        # Bulk-load participant_org rows referenced by the nodes.
        org_ids = {n.participant_org_id for n in nodes if n.participant_org_id is not None}
        org_lookup: dict[uuid.UUID, ParticipantOrg] = {}
        if org_ids:
            org_lookup = {
                o.id: o
                for o in session.query(ParticipantOrg).filter(ParticipantOrg.id.in_(org_ids)).all()
            }

        active_nodes = [n for n in nodes if n.removed_at is None]
        historical_nodes = [n for n in nodes if n.removed_at is not None]

        # Every decision linked to this matter (per the Matter = collection-
        # of-decision-records framing in SURFACE-USER-STORIES). Ordered
        # by created_at so the chronology reads top→bottom. Includes the
        # originating decision as a regular member of the list; the
        # `originating_decision_id` on the matter marks WHICH entry is
        # the originating one.
        decision_rows = (
            session.query(Decision)
            .filter(Decision.matter_id == matter.id)
            .order_by(Decision.created_at.asc())
            .all()
        )
        decisions_payload = [
            {
                "id": str(d.id),
                "decision_number": d.decision_number,
                "decision_type": d.decision_type,
                "status": d.status,
                "title": d.title,
                "priority": d.priority,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                "selected_option": d.selected_option,
                "outcome_text": d.outcome_text,
                "is_originating": d.id == matter.originating_decision_id,
                # Optional tier hint from the matter node the decision
                # attaches to — lets the UI annotate "federal · originating"
                # vs "state · amendment" without a separate lookup.
                "matter_node_id": (
                    str(d.matter_node_id) if d.matter_node_id else None
                ),
                # Signal source — lets the UI classify decisions into
                # tier-accept vs investigative-action buckets without
                # parsing titles. Values include 'tier_accept',
                # 'federal_seed_dev', 'alert.flow_graph.tier_skip',
                # 'manual', etc.
                "signal_source": d.signal_source,
                # Evidence references — JSON list of arbitrary shape
                # (typically {kind, ref} entries). Feeds the composite
                # card's Evidence drawer.
                "evidence_refs": d.evidence_refs,
                # Commitment marker (migration 0054). Case-file §3
                # badges the row differently when set; tier-accept and
                # commitment coexist without cross-linking in A0.
                "is_commitment": d.is_commitment,
                "originating_party_name": d.originating_party_name,
                # Structured response payload — powers the Commitment
                # integrity card (attestations, signatory, prompt type).
                # NULL on non-commitment rows.
                "response_shape": d.response_shape,
                # RFR reference (Phase A0: text stand-in for the FK that
                # lands with the requests_for_response model).
                "in_response_to": d.in_response_to,
            }
            for d in decision_rows
        ]

        # Legacy convenience: keep `originating_decision` on the response
        # so existing callers don't break. New consumers should use the
        # `decisions[]` list and check `is_originating`.
        originating: dict[str, Any] | None = None
        if matter.originating_decision_id is not None:
            d = session.get(Decision, matter.originating_decision_id)
            if d is not None:
                originating = {
                    "id": str(d.id),
                    "decision_number": d.decision_number,
                    "status": d.status,
                    "title": d.title,
                }

        signals_by_matter = _open_signals_by_matter(session, [matter.id])
        body = _matter_summary(
            matter,
            node_count=len(active_nodes),
            signals=signals_by_matter.get(matter.id, []),
        )
        body["nodes"] = [_node_dict(n, org_lookup) for n in active_nodes]
        body["historical_nodes"] = [_node_dict(n, org_lookup) for n in historical_nodes]
        body["originating_decision"] = originating
        body["decisions"] = decisions_payload
        return jsonify(body), 200


@bp.get("/matters/<matter_id>/case-file")
@require_auth
def export_matter_case_file(matter_id: str) -> Response:
    """Stream the matter case-file PDF as a download.

    Per SURFACE-USER-STORIES, the case file is the artefact that
    travels — self-contained, tamper-evident, verifiable without DP
    credentials. Tier scope mirrors GET /matters/<id>: federal sees
    all, state/recipient see only matters their node tree includes.
    """
    try:
        bid = uuid.UUID(matter_id)
    except ValueError:
        resp = jsonify({"error": "invalid matter_id"})
        resp.status_code = 400
        return resp

    auth = g.auth
    with session_scope() as session:
        matter = session.get(Matter, bid)
        if matter is None:
            resp = jsonify({"error": "matter not found"})
            resp.status_code = 404
            return resp
        if auth.tier != "federal":
            org_id = (
                uuid.UUID(auth.participant_org_id)
                if auth.participant_org_id
                else None
            )
            if org_id is None:
                resp = jsonify({"error": "forbidden"})
                resp.status_code = 403
                return resp
            has_node = (
                session.query(MatterNode)
                .filter_by(
                    matter_id=matter.id,
                    participant_org_id=org_id,
                    removed_at=None,
                )
                .first()
                is not None
            )
            if not has_node:
                resp = jsonify({"error": "forbidden"})
                resp.status_code = 403
                return resp
        matter_short = matter.id.hex[:8]

    from reasonbook.reports import generate_matter_case_file_pdf

    pdf_bytes = generate_matter_case_file_pdf(bid)
    if not pdf_bytes:
        resp = jsonify({"error": "matter not found"})
        resp.status_code = 404
        return resp

    resp = make_response(pdf_bytes)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="matter-case-file-{matter_short}.pdf"'
    )
    return resp


@bp.post("/matters")
@require_auth
def create_matter_route() -> tuple[Response, int]:
    """Federal-tier matter create — wraps reasonbook.matters.service.create_matter.

    Body:

        { "program_id": "cdbg",
          "awarding_agency": "HUD",
          "amount_obligated": "12000000.00",
          "period_label": "FY26",
          "terms": "...",
          "federal_application_ref": "HUD-...",
          "states": [{"participant_org_id": "<uuid>", ...}],
          "recipients": [{"parent_state_org_id": "<uuid>",
                          "participant_org_id": "<uuid>", ...}] }

    Federal-only — service rejects non-federal actors via the User
    row's tier column on a downstream amendment, but create itself is
    open to any authenticated federal-tier user. Idempotent on the
    (program_id, awarding_agency, period_label, federal_application_ref)
    tuple; replays return the existing matter.
    """
    auth = g.auth
    if auth.tier != "federal":
        return jsonify({"error": "forbidden", "detail": "federal-tier only"}), 403

    body = request.get_json(silent=True) or {}
    required = [
        "program_id",
        "awarding_agency",
        "amount_obligated",
        "period_label",
        "terms",
        "federal_application_ref",
    ]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": "missing_fields", "detail": missing}), 400

    from decimal import Decimal, InvalidOperation

    try:
        amount = Decimal(str(body["amount_obligated"]))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "invalid amount_obligated"}), 400

    states_raw = body.get("states") or []
    recipients_raw = body.get("recipients") or []

    try:
        states = [
            StakeholderSpec(
                participant_org_id=uuid.UUID(s["participant_org_id"]),
                active_archetypes=s.get("active_archetypes"),
                authority_role=s.get("authority_role"),
            )
            for s in states_raw
        ]
        recipients = [
            RecipientSpec(
                parent_state_org_id=uuid.UUID(r["parent_state_org_id"]),
                participant_org_id=uuid.UUID(r["participant_org_id"]),
                active_archetypes=r.get("active_archetypes"),
                authority_role=r.get("authority_role"),
            )
            for r in recipients_raw
        ]
    except (KeyError, ValueError) as exc:
        return jsonify({"error": "invalid spec", "detail": str(exc)}), 400

    with session_scope() as session:
        try:
            matter = create_matter(
                program_id=body["program_id"],
                awarding_agency=body["awarding_agency"],
                amount_obligated=amount,
                period_label=body["period_label"],
                terms=body["terms"],
                federal_application_ref=body["federal_application_ref"],
                states=states,
                recipients=recipients,
                actor_user_id=uuid.UUID(auth.sub),
                tenant_id=auth.tenant,
                session=session,
            )
        except MatterCreateError as exc:
            return jsonify({"error": "create_failed", "detail": str(exc)}), 400

        session.flush()
        node_count = (
            session.query(MatterNode)
            .filter_by(matter_id=matter.id, removed_at=None)
            .count()
        )
        return jsonify(_matter_summary(matter, node_count=node_count)), 201


@bp.get("/participant_orgs")
@require_auth
def list_participant_orgs() -> tuple[Response, int]:
    """List participant_orgs available for the create-matter drawer.

    Optional ``kind`` query param filters to 'state' or 'recipient'.
    Open to any authenticated user — orgs are public records, not
    tenant-scoped.
    """
    kind = request.args.get("kind")
    if kind is not None and kind not in ("state", "recipient"):
        return jsonify({"error": "kind must be 'state' or 'recipient'"}), 400

    with session_scope() as session:
        q = session.query(ParticipantOrg).order_by(ParticipantOrg.display_name.asc())
        if kind:
            q = q.filter(ParticipantOrg.kind == kind)
        items = [
            {
                "id": str(o.id),
                "kind": o.kind,
                "display_name": o.display_name,
                "code": o.code,
            }
            for o in q.all()
        ]
        return jsonify({"items": items}), 200


@bp.post("/matters/<matter_id>/claim")
@require_auth
def claim_matter(matter_id: str) -> tuple[Response, int]:
    """Take over an entire matter — claim every workable Decision at once.

    "Workable" = status in ('open', 'assigned', 'in_progress') AND not a
    party commitment. Terminal decisions (decided, closed, deferred,
    escalated) and commitments (is_commitment=True) are skipped — the
    action is about picking up the operational work, not rewriting the
    ledger.

    Decisions unowned OR owned by someone else are transferred to the
    caller in one shot. Each transition writes a decision_events row so
    the audit trail preserves the ownership change even though the
    matter-level UI collapsed it into one button click. A
    `bulk_operation_id` tag groups them all so audit can reconstruct
    the batch.

    Idempotent: a decision already owned by the caller in 'in_progress'
    is left alone. The response reports { claimed, transferred, skipped }
    counts so the UI can render an honest confirmation.
    """
    from reasonbook.decisions.manager import claim_decision

    auth = g.auth
    try:
        mid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "invalid matter_id"}), 400

    caller_id = uuid.UUID(auth.sub)
    bulk_op_id = uuid.uuid4()
    now = datetime.now(UTC)

    with session_scope() as session:
        matter = session.get(Matter, mid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404

        workable_statuses = ("open", "assigned", "in_progress")
        workable = (
            session.query(Decision)
            .filter(
                Decision.matter_id == mid,
                Decision.status.in_(workable_statuses),
                Decision.is_commitment.is_(False),
            )
            .all()
        )

        claimed: list[str] = []
        transferred: list[str] = []
        skipped_already_mine: list[str] = []

        for d in workable:
            if d.owner_id == caller_id and d.status == "in_progress":
                skipped_already_mine.append(d.decision_number)
                continue

            if d.owner_id is None or d.status in ("open", "assigned"):
                # Standard claim — routes through the manager so
                # authority snapshot + escalation path get computed.
                claim_decision(
                    decision_id=d.id,
                    user_id=caller_id,
                    bulk_operation_id=bulk_op_id,
                    session=session,
                )
                claimed.append(d.decision_number)
            else:
                # in_progress owned by someone else — direct transfer.
                # claim_decision's TRANSITIONS forbid in_progress→in_progress
                # (correct default), so we handle transfer here inline with
                # a distinct event action for the audit trail.
                old_owner = d.owner_id
                d.owner_id = caller_id
                d.acknowledged_at = now
                _log_ownership_transfer(
                    session,
                    decision=d,
                    from_user=old_owner,
                    to_user=caller_id,
                    bulk_operation_id=bulk_op_id,
                )
                transferred.append(d.decision_number)

        session.flush()

        return (
            jsonify(
                {
                    "matter_id": str(mid),
                    "bulk_operation_id": str(bulk_op_id),
                    "claimed": claimed,
                    "transferred": transferred,
                    "skipped_already_mine": skipped_already_mine,
                    "total_touched": len(claimed) + len(transferred),
                }
            ),
            200,
        )


def _log_ownership_transfer(
    session: Session,
    *,
    decision: Decision,
    from_user: uuid.UUID | None,
    to_user: uuid.UUID,
    bulk_operation_id: uuid.UUID,
) -> None:
    """Write a decision_events row for a matter-level ownership transfer.

    Distinct action ('ownership_transferred') so audit queries can
    separate "claimed an unowned decision" from "grabbed one out of a
    colleague's hands". Both are legitimate; both leave a trail.
    """
    from reasonbook.models import DecisionEvent

    session.add(
        DecisionEvent(
            id=uuid.uuid4(),
            decision_id=decision.id,
            tenant_id=decision.tenant_id,
            workflow_id=decision.workflow_id,
            user_id=to_user,
            action="ownership_transferred",
            old_status=decision.status,
            new_status=decision.status,
            event_metadata={
                "bulk_operation_id": str(bulk_operation_id),
                "from_user_id": str(from_user) if from_user else None,
                "to_user_id": str(to_user),
            },
        )
    )


@bp.post("/matters/<matter_id>/recipient-response")
@require_auth
def recipient_response(matter_id: str) -> tuple[Response, int]:
    """Submit an external-party response as a commitment Decision.

    MVP-slice (backlog A0). Federal-proxy path: the authenticated caller
    (a federal PM) is the submitter; the response is attributed to
    ``originating_party_name`` in the ledger. Real recipient auth
    replaces the proxy in Phase B (invite-mfa).

    Body shape (spec §6):

        { "originating_party_name": "Stanford University",
          "in_response_to":        "RFR-2026-04-2118",  // optional
          "response_shape": {
            "prompt_type":       "accept_scope",
            "accepted":          "as_issued" | "with_exceptions" | "declined",
            "exceptions":        null | "<text>",
            "signatory_name":    "Dr. Ellen Weiss",
            "signatory_title":   "Associate VP, Research",
            "attestations":      ["authorized_to_bind", "understands_commitment"],
            "attachments":       []
          }
        }

    Response: ``201`` with the created Decision summary.

    Attestation rule (spec §6): both attestations MUST be present in
    ``response_shape.attestations`` or the write is rejected — the two
    checkboxes on the form are load-bearing legal signal, not decoration.
    """
    from reasonbook.decisions.manager import create_commitment_decision

    auth = g.auth
    try:
        mid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "invalid matter_id"}), 400

    body = request.get_json(silent=True) or {}
    originating_party_name = (body.get("originating_party_name") or "").strip()
    if not originating_party_name:
        return jsonify({"error": "missing_field", "detail": "originating_party_name"}), 400

    response_shape = body.get("response_shape") or {}
    if not isinstance(response_shape, dict):
        return jsonify({"error": "invalid response_shape"}), 400

    required_shape_fields = ("accepted", "signatory_name", "signatory_title", "attestations")
    missing = [k for k in required_shape_fields if not response_shape.get(k)]
    if missing:
        return jsonify({"error": "missing_response_fields", "detail": missing}), 400

    attestations = response_shape.get("attestations") or []
    required_attestations = {"authorized_to_bind", "understands_commitment"}
    if not required_attestations.issubset(set(attestations)):
        return (
            jsonify(
                {
                    "error": "missing_attestations",
                    "detail": sorted(required_attestations - set(attestations)),
                }
            ),
            400,
        )

    in_response_to = body.get("in_response_to")

    with session_scope() as session:
        matter = session.get(Matter, mid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404

        # A0 authz: any authenticated user can submit federal-proxy.
        # Phase B enforces party_id + PartyEntitlement per spec §5.1.

        # Root node of the matter — the commitment attaches at the
        # federal root for A0 since we don't yet resolve the party
        # to a specific tier-node. Phase A migration adds that
        # linkage automatically via the parties FK.
        root = (
            session.query(MatterNode)
            .filter_by(matter_id=matter.id, parent_node_id=None, removed_at=None)
            .first()
        )
        title = (
            f"Commitment · {originating_party_name} · "
            f"{response_shape.get('prompt_type') or 'accept_scope'}"
        )
        signal_summary = (
            f"{originating_party_name} · {response_shape.get('accepted')}"
        )

        decision = create_commitment_decision(
            tenant_id=auth.tenant,
            matter_id=matter.id,
            workflow_id=matter.program_id,
            title=title,
            originating_party_name=originating_party_name,
            response_shape=response_shape,
            in_response_to=in_response_to,
            submitted_by_user_id=uuid.UUID(auth.sub),
            matter_node_id=root.id if root else None,
            agency_id=matter.agency_id,
            signal_summary=signal_summary,
            session=session,
        )
        session.flush()

        # Resolve the matching open RFR — if the caller supplied an
        # in_response_to that maps to a real RFR on this matter, close
        # it out. Silent no-op when no match (A0 supports commitments
        # without an RFR emitted).
        if in_response_to:
            rfr = (
                session.query(RequestForResponse)
                .filter(
                    RequestForResponse.matter_id == matter.id,
                    RequestForResponse.rfr_number == in_response_to,
                    RequestForResponse.status == "open",
                )
                .first()
            )
            if rfr is not None:
                rfr.status = "resolved"
                rfr.resolved_by_decision_id = decision.id
                rfr.resolved_at = datetime.now(UTC)
                session.flush()

        return (
            jsonify(
                {
                    "id": str(decision.id),
                    "decision_number": decision.decision_number,
                    "matter_id": str(matter.id),
                    "is_commitment": True,
                    "originating_party_name": decision.originating_party_name,
                    "in_response_to": decision.in_response_to,
                    "response_shape": decision.response_shape,
                    "decided_at": decision.decided_at.isoformat()
                    if decision.decided_at
                    else None,
                    "title": decision.title,
                    "status": decision.status,
                }
            ),
            201,
        )


@bp.post("/matters/<matter_id>/amendments")
@require_auth
def amend_matter(matter_id: str) -> tuple[Response, int]:
    """Apply a single amendment to ``matter_id``.

    Body shape (type-discriminated):

        { "type": "add_recipient",
          "parent_state_node_id": "...",
          "participant_org_id": "...",
          "active_archetypes": ["payment_authorization", ...],  # optional
          "authority_role": "certifying_officer" }              # optional

        { "type": "remove_recipient",
          "recipient_node_id": "..." }

    Authorization is enforced by the amendment service (TENANCY-MODEL
    §13.2). 403 on policy violation; 409 on attempting to add a
    duplicate active node; 400 on schema problems.
    """
    auth = g.auth
    try:
        bid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "invalid matter_id"}), 400

    body = request.get_json(silent=True) or {}
    amend_type = body.get("type")
    valid_types = (
        "add_recipient",
        "remove_recipient",
        "add_state",
        "remove_state",
        "amend_archetypes",
        "amend_matter_fields",
    )
    if amend_type not in valid_types:
        return (
            jsonify(
                {
                    "error": f"type must be one of: {', '.join(valid_types)}",
                }
            ),
            400,
        )

    with session_scope() as session:
        matter = session.get(Matter, bid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404

        actor = session.get(User, uuid.UUID(auth.sub))
        if actor is None:
            return jsonify({"error": "actor not found"}), 401

        try:
            if amend_type == "add_recipient":
                node = add_recipient_node(
                    matter_id=bid,
                    parent_state_node_id=uuid.UUID(body["parent_state_node_id"]),
                    participant_org_id=uuid.UUID(body["participant_org_id"]),
                    active_archetypes=body.get("active_archetypes"),
                    authority_role=body.get("authority_role"),
                    actor=actor,
                    session=session,
                )
            elif amend_type == "remove_recipient":
                node = remove_recipient_node(
                    recipient_node_id=uuid.UUID(body["recipient_node_id"]),
                    actor=actor,
                    session=session,
                )
            elif amend_type == "add_state":
                node = add_state_node(
                    matter_id=bid,
                    participant_org_id=uuid.UUID(body["participant_org_id"]),
                    active_archetypes=body.get("active_archetypes"),
                    authority_role=body.get("authority_role"),
                    actor=actor,
                    session=session,
                )
            elif amend_type == "remove_state":
                node = remove_state_node(
                    state_node_id=uuid.UUID(body["state_node_id"]),
                    actor=actor,
                    session=session,
                )
            elif amend_type == "amend_archetypes":
                node = amend_node_active_archetypes(
                    node_id=uuid.UUID(body["node_id"]),
                    new_active_archetypes=list(body["active_archetypes"]),
                    actor=actor,
                    session=session,
                )
            else:  # amend_matter_fields
                from decimal import Decimal, InvalidOperation

                amount = body.get("amount_obligated")
                amount_decimal = None
                if amount is not None:
                    try:
                        amount_decimal = Decimal(str(amount))
                    except (InvalidOperation, ValueError):
                        return jsonify({"error": "invalid amount_obligated"}), 400

                changes = amend_matter_fields(
                    matter_id=bid,
                    actor=actor,
                    session=session,
                    amount_obligated=amount_decimal,
                    terms=body.get("terms"),
                    retention_months=body.get("retention_months"),
                )
                return jsonify({"matter_id": str(bid), "changes": changes}), 200
        except AmendmentAuthorityError as exc:
            return jsonify({"error": "forbidden", "detail": str(exc)}), 403
        except AmendmentError as exc:
            return jsonify({"error": "amendment_failed", "detail": str(exc)}), 400
        except IntegrityError as exc:
            # Most commonly: unique-violation on the
            # (matter, participant_org) WHERE removed_at IS NULL index.
            # Rollback so session_scope() doesn't try to commit a
            # poisoned session on the way out.
            session.rollback()
            if isinstance(exc.orig, psycopg.errors.UniqueViolation):
                return (
                    jsonify(
                        {
                            "error": "conflict",
                            "detail": "this participant_org already has an active node in the matter",
                        }
                    ),
                    409,
                )
            raise
        except KeyError as exc:
            return jsonify({"error": "missing_field", "detail": str(exc)}), 400

        session.flush()
        org_lookup: dict[uuid.UUID, ParticipantOrg] = {}
        if node.participant_org_id is not None:
            org = session.get(ParticipantOrg, node.participant_org_id)
            if org is not None:
                org_lookup[node.participant_org_id] = org
        return jsonify(_node_dict(node, org_lookup)), 200


# ─── RFR read endpoints ─────────────────────────────────────────────────
#
# Minimum-slice read surface for the requests_for_response table.
# Emission service (auto-write when a Decision finalize declares a
# prompt) and the federal-PM "issue RFR" affordance are deferred to
# subsequent slices per backlog/awaiting-recipient-stage-band.md.


def _rfr_dict(rfr: RequestForResponse) -> dict[str, Any]:
    return {
        "id": str(rfr.id),
        "rfr_number": rfr.rfr_number,
        "matter_id": str(rfr.matter_id),
        "matter_node_id": str(rfr.matter_node_id) if rfr.matter_node_id else None,
        "originating_decision_id": (
            str(rfr.originating_decision_id) if rfr.originating_decision_id else None
        ),
        "target_party_name": rfr.target_party_name,
        "prompt_type": rfr.prompt_type,
        "prompt_body": rfr.prompt_body,
        "due_at": rfr.due_at.isoformat() if rfr.due_at else None,
        "status": rfr.status,
        "resolved_by_decision_id": (
            str(rfr.resolved_by_decision_id) if rfr.resolved_by_decision_id else None
        ),
        "resolved_at": rfr.resolved_at.isoformat() if rfr.resolved_at else None,
        "issued_by_user_id": (
            str(rfr.issued_by_user_id) if rfr.issued_by_user_id else None
        ),
        "created_at": rfr.created_at.isoformat() if rfr.created_at else None,
    }


@bp.get("/matters/<matter_id>/rfrs")
@require_auth
def list_matter_rfrs(matter_id: str) -> tuple[Response, int]:
    """List RFRs on a matter, optionally filtered by status.

    ``?status=open`` (default), ``?status=all``, or a specific value.
    Powers the case-file "Awaiting response" row and the federal-PM
    matter-detail issue-RFR affordance's existing-list check.
    """
    try:
        mid = uuid.UUID(matter_id)
    except ValueError:
        return jsonify({"error": "invalid matter_id"}), 400

    status_filter = request.args.get("status", "open")
    with session_scope() as session:
        matter = session.get(Matter, mid)
        if matter is None:
            return jsonify({"error": "matter not found"}), 404

        q = session.query(RequestForResponse).filter(
            RequestForResponse.matter_id == mid
        )
        if status_filter != "all":
            q = q.filter(RequestForResponse.status == status_filter)

        rows = q.order_by(RequestForResponse.created_at.desc()).all()
        return jsonify({"items": [_rfr_dict(r) for r in rows]}), 200


@bp.get("/rfrs")
@require_auth
def list_rfrs() -> tuple[Response, int]:
    """Cross-matter RFR list — powers the Recipient Portal watchlist.

    Query params:
      ?status=open|resolved|superseded|all  (default: open)
      ?party=<text>                          filter by target party name
    """
    status_filter = request.args.get("status", "open")
    party_filter = (request.args.get("party") or "").strip() or None

    with session_scope() as session:
        q = session.query(RequestForResponse)
        if status_filter != "all":
            q = q.filter(RequestForResponse.status == status_filter)
        if party_filter:
            q = q.filter(RequestForResponse.target_party_name == party_filter)

        rows = q.order_by(RequestForResponse.due_at.asc()).all()

        # Enrich with matter metadata so the watchlist can render
        # "Central Valley Behavioral Health Network · Medicaid FY26"
        # without a follow-up round-trip per row.
        matter_ids = {r.matter_id for r in rows}
        matter_lookup: dict[uuid.UUID, Matter] = (
            {
                m.id: m
                for m in session.query(Matter)
                .filter(Matter.id.in_(matter_ids))
                .all()
            }
            if matter_ids
            else {}
        )

        items = []
        for r in rows:
            row = _rfr_dict(r)
            m = matter_lookup.get(r.matter_id)
            if m is not None:
                row["matter"] = {
                    "id": str(m.id),
                    "awarding_agency": m.awarding_agency,
                    "program_id": m.program_id,
                    "period_label": m.period_label,
                }
            items.append(row)

        return jsonify({"items": items}), 200
