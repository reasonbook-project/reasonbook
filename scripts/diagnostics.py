# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Ad-hoc DB diagnostic queries for DO Console.

Use from DO Console (`reasonbook` service):

    python -m scripts.diagnostics dashboard_totals
    python -m scripts.diagnostics decision_numbers_by_prefix DEC-
    python -m scripts.diagnostics apex_evidence_links

These are read-only by design. Cleanup goes through ``scripts.seed_demo``
which handles foreign-key constraints (apex_evidence_links references
operational decisions with ON DELETE RESTRICT — a wholesale wipe will
trip the constraint).

Added 2026-05-12 during narrative-2 demo prep when stale ``DEC-*``
auto-numbered decisions from UI testing of the create-decision drawer
were inflating Sarah's dashboard.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Callable

from sqlalchemy import select

from reasonbook.db import session_scope
from reasonbook.models import Decision

TENANT_ID = "us-federal"
OPEN_STATUSES = ("open", "assigned", "in_progress")


def dashboard_totals() -> None:
    """Per-workflow open / decided / at-risk counts for Riverdale.

    Mirrors the executive dashboard's tile math. ``at_risk`` is
    decisions whose SLA deadline is within 24h or already past, per
    ``reasonbook.api.dashboard._at_risk_filter``.
    """
    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) + timedelta(hours=24)
    with session_scope() as s:
        rows = s.scalars(select(Decision).where(Decision.tenant_id == TENANT_ID)).all()
        by_wf: dict[str, dict[str, int]] = {}
        for d in rows:
            counts = by_wf.setdefault(d.workflow_id, {"open": 0, "decided": 0, "at_risk": 0})
            if d.status in OPEN_STATUSES:
                counts["open"] += 1
            if d.status == "decided":
                counts["decided"] += 1
            if (
                d.sla_deadline is not None
                and d.sla_deadline <= cutoff
                and d.status not in ("closed", "deferred")
            ):
                counts["at_risk"] += 1

        totals = {"open": 0, "decided": 0, "at_risk": 0}
        print(f"{'workflow':<32} {'OPEN':>6} {'DECIDED':>8} {'AT RISK':>8}")
        for wf_id in sorted(by_wf):
            c = by_wf[wf_id]
            print(f"  {wf_id:<30} {c['open']:>6} {c['decided']:>8} {c['at_risk']:>8}")
            for k in totals:
                totals[k] += c[k]
        print(f"  {'TOTAL':<30} {totals['open']:>6} {totals['decided']:>8} {totals['at_risk']:>8}")


def decision_numbers_by_prefix(prefix: str) -> None:
    """Show every decision_number matching prefix, grouped by workflow."""
    with session_scope() as s:
        rows = s.scalars(
            select(Decision)
            .where(
                Decision.tenant_id == TENANT_ID,
                Decision.decision_number.like(f"{prefix}%"),
            )
            .order_by(Decision.workflow_id, Decision.decision_number)
        ).all()
        if not rows:
            print(f"No decisions matching {prefix}*")
            return
        print(f"Found {len(rows)} decisions matching {prefix}*:")
        for d in rows:
            print(
                f"  {d.decision_number:<24} {d.workflow_id:<32} "
                f"status={d.status:<12} authority={d.owner_authority_level}"
            )
        by_wf = Counter(d.workflow_id for d in rows)
        print()
        print("By workflow:")
        for wf, n in sorted(by_wf.items()):
            print(f"  {wf:<32} {n}")


def apex_evidence_links() -> None:
    """List every apex_evidence_links row with the linked operational decision.

    Useful when a wholesale delete trips the
    ``apex_evidence_links_operational_decision_id_fkey`` RESTRICT
    constraint — this tells you which decisions are FK-protected.
    """
    from reasonbook.models import OversightEvidenceLink

    with session_scope() as s:
        rows = s.scalars(
            select(OversightEvidenceLink).where(OversightEvidenceLink.tenant_id == TENANT_ID)
        ).all()
        print(f"Total apex_evidence_links: {len(rows)}")
        for link in rows:
            op = s.get(Decision, link.operational_decision_id)
            apex = s.get(Decision, link.oversight_decision_id)
            print(
                f"  {apex.decision_number if apex else '?':<24} ← "
                f"{op.decision_number if op else '?':<24} "
                f"({link.evidence_role})"
            )


_REGISTRY: dict[str, Callable[..., None]] = {
    "dashboard_totals": dashboard_totals,
    "decision_numbers_by_prefix": decision_numbers_by_prefix,
    "apex_evidence_links": apex_evidence_links,
}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _REGISTRY:
        print("Usage: python -m scripts.diagnostics <query> [args]")
        print()
        print("Available queries:")
        for name, fn in _REGISTRY.items():
            doc = (fn.__doc__ or "").strip().split("\n")[0]
            print(f"  {name:<32} {doc}")
        sys.exit(0 if len(sys.argv) < 2 else 2)

    fn = _REGISTRY[sys.argv[1]]
    fn(*sys.argv[2:])


if __name__ == "__main__":
    main()
