# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Idempotent loader for fund-flow matters → DP matters.

Reads ``docs/fund-flow/data/matters.json`` (24 curated real federal
awards from the USAspending collector, per ADR-10's decoupled producer
pattern) and writes them into DP's matter aggregate so the Register and
matter detail surfaces show real data instead of synthetic placeholders.

Mapping (matters.json shape → DP schema):

  matter.id           -> matters.federal_application_ref + decision title
  matter.type         -> matters.federal_archetype (mapped via ARCH labels)
  matter.path[0]      -> awarding_agency string (short → real name via AgencyCatalog
                         lookup; falls back to literal string)
  matter.path[1]      -> participant_org (kind='recipient'), recipient matter node
  matter.path[2..]    -> participant_orgs (kind='recipient' per ADR-11 — DP doesn't
                         distinguish subrecipients at the org table), recipient
                         matter nodes under the prime recipient
  matter.x            -> matters.amount_obligated (parsed from "$1.0B" form)
                         + recipient matter_node.amount

Federal-direct (post P29): USAspending prime-award data is overwhelmingly
agency→recipient direct (no state pass-through). The matter service
accepts ``RecipientSpec(parent_state_org_id=None)`` so recipients hang
straight off the federal root with no state node in between — exactly
matching the data's shape.

Usage::

    uv run python -m scripts.import_matters
    uv run python -m scripts.import_matters --source path/to/matters.json
    uv run python -m scripts.import_matters --limit 10

Idempotent — re-runs upsert orgs and matter service handles duplicate
matter ids on its own.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.matters.service import RecipientSpec, create_matter
from reasonbook.models import AgencyCatalog, MatterNode, ParticipantOrg, User
from reasonbook.semantic.engine import get_engine, init_engine

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = ROOT / "docs" / "fund-flow" / "data" / "matters.json"

# Reuse the importer's deterministic UUID namespace so any org slug
# resolved here matches one from the agency / recipient CSV loaders.
from scripts.import_usaspending import NAMESPACE_DP_ENTITY  # noqa: E402

# Most matter rows use `archetype: "Competitive award"` (already human
# label); the matter's federal_archetype is the program-yaml archetype id.
# Map back to the id for create_matter (which looks up the program).
ARCH_TO_PROGRAM_ID: dict[str, str] = {
    # archetype label → program_id that binds that archetype
    # Use "competitive_award" archetype → "nih-r01" program for now;
    # the demo doesn't depend on perfect program-id fidelity (the
    # matter's awarding_agency string carries the visible identity).
    "Competitive award": "nih-r01",
    "competitive_award": "nih-r01",
    "Formula allocation": "cdbg",
    "formula_allocation": "cdbg",
    "Contract": "treasury-disbursement",
    "contract": "treasury-disbursement",
}
DEFAULT_PROGRAM_ID = "nih-r01"


def parse_money(s: str) -> Decimal:
    """Parse '$1.0B', '$46.7M', '$415k', '$2,054,756,020' → Decimal dollars."""
    if not s:
        return Decimal("0")
    cleaned = s.replace("$", "").replace(",", "").strip()
    multiplier = Decimal("1")
    if cleaned.endswith("B"):
        multiplier = Decimal("1000000000")
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = Decimal("1000000")
        cleaned = cleaned[:-1]
    elif cleaned.endswith("k"):
        multiplier = Decimal("1000")
        cleaned = cleaned[:-1]
    try:
        return (Decimal(cleaned) * multiplier).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0")


def slugify(name: str) -> str:
    """Lowercase, alnum-only slug — used as input to uuid5 for org ids."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def org_uuid(slug: str, kind: str) -> uuid.UUID:
    """Deterministic UUID for a participant_org keyed by (kind, slug)."""
    return uuid.uuid5(NAMESPACE_DP_ENTITY, f"{kind}:{slug}")


@dataclass
class LoadReport:
    matters_created: int
    matters_skipped: int
    orgs_inserted: int

    def __str__(self) -> str:
        return (
            f"matters_created={self.matters_created} "
            f"matters_skipped={self.matters_skipped} "
            f"orgs_inserted={self.orgs_inserted}"
        )


def _ensure_recipient(session: Session, *, name: str) -> tuple[ParticipantOrg, bool]:
    slug = slugify(name)
    if not slug:
        raise ValueError(f"cannot slugify recipient name: {name!r}")
    row_id = org_uuid(slug, "recipient")
    existing = session.get(ParticipantOrg, row_id)
    if existing is not None:
        return existing, False
    org = ParticipantOrg(
        id=row_id,
        kind="recipient",
        display_name=name,
        code=slug,
    )
    session.add(org)
    session.flush()
    return org, True


def _resolve_agency_display(session: Session, short: str) -> str:
    """Map a short agency string to the catalog's full display_name.

    matters.json carries short labels ("HHS", "DS"). The agency_catalog
    has full names ("Department of Health and Human Services"). Best-effort
    lookup by trailing initials; falls back to the short string so the
    matter still creates.
    """
    if not short:
        return ""
    # Direct lookups for the most common shorts we see in matters.json.
    known = {
        "HHS": "Department of Health and Human Services",
        "DS": "Department of State",
        "USAID": "Agency for International Development",
        "ED": "Department of Education",
        "DOJ": "Department of Justice",
        "DOD": "Department of Defense",
        # matters.json uses the two-letter USAspending toptier codes,
        # not the conventional DoD/USDA. Map both forms so re-imports
        # from either source land on the canonical agency name.
        "DD": "Department of Defense",
        "DA": "Department of Agriculture",
        "USDA": "Department of Agriculture",
        "DOL": "Department of Labor",
        "HUD": "Department of Housing and Urban Development",
        "DOT": "Department of Transportation",
        "DOE": "Department of Energy",
        "VA": "Department of Veterans Affairs",
        "DHS": "Department of Homeland Security",
        "Treasury": "Department of Treasury",
        "Commerce": "Department of Commerce",
        "Interior": "Department of the Interior",
    }
    if short in known:
        # Verify the row actually exists in our catalog; fall back to
        # the short string if it doesn't.
        from sqlalchemy import select

        row = session.execute(
            select(AgencyCatalog).where(AgencyCatalog.display_name == known[short])
        ).scalar_one_or_none()
        if row is not None:
            return row.display_name
    return short


def _picked_program_id(matter_type: str) -> str:
    return ARCH_TO_PROGRAM_ID.get(matter_type, DEFAULT_PROGRAM_ID)


def _amount_for_matter(matter: dict[str, Any]) -> Decimal:
    return parse_money(matter.get("x", ""))


def _seed_actor(session: Session) -> User:
    """Pick a federal user to attribute the matter to.

    Prefers ``jamie.kim`` (federal demo user); falls back to the first
    federal-tier user in the DB. Raises if none exists — caller should
    ensure the federal seed has run first.
    """
    actor = (
        session.query(User).filter(User.username == "jamie.kim").one_or_none()
    )
    if actor is not None:
        return actor
    actor = (
        session.query(User).filter(User.tier == "federal").first()
    )
    if actor is None:
        raise RuntimeError("no federal user available; run `make seed` first")
    return actor


def load_matters(
    session: Session,
    *,
    source: Path | None = None,
    limit: int | None = None,
    agencies: dict[str, Any] | None = None,
) -> LoadReport:
    source = source or DEFAULT_SOURCE
    if not source.exists():
        # The curated fund-flow matters corpus is an optional demo dataset
        # that is not shipped in the repo. Skip gracefully so seeding still
        # produces the core corpus (agencies, users, alerts, decisions).
        log.warning("matters corpus not found at %s — skipping matter import", source)
        return LoadReport(matters_created=0, matters_skipped=0, orgs_inserted=0)

    payload = json.loads(source.read_text(encoding="utf-8"))
    matters: list[dict[str, Any]] = payload.get("matters", [])
    if limit is not None:
        matters = matters[:limit]

    try:
        get_engine()
    except Exception:  # noqa: BLE001 — first-call init is expected
        init_engine()

    actor = _seed_actor(session)

    matters_created = 0
    matters_skipped = 0
    orgs_inserted = 0

    for source_row in matters:
        match_path: list[Any] = source_row.get("path", [])
        if len(match_path) < 2:
            log.warning("matter %s has malformed path; skipping", source_row.get("id"))
            continue

        agency_short = match_path[0][1] if isinstance(match_path[0], list) else None
        recipient_name = (
            match_path[1][1] if isinstance(match_path[1], list) else None
        )
        if not recipient_name:
            log.warning("matter %s missing recipient; skipping", source_row.get("id"))
            continue

        amount = _amount_for_matter(source_row)
        agency_display = _resolve_agency_display(session, agency_short or "")
        if not agency_display:
            agency_display = "Unknown agency"

        recipient_org, was_new = _ensure_recipient(session, name=recipient_name)
        if was_new:
            orgs_inserted += 1

        # Subrecipient handling: only the 2 matters with path_len=3 carry
        # them, and as a summarized "Name · Name" string. Split by '·',
        # trim, and create one recipient_node per subrecipient with
        # amount=None (sub-edge amounts aren't in matters.json).
        sub_names: list[str] = []
        if len(match_path) >= 3:
            sub_entry = match_path[2]
            if isinstance(sub_entry, list) and len(sub_entry) >= 2:
                raw_subs = str(sub_entry[1])
                # Trailing ellipsis marks "and more"; strip it before split.
                raw_subs = raw_subs.rstrip("…").rstrip(".").strip()
                sub_names = [
                    s.strip() for s in raw_subs.split("·") if s.strip()
                ]

        sub_orgs: list[ParticipantOrg] = []
        for sub_name in sub_names:
            sub_org, sub_was_new = _ensure_recipient(session, name=sub_name)
            if sub_was_new:
                orgs_inserted += 1
            sub_orgs.append(sub_org)

        program_id = _picked_program_id(source_row.get("type", ""))

        # Build the recipient specs — prime + every subrecipient as
        # federal-direct (parent_state_org_id=None) per P29. USAspending
        # prime-award rows don't carry state pass-throughs, so the matter
        # service hangs them directly off the federal root.
        recipient_specs = [
            RecipientSpec(
                parent_state_org_id=None,
                participant_org_id=recipient_org.id,
            )
        ]
        for sub_org in sub_orgs:
            recipient_specs.append(
                RecipientSpec(
                    parent_state_org_id=None,
                    participant_org_id=sub_org.id,
                )
            )

        try:
            # Best-effort agency lookup via the awarding_agency string.
            # Falls through to agency_id=NULL when no match — the scope
            # filter treats null as "visible to everyone" so demo data
            # doesn't get accidentally hidden.
            from scripts.seed_dev import AWARDING_AGENCY_TO_SLUG

            agency_row = None
            if agencies is not None:
                slug = AWARDING_AGENCY_TO_SLUG.get(agency_display)
                if slug is not None:
                    agency_row = agencies.get(slug)

            matter = create_matter(
                program_id=program_id,
                awarding_agency=agency_display,
                amount_obligated=amount,
                period_label="FY26",
                terms="USAspending FY2025 prime-award projection (one-shot import)",
                federal_application_ref=str(source_row.get("id", uuid.uuid4().hex)),
                states=[],
                recipients=recipient_specs,
                actor_user_id=actor.id,
                tenant_id="us-federal",
                agency_id=agency_row.id if agency_row is not None else None,
                session=session,
            )
        except Exception as exc:  # noqa: BLE001 — log + skip on bad row
            log.warning("matter %s: create_matter failed: %s", source_row.get("id"), exc)
            continue

        # Patch the prime recipient node's amount = matter amount.
        # Subs: no amount in matters.json; leave NULL so FundFlowPath
        # renders them without an edge label.
        prime_node = (
            session.query(MatterNode)
            .filter(
                MatterNode.matter_id == matter.id,
                MatterNode.tier == "recipient",
                MatterNode.participant_org_id == recipient_org.id,
                MatterNode.removed_at.is_(None),
            )
            .first()
        )
        if prime_node is not None:
            prime_node.amount = amount

        session.flush()

        if matter.amount_obligated == amount:
            matters_created += 1
        else:
            matters_skipped += 1
        log.info(
            "matter %s · %s · %s · %s",
            source_row.get("id"),
            agency_short or "?",
            recipient_name[:50],
            source_row.get("x"),
        )

    report = LoadReport(
        matters_created=matters_created,
        matters_skipped=matters_skipped,
        orgs_inserted=orgs_inserted,
    )
    log.info("import_matters: %s", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        with session_scope() as s:
            load_matters(s, source=Path(args.source), limit=args.limit)
    except FileNotFoundError as exc:
        print(f"missing: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
