# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Executive dashboard API.

GET /api/dashboard returns a compact, cross-workflow institutional summary
that powers the /dashboard page. Composed of three blocks:

  1. operational — per-workflow open / decided / at-risk decision counts,
     plus a 4-week opened-decision trend sparkline per workflow.
  2. apex — open apex decisions, per-domain breakdown, and current board
     cycle.
  3. recent_outcomes — top 10 decisions whose outcome was recorded in
     the trailing 30 days, cross-workflow. Surfaces institutional
     throughput on the same surface that surfaces what's still open.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from flask import Blueprint, Response, g, jsonify
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.decisions.scope import (
    AT_RISK_CATEGORY_BY_WORKFLOW as _AT_RISK_CATEGORY_BY_WORKFLOW,
)
from reasonbook.decisions.scope import OPEN_STATUSES as _OPEN_STATUSES
from reasonbook.decisions.scope import at_risk_filter as _at_risk_filter
from reasonbook.decisions.scope import oversight_awaiting_committee_filter, tier_scope_where
from reasonbook.models import Decision, Tenant
from reasonbook.semantic.engine import get_engine

bp = Blueprint("dashboard", __name__)
log = logging.getLogger(__name__)

OVERSIGHT_WORKFLOW_ID = "10-oversight"


def _tier_where() -> Any:
    """Row-level tier-scope where-clause from current ``g.auth``.

    Returns SQL TRUE for federal (no restriction); a fund_flow_path
    predicate for state/recipient. Always safe to pass to ``.where()``.
    Per TENANCY-MODEL.md §3 — single source for the scope filter so
    every Decision aggregate in this module routes the same policy.
    """
    auth = g.auth
    return tier_scope_where(
        tier=auth.tier,
        participant_org_id=(
            uuid.UUID(auth.participant_org_id) if auth.participant_org_id else None
        ),
    )

# ``_OPEN_STATUSES``, ``_AT_RISK_CATEGORY_BY_WORKFLOW``, and
# ``_at_risk_filter`` are imported from ``reasonbook.decisions.scope`` (above)
# so the dashboard and the P17 decision-queue endpoint share one
# definition. They keep their underscore-prefixed alias here for the
# same reason the helpers in this file do — they're treated as module
# locals by every existing reference downstream.

# Sparkline window: 4 weeks of opened-decision counts, ending today.
_TREND_WEEKS = 4

# Top-rail sparkline: 7 daily snapshots of the institution's total open
# decision count, oldest→newest. Backs the small line under the OPEN tile
# and reads as "is the open-decision backlog growing or steady" at a glance.
_OPEN_TREND_DAYS = 7

# Window for the "avg cycle" footnote on the DECIDED tile. 30 days
# smooths daily volatility while staying recent enough to reflect
# current operational tempo.
_DECIDED_AVG_CYCLE_WINDOW_DAYS = 30

# Recent-outcomes window: trailing 30 days, capped at top N for the panel.
_OUTCOMES_WINDOW_DAYS = 30
_OUTCOMES_LIMIT = 10

# Cap on in-flight apex decisions inlined under the cycle card. Most
# active cycles carry 1–5 in-flight decisions; the cap defends against
# a pathological seed or future high-volume cycle blowing up the
# dashboard's vertical real estate. Anything past the cap surfaces as
# a "+N more" link that routes to the apex view.
_CYCLE_OPEN_DECISIONS_LIMIT = 5


def _operational_counts(session: Session, tenant_id: str) -> dict[str, Any]:
    """Per-workflow counts + a 4-week opened-decision trend, in two queries.

    Returns ``{by_workflow: [...], totals: {...}}``. Each by_workflow entry
    has open / decided / at-risk counts plus ``trend: [{week_starting,
    opened_count}, ...]`` — 4 entries oldest→newest, intended to power
    inline SVG sparklines on the dashboard tiles. Workflows with zero
    decisions still appear (we union with the engine's entitled list so
    the dashboard renders empty cards rather than hiding workflows that
    haven't surfaced anything yet).
    """
    # Aggregate per-workflow open + decided counts.
    rows = session.execute(
        select(
            Decision.workflow_id,
            func.count(Decision.id).filter(Decision.status.in_(_OPEN_STATUSES)).label("open_count"),
            func.count(Decision.id).filter(Decision.status == "decided").label("decided_count"),
            func.count(Decision.id).filter(_at_risk_filter()).label("at_risk_count"),
        )
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id != OVERSIGHT_WORKFLOW_ID)
        .group_by(Decision.workflow_id)
    ).all()

    by_id = {
        row.workflow_id: {
            "open_count": int(row.open_count),
            "decided_count": int(row.decided_count),
            "at_risk_count": int(row.at_risk_count),
        }
        for row in rows
    }

    trends_by_workflow = _opened_trend_by_workflow(session, tenant_id)

    # Card per registered workflow so agencies see a card for every
    # workflow that could receive decisions, even when zero have
    # surfaced yet. Oversight excluded — has its own dashboard surface.
    engine = get_engine()
    workflow_ids = [s["id"] for s in engine.list_summaries() if s["id"] != OVERSIGHT_WORKFLOW_ID]
    by_workflow: list[dict[str, Any]] = []
    for wid in workflow_ids:
        if not engine.has(wid):
            continue
        cfg = engine.get_config(wid)
        counts = by_id.get(wid, {"open_count": 0, "decided_count": 0, "at_risk_count": 0})
        by_workflow.append(
            {
                "workflow_id": wid,
                "workflow_name": cfg.workflow.name,
                "color": cfg.workflow.color,
                **counts,
                "trend": trends_by_workflow.get(wid, _empty_trend()),
            }
        )

    totals = {
        "open": sum(w["open_count"] for w in by_workflow),
        "decided": sum(w["decided_count"] for w in by_workflow),
        "at_risk": sum(w["at_risk_count"] for w in by_workflow),
    }

    # Top-rail enrichments: deltas, breakdown, avg cycle, daily sparkline.
    # Computed against the same entitled-workflows scope (non-apex) so
    # the totals row reads coherently with the workflow grid below.
    entitled_non_apex = [w["workflow_id"] for w in by_workflow]
    totals.update(_totals_enrichments(session, tenant_id, entitled_non_apex))

    return {
        "by_workflow": by_workflow,
        "totals": totals,
        "open_trend": _open_trend_daily(session, tenant_id, entitled_non_apex),
    }


def _totals_enrichments(
    session: Session, tenant_id: str, entitled_workflows: list[str]
) -> dict[str, Any]:
    """Top-rail-specific top-of-payload enrichments.

    Returns the four extra fields the dashboard's top three tiles need
    beyond raw counts:

    - ``open_delta_24h`` — new decisions created in the trailing 24h
      (positive integer; arrivals only, not a signed change)
    - ``decided_delta_24h`` — signed change in decided-today count vs.
      the prior 24h window (today's decided minus yesterday's decided)
    - ``at_risk_delta_24h`` — count of decisions whose SLA deadline
      crossed into the ``≤24h`` window during the trailing 24h
      (positive integer; "newly at-risk" arrivals)
    - ``decided_avg_cycle_days`` — average days from ``created_at`` to
      ``decided_at`` over the trailing 30-day decided population, or
      ``None`` when no decided rows exist in the window
    - ``at_risk_breakdown`` — list of ``{label, count}`` aggregated by
      strategic-domain category (credit / compliance / ops), sorted
      desc by count, empty buckets dropped
    """
    if not entitled_workflows:
        return {
            "open_delta_24h": 0,
            "decided_delta_24h": 0,
            "at_risk_delta_24h": 0,
            "decided_avg_cycle_days": None,
            "at_risk_breakdown": [],
        }

    now = datetime.now(UTC)
    window_24h = now - timedelta(hours=24)
    window_48h = now - timedelta(hours=48)
    window_30d = now - timedelta(days=_DECIDED_AVG_CYCLE_WINDOW_DAYS)

    # open_delta_24h — decisions created in last 24h that landed in an
    # open status (anything not closed/deferred). Reads as "new opens
    # since yesterday."
    open_delta = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(Decision.created_at >= window_24h)
        .where(Decision.status.in_(_OPEN_STATUSES))
    ).scalar_one()

    # decided_delta_24h — signed: today's decided count minus
    # yesterday's. Negative means fewer decided today than yesterday;
    # the mockup's ``▼ 1`` shape.
    decided_today = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(Decision.decided_at.isnot(None))
        .where(Decision.decided_at >= window_24h)
    ).scalar_one()
    decided_yesterday = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(Decision.decided_at.isnot(None))
        .where(Decision.decided_at >= window_48h)
        .where(Decision.decided_at < window_24h)
    ).scalar_one()
    decided_delta = int(decided_today) - int(decided_yesterday)

    # at_risk_delta_24h — current at-risk count (same predicate as
    # ``_at_risk_filter``). The "delta" framing in the property name is
    # historical (the field originally tried to compute "newly entered
    # at-risk in last 24h"). Today it just mirrors the at-risk total
    # under the same filter so the UI can render a count next to the
    # arrow; semantic alignment with a true day-over-day delta is a
    # follow-up. Same status filter (intersect with _OPEN_STATUSES) as
    # ``_at_risk_filter`` so the invariant at_risk_delta ≤ at_risk
    # holds.
    at_risk_delta = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(Decision.sla_deadline.isnot(None))
        .where(Decision.sla_deadline <= now + timedelta(hours=24))
        .where(Decision.status.in_(_OPEN_STATUSES))
    ).scalar_one()

    # decided_avg_cycle_days — mean (decided_at - created_at) in days
    # for decisions decided in the trailing 30 days. Returns None when
    # there's no decided population in the window.
    cycle_seconds = session.execute(
        select(
            func.avg(
                func.extract("epoch", Decision.decided_at)
                - func.extract("epoch", Decision.created_at)
            )
        )
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(Decision.decided_at.isnot(None))
        .where(Decision.decided_at >= window_30d)
    ).scalar_one()
    decided_avg_cycle_days = (
        round(float(cycle_seconds) / 86400.0, 1) if cycle_seconds is not None else None
    )

    # at_risk_breakdown — group currently-at-risk decisions by
    # category. Per-workflow counts via the same predicate as
    # _at_risk_filter, then folded into the category map.
    breakdown_rows = session.execute(
        select(Decision.workflow_id, func.count(Decision.id).label("n"))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id.in_(entitled_workflows))
        .where(_at_risk_filter())
        .group_by(Decision.workflow_id)
    ).all()
    by_category: dict[str, int] = {}
    for r in breakdown_rows:
        label = _AT_RISK_CATEGORY_BY_WORKFLOW.get(r.workflow_id)
        if label is None:
            continue
        by_category[label] = by_category.get(label, 0) + int(r.n)
    breakdown_entries: list[tuple[str, int]] = [(k, v) for k, v in by_category.items() if v > 0]
    breakdown_entries.sort(key=lambda e: e[1], reverse=True)
    at_risk_breakdown: list[dict[str, Any]] = [
        {"label": label, "count": count} for label, count in breakdown_entries
    ]

    return {
        "open_delta_24h": int(open_delta),
        "decided_delta_24h": decided_delta,
        "at_risk_delta_24h": int(at_risk_delta),
        "decided_avg_cycle_days": decided_avg_cycle_days,
        "at_risk_breakdown": at_risk_breakdown,
    }


def _open_trend_daily(
    session: Session, tenant_id: str, entitled_workflows: list[str]
) -> list[dict[str, Any]]:
    """7-day daily open-count sparkline.

    Each entry is the count of decisions that were in an open status
    at end-of-day. Approximation: ``created_at <= day_end`` AND
    (``decided_at IS NULL`` OR ``decided_at > day_end``). Surfaces the
    institution's open-decision backlog trend under the OPEN tile.
    """
    if not entitled_workflows:
        return []
    now = datetime.now(UTC)
    today = now.date()
    days = [today - timedelta(days=_OPEN_TREND_DAYS - 1 - i) for i in range(_OPEN_TREND_DAYS)]

    out: list[dict[str, Any]] = []
    for d in days:
        day_end = datetime.combine(d, datetime.max.time(), tzinfo=UTC)
        cnt = session.execute(
            select(func.count(Decision.id))
            .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
            .where(Decision.workflow_id.in_(entitled_workflows))
            .where(Decision.created_at <= day_end)
            .where((Decision.decided_at.is_(None)) | (Decision.decided_at > day_end))
        ).scalar_one()
        out.append({"day": d.isoformat(), "open_count": int(cnt)})
    return out


def _week_buckets(weeks: int = _TREND_WEEKS) -> list[date]:
    """Return ``weeks`` Monday-anchored week-start dates, oldest first.

    Weeks are anchored on Monday so a customer's "this week" reading
    matches the conventional business-week mental model regardless of
    the server's locale settings.
    """
    today = datetime.now(UTC).date()
    monday_this_week = today - timedelta(days=today.weekday())
    return [monday_this_week - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]


def _empty_trend() -> list[dict[str, Any]]:
    return [{"week_starting": w.isoformat(), "opened_count": 0} for w in _week_buckets()]


def _opened_trend_by_workflow(session: Session, tenant_id: str) -> dict[str, list[dict[str, Any]]]:
    """Per-workflow weekly count of decisions whose ``created_at`` falls
    in each of the trailing 4 ISO weeks. One round-trip; client zips."""
    buckets = _week_buckets()
    earliest = datetime.combine(buckets[0], datetime.min.time(), tzinfo=UTC)
    rows = session.execute(
        select(
            Decision.workflow_id,
            func.date_trunc("week", Decision.created_at).label("week"),
            func.count(Decision.id).label("n"),
        )
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id != OVERSIGHT_WORKFLOW_ID)
        .where(Decision.created_at >= earliest)
        .group_by(Decision.workflow_id, "week")
    ).all()

    # Map each (workflow_id, week_start_date) → count
    by_key: dict[tuple[str, date], int] = {}
    for r in rows:
        # `week` is a tz-aware datetime at the Monday boundary
        week_d: date = r.week.date() if hasattr(r.week, "date") else r.week
        by_key[(r.workflow_id, week_d)] = int(r.n)

    out: dict[str, list[dict[str, Any]]] = {}
    workflow_ids = {r.workflow_id for r in rows}
    for wid in workflow_ids:
        out[wid] = [
            {
                "week_starting": w.isoformat(),
                "opened_count": by_key.get((wid, w), 0),
            }
            for w in buckets
        ]
    return out


def _oversight_summary(session: Session, tenant_id: str) -> dict[str, Any]:
    """Open apex decisions, per-domain breakdown, and current board cycle."""
    open_count = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id == OVERSIGHT_WORKFLOW_ID)
        .where(Decision.status.in_(_OPEN_STATUSES))
    ).scalar_one()

    # Per-domain breakdown: GROUP BY decision_type_id, then map each
    # decision type to its domain via the apex YAML config. The mapping
    # lives in YAML (extra fields on `decision_types` permit `domain`),
    # not the database — that's deliberate per apex spec §3.6.
    by_domain = _apex_open_by_domain(session, tenant_id)

    # Board cycle is its own table; query the active cycle for this tenant
    # if one exists. Defer rich cycle metrics (decisions-at-risk, dossier
    # link) to v2 — for the dashboard summary we just need name + close
    # date so the executive knows the deadline.
    cycle_payload = _current_cycle(session, tenant_id)

    return {
        "open_decisions_count": int(open_count),
        "open_by_domain": by_domain,
        "current_cycle": cycle_payload,
    }


def _apex_open_by_domain(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Open apex decisions grouped by strategic domain.

    Returns one entry per domain declared on the apex workflow YAML, in
    the YAML's declared order. Domains with zero open decisions are
    included with ``open_count: 0`` so the dashboard renders the full
    eight-domain picture rather than hiding empty domains — a CEO scan
    benefits from "Capital: 0" being explicit, not absent.
    """
    engine = get_engine()
    if not engine.has(OVERSIGHT_WORKFLOW_ID):
        return []
    oversight_cfg = engine.get_config(OVERSIGHT_WORKFLOW_ID)

    # Each apex decision_type carries a `domain` field via _Permissive
    # extra. Build the type→domain map.
    type_to_domain: dict[str, str] = {}
    for dt in oversight_cfg.decision_types:
        domain_id = getattr(dt, "domain", None) or (dt.model_extra or {}).get("domain")
        if domain_id:
            type_to_domain[dt.id] = domain_id

    rows = session.execute(
        select(Decision.decision_type, func.count(Decision.id).label("n"))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id == OVERSIGHT_WORKFLOW_ID)
        .where(Decision.status.in_(_OPEN_STATUSES))
        .group_by(Decision.decision_type)
    ).all()

    counts_by_domain: dict[str, int] = {}
    for r in rows:
        domain_id = type_to_domain.get(r.decision_type)
        if domain_id is None:
            # Decision type not mapped to any domain — skip rather than
            # invent a bucket; surfaces only if YAML and database disagree.
            continue
        counts_by_domain[domain_id] = counts_by_domain.get(domain_id, 0) + int(r.n)

    return [
        {
            "domain_id": d.id,
            "name": d.name,
            "primary_owner_role": d.primary_owner_role,
            "open_count": counts_by_domain.get(d.id, 0),
        }
        for d in oversight_cfg.decision_domains
    ]


def _current_cycle(session: Session, tenant_id: str) -> dict[str, Any] | None:
    """Most recent active board cycle for this tenant, or None.

    Includes the first N in-flight decisions inlined as ``open_decisions``
    so the dashboard can render their titles directly under the cycle
    card rather than just a count. Surfaced 2026-05-12: the count-only
    layout left execs asking "okay, *which two*?" with no answer on
    the dashboard surface.
    """
    from reasonbook.models import OversightCycle

    cycle = (
        session.query(OversightCycle)
        .filter(OversightCycle.tenant_id == tenant_id)
        .filter(OversightCycle.status == "active")
        .order_by(OversightCycle.cycle_end.asc())
        .first()
    )
    if cycle is None:
        return None

    # Cycle "in flight" for apex extends through `decided` until a
    # ratified_by_board event fires — operational `decided` semantics
    # don't apply, the board is the next gate. Per apex spec §6.3 + P51.
    open_in_cycle = session.execute(
        select(func.count(Decision.id))
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id == OVERSIGHT_WORKFLOW_ID)
        .where(Decision.oversight_cycle_id == cycle.id)
        .where((Decision.status.in_(_OPEN_STATUSES)) | oversight_awaiting_committee_filter())
    ).scalar_one()

    open_decisions = _cycle_open_decisions(session, tenant_id, cycle.id)
    more_count = max(0, int(open_in_cycle) - len(open_decisions))

    return {
        "id": str(cycle.id),
        "name": cycle.name,
        "cycle_end": cycle.cycle_end.isoformat() if cycle.cycle_end else None,
        "open_count": int(open_in_cycle),
        "open_decisions": open_decisions,
        "open_decisions_more": more_count,
    }


def _cycle_open_decisions(session: Session, tenant_id: str, cycle_id: Any) -> list[dict[str, Any]]:
    """In-flight apex decisions in a board cycle with owner names.

    Ordered SLA-deadline ascending (most urgent first) then decision_number
    so the dashboard inline list reads as a triage queue. Capped at
    ``_CYCLE_OPEN_DECISIONS_LIMIT``; the caller computes a "+N more"
    count from the cycle total.
    """
    from reasonbook.models import User

    rows = session.execute(
        select(
            Decision.id,
            Decision.decision_number,
            Decision.title,
            Decision.decision_type,
            User.name.label("owner_name"),
        )
        .outerjoin(User, Decision.owner_id == User.id)
        .where(_tier_where())
        .where(Decision.tenant_id == tenant_id)
        .where(Decision.workflow_id == OVERSIGHT_WORKFLOW_ID)
        .where(Decision.oversight_cycle_id == cycle_id)
        .where((Decision.status.in_(_OPEN_STATUSES)) | oversight_awaiting_committee_filter())
        .order_by(
            Decision.sla_deadline.asc().nulls_last(),
            Decision.decision_number.asc(),
        )
        .limit(_CYCLE_OPEN_DECISIONS_LIMIT)
    ).all()

    return [
        {
            "decision_id": str(r.id),
            "decision_number": r.decision_number,
            "title": r.title,
            "decision_type": r.decision_type,
            "owner_name": r.owner_name,
        }
        for r in rows
    ]


def _recent_outcomes(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    """Top N decisions whose outcome was recorded in the trailing 30 days.

    Cross-workflow. Surfaces institutional throughput on the same surface
    that surfaces what's still open — "what closed" complements "what's
    in flight" without requiring a separate page.
    """
    cutoff = datetime.now(UTC) - timedelta(days=_OUTCOMES_WINDOW_DAYS)
    rows = (
        session.query(Decision)
        .filter(
            and_(
                _tier_where(),
                Decision.tenant_id == tenant_id,
                Decision.outcome_recorded_at.isnot(None),
                Decision.outcome_recorded_at >= cutoff,
            )
        )
        .order_by(Decision.outcome_recorded_at.desc())
        .limit(_OUTCOMES_LIMIT)
        .all()
    )

    engine = get_engine()
    out: list[dict[str, Any]] = []
    for d in rows:
        wf_name = (
            engine.get_config(d.workflow_id).workflow.name
            if engine.has(d.workflow_id)
            else d.workflow_id
        )
        wf_color = (
            engine.get_config(d.workflow_id).workflow.color if engine.has(d.workflow_id) else None
        )
        out.append(
            {
                "decision_id": str(d.id),
                "decision_number": d.decision_number,
                "title": d.title,
                "workflow_id": d.workflow_id,
                "workflow_name": wf_name,
                "workflow_color": wf_color,
                "outcome_recorded_at": d.outcome_recorded_at.isoformat()
                if d.outcome_recorded_at
                else None,
            }
        )
    return out


@bp.get("/dashboard")
@require_auth
def dashboard() -> tuple[Response, int]:
    """Cross-workflow executive summary for /dashboard."""
    auth = g.auth
    with session_scope() as session:
        tenant = session.get(Tenant, auth.tenant)
        if tenant is None:
            return jsonify({"error": "tenant not found"}), 404

        operational = _operational_counts(session, auth.tenant)
        apex = _oversight_summary(session, auth.tenant)
        recent_outcomes = _recent_outcomes(session, auth.tenant)

        # Invariant: at_risk decisions are by definition still in the
        # open population. If this fails for any tenant, the at-risk
        # filter has regressed (e.g. someone widened the status check
        # to include 'decided' again). Log loudly so the regression
        # surfaces in DO logs without breaking the response.
        totals = operational["totals"]
        if totals["at_risk"] > totals["open"]:
            log.warning(
                "dashboard.at_risk_exceeds_open tenant=%s at_risk=%d open=%d "
                "— at-risk filter likely permits non-open statuses",
                auth.tenant,
                totals["at_risk"],
                totals["open"],
            )

        # Belt-and-suspenders: when a delta value equals the metric
        # value itself, the delta is almost certainly broken (fresh
        # seed with all rows ≤24h old, or a regression in delta
        # semantics). The frontend has a UI guard that suppresses
        # rendering in that case; these warnings give ops visibility
        # if the data class returns through another angle.
        if totals["open_delta_24h"] == totals["open"] and totals["open"] > 0:
            log.warning(
                "dashboard.open_delta_equals_current tenant=%s open=%d "
                "— delta calc lacks day-over-day subtraction OR seed "
                "concentrates created_at in last 24h",
                auth.tenant,
                totals["open"],
            )
        if totals["decided_delta_24h"] == totals["decided"] and totals["decided"] > 0:
            log.warning(
                "dashboard.decided_delta_equals_current tenant=%s "
                "decided=%d — same delta-equals-current bug class as "
                "open_delta_24h; check decided_yesterday baseline",
                auth.tenant,
                totals["decided"],
            )

        body = {
            "tenant": {
                "id": tenant.tenant_id,
                "name": tenant.name,
            },
            "operational": operational,
            "apex": apex,
            "recent_outcomes": recent_outcomes,
        }
    return jsonify(body), 200
