# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Seed the development database.

Idempotent — safe to re-run. Inserts:

- One agency (legacy `Tenant` table until the rename lands): NIH Office
  of Extramural Research.
- Four users: Sarah Mitchell (agency head), Jamie Kim (Program Officer
  (Extramural)), Marcus Webb (CPIO), David Park (data steward).
- Entitlements for the federal program IDs the seed writes Decisions
  against (nih-r01, nih-no-cost-extension, treasury-disbursement,
  grant-debarment, cdbg) plus the oversight (apex) workflow.
- Oversight: Sarah carries agency_head oversight authority across all
  9 federal domains; Marcus carries CPIO authority for program-
  integrity domains; Priya carries CCO authority for
  congressional_and_regulatory_posture; Daniel carries CFO authority
  for appropriations_and_obligations. One concluded oversight cycle
  and one active oversight cycle, each with seeded oversight
  decisions.
- Connector registry: USASpending.gov collector (the first
  federal-system data source wired into DP).

NOTE: this file's inserts against Tenant / tenant_id are the last
surface still using the DG-era vocabulary. The tenant→agency rename
is tracked in docs/architecture/backlog/ and will land as a follow-up
sweep.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import bcrypt
from sqlalchemy import select, text

from reasonbook.db import schema_prefix, session_scope
from reasonbook.models import (
    Agency,
    AgencySemanticOverride,
    Connector,
    Decision,
    OversightCycle,
    OversightFinding,
    RequestForResponse,
    Tenant,
    User,
    UserAgencyScope,
    UserSupervisor,
    UserWorkflowAuthority,
)
from reasonbook.oversight import DECISION_DOMAINS, OVERSIGHT_WORKFLOW_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

TENANT_ID = "us-federal"
# No shipped default. Set REASONBOOK_SEED_PASSWORD to seed demo accounts;
# seed() fails loudly when it is unset. These accounts are NON-PRODUCTION
# demo identities on example.org addresses.
DEMO_PASSWORD = os.environ.get("REASONBOOK_SEED_PASSWORD", "")


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _upsert_agency(
    session: Session,
    *,
    slug: str,
    name: str,
    short_name: str,
    parent_slug: str | None = None,
) -> Agency:
    """Idempotent agency insert. Resolves parent by slug so callers can
    write the tree top-down without holding UUIDs."""
    existing = session.query(Agency).filter_by(agency_slug=slug).one_or_none()
    if existing is not None:
        return existing

    parent = (
        session.query(Agency).filter_by(agency_slug=parent_slug).one()
        if parent_slug
        else None
    )
    depth = (parent.depth + 1) if parent is not None else 0
    row = Agency(
        id=uuid.uuid4(),
        agency_slug=slug,
        name=name,
        short_name=short_name,
        parent_agency_id=parent.id if parent else None,
        depth=depth,
    )
    session.add(row)
    session.flush()
    log.info("inserted agency %s (depth %d)", slug, depth)
    return row


def _seed_agencies(session: Session) -> dict[str, Agency]:
    """Seed the federal-agency hierarchy the demo pilots against.

    Two top-level departments (HHS, HUD) plus a flat DoD. HHS grows a
    NIH bureau which grows a NIH-OER program office — three levels
    deep, matches the natural hierarchy of the current corpus (NIH-OER
    is where Sarah owns her decisions).
    """
    hhs = _upsert_agency(
        session,
        slug="hhs",
        name="Department of Health and Human Services",
        short_name="HHS",
    )
    nih = _upsert_agency(
        session,
        slug="nih",
        name="National Institutes of Health",
        short_name="NIH",
        parent_slug="hhs",
    )
    nih_oer = _upsert_agency(
        session,
        slug="nih-oer",
        name="NIH Office of Extramural Research",
        short_name="NIH-OER",
        parent_slug="nih",
    )
    hud = _upsert_agency(
        session,
        slug="hud",
        name="Department of Housing and Urban Development",
        short_name="HUD",
    )
    dod = _upsert_agency(
        session,
        slug="dod",
        name="Department of Defense",
        short_name="DoD",
    )
    # The current demo corpus (USASpending imports + tenancy-matter
    # seed) touches State + Agriculture too; seeded flat so every
    # matter in the tree can be stamped with an agency_id.
    state = _upsert_agency(
        session,
        slug="state",
        name="Department of State",
        short_name="State",
    )
    usda = _upsert_agency(
        session,
        slug="usda",
        name="Department of Agriculture",
        short_name="USDA",
    )
    return {
        "hhs": hhs,
        "nih": nih,
        "nih-oer": nih_oer,
        "hud": hud,
        "dod": dod,
        "state": state,
        "usda": usda,
    }


# awarding_agency → agency slug. Used by the matter backfill to map
# USASpending / import_matters matter strings to a scope-carrier
# Agency. Missing strings fall through to agency_id=NULL, which the
# scope filter treats as "everyone sees it" so demo data isn't
# accidentally hidden.
AWARDING_AGENCY_TO_SLUG: dict[str, str] = {
    "Department of Health and Human Services": "hhs",
    "Department of Housing and Urban Development": "hud",
    "Department of Defense": "dod",
    "Department of State": "state",
    "Department of Agriculture": "usda",
}


def _agency_for_awarding_agency(
    agencies: dict[str, Agency], awarding_agency: str
) -> Agency | None:
    """Best-effort map from a USASpending awarding-agency label to an
    Agency in our scope hierarchy. Returns None when no match — the
    caller writes agency_id=NULL and the scope filter falls through."""
    slug = AWARDING_AGENCY_TO_SLUG.get(awarding_agency)
    if slug is None:
        return None
    return agencies.get(slug)


# Program-id → agency slug map. Used by the final backfill pass to
# stamp agency_id on decisions/matters whose scope carrier isn't set
# via the awarding_agency string (e.g., NIH-R01 workflows always
# belong to NIH-OER even if the matter's awarding_agency is a
# generic "HHS").
_PROGRAM_ID_TO_AGENCY_SLUG: dict[str, str] = {
    "nih-r01": "nih-oer",
    "nih-no-cost-extension": "nih-oer",
    "treasury-disbursement": "dod",
    "cdbg": "hud",
    "grant-debarment": "hhs",
    "10-oversight": "hhs",  # oversight decisions live at the HHS layer
    "01-regulatory-compliance": "hhs",
}


def _seed_disputes(
    session: Session,
    *,
    tenant_id: str,
    agencies: dict[str, Agency],
    opened_by: User,
) -> None:
    """Seed a handful of identity-resolution disputes for the demo.

    Each dispute pairs two candidate identities that look similar
    enough to warrant analyst review — SAM.gov name collisions,
    DUNS-vs-UEI transitions, and one already-resolved case so the
    tab shows both open and closed rows.

    Idempotent — skips insertion if any dispute already exists for
    the tenant.
    """
    # Look up matter matters the disputes attach to. Linkage lets the
    # resolve endpoint copy matter_id onto the created Decision
    # so the resulting record surfaces on the matter's case-file
    # instead of floating as a matter-less orphan. Matters don't store
    # federal_application_ref on the row; the deterministic UUID is
    # derived from (program_id, awarding_agency, period_label,
    # federal_application_ref) so we recompute the id via the same
    # helper.
    from reasonbook.matters.service import _idempotency_id
    from reasonbook.models import Decision, Dispute, Matter

    central_valley_matter = session.get(
        Matter,
        _idempotency_id(
            program_id="medicaid",
            awarding_agency="Department of Health and Human Services",
            period_label="FY26",
            federal_application_ref="SIG-TIER-SKIP-CA-MEDICAL",
        ),
    )
    hud_cdbg_matter = session.get(
        Matter,
        _idempotency_id(
            program_id="cdbg",
            awarding_agency="Department of Housing and Urban Development",
            period_label="FY26",
            federal_application_ref="HUD-CDBG-2026-DEMO",
        ),
    )

    _SUBJECT_TO_MATTER: dict[str, Matter | None] = {
        "ABLE FORCE, INC.": hud_cdbg_matter,
        "Central Valley Behavioral Health Network": central_valley_matter,
    }

    existing = (
        session.query(Dispute).filter(Dispute.tenant_id == tenant_id).all()
    )
    if existing:
        # Backfill related_matter_id on rows that missed it, and cascade
        # the linkage onto any Decisions already promoted via resolve.
        touched = 0
        for d in existing:
            wanted = _SUBJECT_TO_MATTER.get(d.subject_name)
            if wanted is not None and d.related_matter_id is None:
                d.related_matter_id = wanted.id
                touched += 1
            if d.linked_decision_id is not None and wanted is not None:
                dec = session.get(Decision, d.linked_decision_id)
                if dec is not None and dec.matter_id is None:
                    dec.matter_id = wanted.id
        session.flush()
        log.info(
            "disputes already seeded (%d rows); backfilled linkage on %d",
            len(existing),
            touched,
        )
        return

    now = datetime.now(UTC)

    session.add(
        Dispute(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agency_id=agencies["hud"].id,
            subject_name="ABLE FORCE, INC.",
            related_matter_id=hud_cdbg_matter.id if hud_cdbg_matter else None,
            candidate_a={
                "source": "SAM.gov",
                "legal_name": "ABLE FORCE, INC.",
                "uei": "R2M9K4XT7L21",
                "duns": "079283641",
                "address": "1200 K Street NW, Washington DC 20005",
                "status": "Active",
                "exclusion_status": "Not excluded",
            },
            candidate_b={
                "source": "USASpending",
                "legal_name": "ABLE FORCE INCORPORATED",
                "uei": "R2M9K4XT7L21",
                "duns": "079283641",
                "address": "1200 K St NW, Washington DC 20005",
                "recent_awards": 3,
                "prior_recipient": True,
            },
            status="open",
            opened_by=opened_by.id,
            opened_at=now - timedelta(days=1),
            notes=(
                "SAM.gov row shows the trailing ', INC.' punctuation; "
                "USASpending row spells it out. UEI + DUNS match — "
                "confirm same entity before the CDBG accept posts."
            ),
        )
    )
    session.add(
        Dispute(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agency_id=agencies["hhs"].id,
            related_matter_id=central_valley_matter.id if central_valley_matter else None,
            subject_name="Central Valley Behavioral Health Network",
            candidate_a={
                "source": "SAM.gov LEIE",
                "legal_name": "Central Valley Behavioral Health Network, LLC",
                "uei": "N7K3Q9WM4R58",
                "exclusion_status": "OIG-excluded 2024-03-12",
                "exclusion_reason": "Medicare/Medicaid fraud (§1128(a)(1))",
            },
            candidate_b={
                "source": "USASpending",
                "legal_name": "Central Valley Behavioral Health Network LLC",
                "uei": "N7K3Q9WM4R58",
                "cage_code": "8H2Y4",
                "recent_awards": 1,
                "award_period": "FY26",
            },
            status="open",
            opened_by=opened_by.id,
            opened_at=now - timedelta(hours=6),
            notes=(
                "UEIs match. If confirmed same entity, the pending "
                "CDBG award to this recipient must halt — LEIE "
                "exclusion is disqualifying under 2 CFR §180."
            ),
        )
    )
    session.add(
        Dispute(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            agency_id=agencies["dod"].id,
            subject_name="Advanced Robotics for Manufacturing Institute",
            candidate_a={
                "source": "USASpending FY25",
                "legal_name": "Advanced Robotics For Manufacturing Institute",
                "duns": "078425139",
                "address": "4795 Bayard St, Pittsburgh PA 15213",
            },
            candidate_b={
                "source": "USASpending FY26",
                "legal_name": "ARM Institute",
                "uei": "L4T7Z2B8Q9M6",
                "address": "4795 Bayard St, Pittsburgh PA 15213",
            },
            status="resolved_same",
            resolution="same_entity",
            resolution_rationale=(
                "Confirmed via UEI transition. DUNS retired 2022-04-04; "
                "UEI L4T7Z2B8Q9M6 issued as the successor per SAM.gov "
                "entity registration."
            ),
            opened_by=opened_by.id,
            opened_at=now - timedelta(days=4),
            resolved_by=opened_by.id,
            resolved_at=now - timedelta(days=3),
            notes="DUNS → UEI transition; standard identity carry-over.",
        )
    )
    session.flush()
    log.info("seeded 3 demo disputes for tenant=%s", tenant_id)


def _plant_demo_variations(session: Session) -> None:
    """Enrich a handful of seeded decisions with evidence_refs +
    action / outcome fields so the composite decision-record card
    demos read like real work.

    Idempotent — skips decisions that already have evidence populated.
    """
    from reasonbook.models import Decision

    _EVIDENCE_SAMPLES: list[list[dict[str, str]]] = [
        [
            {"kind": "sam_gov", "ref": "SAM.gov — recipient eligibility check clean"},
            {"kind": "exclusions", "ref": "HHS LEIE + SAM exclusions cross-check clean"},
            {"kind": "tier_accept", "ref": "Tier-acceptance stamped on 2026-06-30"},
            {"kind": "cite", "ref": "2 CFR §200.303 — internal controls"},
        ],
        [
            {"kind": "sam_gov", "ref": "SAM.gov — subrecipient risk assessment"},
            {"kind": "auto_flag", "ref": "IPERA anomaly on obligation timing"},
            {"kind": "attachment", "ref": "Recipient certification signed"},
        ],
        [
            {"kind": "cite", "ref": "Uniform Guidance 2 CFR §200"},
            {"kind": "tier_accept", "ref": "State pass-through acceptance"},
            {"kind": "sam_gov", "ref": "SAM.gov entity search clean"},
            {"kind": "exclusions", "ref": "HHS LEIE cross-check clean"},
        ],
        [
            {"kind": "auto_flag", "ref": "Fraud-risk screening triggered"},
            {"kind": "attachment", "ref": "Investigation memo attached"},
            {"kind": "cite", "ref": "31 USC §3801 — improper payments"},
        ],
    ]

    # Pick up to 8 decisions across the workflow spectrum; skip any that
    # already carry evidence to keep the pass idempotent.
    targets = (
        session.query(Decision)
        .filter(Decision.evidence_refs.is_(None))
        .filter(Decision.status.in_(("in_progress", "decided", "closed")))
        .order_by(Decision.decision_number)
        .limit(8)
        .all()
    )
    enriched = 0
    for i, d in enumerate(targets):
        d.evidence_refs = _EVIDENCE_SAMPLES[i % len(_EVIDENCE_SAMPLES)]

        # Populate action timestamps on decided / closed decisions so
        # the composite card's Action stage renders real times.
        now = datetime.now(UTC)
        if d.status in ("decided", "closed") and d.action_started_at is None:
            d.action_started_at = now - timedelta(days=2)
        if d.status == "closed" and d.action_completed_at is None:
            d.action_completed_at = now - timedelta(days=1)

        # Give closed decisions a real outcome narrative if they don't
        # already carry one.
        if d.status == "closed" and not d.outcome_text:
            d.outcome_text = (
                "Award funded per approved terms. Recipient acknowledged "
                "receipt; reporting cycle scheduled. No conditions, no "
                "follow-up decisions triggered."
            )
            d.outcome_impact = "positive"
            d.outcome_recorded_at = now

        enriched += 1
    session.flush()
    log.info("demo variations: enriched %d decisions with evidence/action/outcome", enriched)


def _plant_planned_disbursements(session: Session) -> None:
    """Backfill matters.planned_disbursement_at for demo.

    Pick a slice of USAspending-import matters that have no adverse
    signals and turn them into Incoming-band candidates:
      · set planned_disbursement_at 15..75 days out (deterministic
        spread across the 30d / 90d / FY horizon toggles), AND
      · close their open operational decisions with a demo outcome
        so the classifier doesn't route them to Inflight instead.

    Matters carrying alerts (tier-skip Central Valley, etc.) are left
    untouched — they land in At-risk naturally. Matters where we don't
    plant a date keep their active decisions and land in Inflight.

    Idempotent: only writes when planned_disbursement_at is NULL.
    """
    from reasonbook.decisions.scope import OPEN_STATUSES
    from reasonbook.models import Alert, Decision, Matter

    now = datetime.now(UTC)

    matters_needing_date = (
        session.query(Matter)
        .filter(Matter.planned_disbursement_at.is_(None))
        .order_by(Matter.created_at.asc(), Matter.id.asc())
        .all()
    )
    if not matters_needing_date:
        return

    matter_ids = [m.id for m in matters_needing_date]

    open_alert_matter_ids = {
        row[0]
        for row in session.execute(
            select(Alert.matter_id)
            .where(
                Alert.matter_id.in_(matter_ids),
                Alert.current_status.in_(("new", "reopened")),
            )
            .distinct()
        ).all()
        if row[0] is not None
    }

    # Healthy NIH-R01 exemplar has no open alerts by design, but it's
    # meant to demonstrate "a fully-governed matter in flight" — not
    # "scheduled disbursement, no active work." Excluding it here keeps
    # its tier-accept (DEC-0089-style) decision in_progress so the
    # feature-tour narration's "recipient's own tier-accept still in
    # progress" line stays true.
    healthy_r01_id = _idempotency_id_for_healthy_r01()
    open_alert_matter_ids.add(healthy_r01_id)

    # Target count — small enough to keep the demo Inflight band the
    # majority (matches the mockup's 3 · 8 · 3 shape) but big enough to
    # populate Incoming across all three horizon toggles.
    incoming_target = 6
    offsets_days = (15, 30, 45, 60, 75, 120)

    planted = 0
    closed_decisions = 0
    for matter in matters_needing_date:
        if planted >= incoming_target:
            break
        if matter.id in open_alert_matter_ids:
            continue
        matter.planned_disbursement_at = now + timedelta(
            days=offsets_days[planted % len(offsets_days)]
        )
        # Close open decisions on this matter — the Incoming band
        # depicts a scheduled disbursement that hasn't kicked off
        # operational work yet.
        open_decs = (
            session.query(Decision)
            .filter(
                Decision.matter_id == matter.id,
                Decision.status.in_(OPEN_STATUSES),
            )
            .all()
        )
        for d in open_decs:
            d.status = "closed"
            d.closed_at = d.closed_at or now
            if not d.outcome_text:
                d.outcome_text = (
                    "Federal authorization on file; disbursement scheduled. "
                    "No operational decisions outstanding at this stage."
                )
                d.outcome_impact = "positive"
                d.outcome_recorded_at = now
            closed_decisions += 1
        planted += 1

    session.flush()
    log.info(
        "demo variations: planted planned_disbursement_at on %d matters (closed %d open decisions)",
        planted,
        closed_decisions,
    )


def _claim_inflight_decisions_for_demo(session: Session, *, jamie: User) -> None:
    """Claim the leading open decision on a handful of Inflight matters
    for Jamie so the demo Inbox landing shows "your queue" with a
    plausible workload instead of an empty Mine scope.

    Idempotent: skips decisions that already carry an owner_id.
    """
    from reasonbook.decisions.scope import OPEN_STATUSES
    from reasonbook.models import Decision, Matter

    now = datetime.now(UTC)

    inflight_matters = (
        session.query(Matter)
        .filter(Matter.planned_disbursement_at.is_(None))
        .order_by(Matter.created_at.asc(), Matter.id.asc())
        .limit(8)
        .all()
    )
    claimed = 0
    for matter in inflight_matters:
        oldest_open = (
            session.query(Decision)
            .filter(
                Decision.matter_id == matter.id,
                Decision.status.in_(OPEN_STATUSES),
                Decision.owner_id.is_(None),
            )
            .order_by(Decision.created_at.asc())
            .first()
        )
        if oldest_open is None:
            continue
        oldest_open.owner_id = jamie.id
        oldest_open.assigned_at = oldest_open.assigned_at or now
        oldest_open.acknowledged_at = oldest_open.acknowledged_at or now
        if oldest_open.status == "open":
            oldest_open.status = "in_progress"
        claimed += 1
    session.flush()
    log.info("demo variations: claimed %d Inflight decisions for jamie.kim", claimed)


def _backfill_agency_ids(
    session: Session, *, agencies: dict[str, Agency]
) -> None:
    """Idempotent final pass that stamps agency_id on every scope-
    carrier row that a callsite forgot (or couldn't) set.

    Rules, in order of preference:
      1. Matter: awarding_agency string → agency_id
      2. Matter (fallback): program_id → agency_id
      3. Decision: derive from its matter's agency_id
      4. Decision (matter-less): workflow_id → agency_id
      5. Alert: derive from its matter's agency_id

    Only touches rows where the target column IS NULL — safe to re-run
    after every seed. Prints counts so re-runs read as no-ops.
    """
    from reasonbook.models import Alert, Decision, Matter

    slug_to_id = {slug: a.id for slug, a in agencies.items()}

    # ── Matters ────────────────────────────────────────────────────
    matter_updates = 0
    for b in session.query(Matter).filter(Matter.agency_id.is_(None)).all():
        slug = AWARDING_AGENCY_TO_SLUG.get(b.awarding_agency)
        if slug is None:
            slug = _PROGRAM_ID_TO_AGENCY_SLUG.get(b.program_id)
        if slug is not None and slug in slug_to_id:
            b.agency_id = slug_to_id[slug]
            matter_updates += 1
    session.flush()

    # ── Decisions ─────────────────────────────────────────────────
    # Derive from matter first (most accurate); fall back to workflow
    # for matter-less decisions.
    decision_updates = 0
    decisions = (
        session.query(Decision).filter(Decision.agency_id.is_(None)).all()
    )
    for d in decisions:
        agency_id = None
        if d.matter_id is not None:
            matter = session.get(Matter, d.matter_id)
            if matter is not None and matter.agency_id is not None:
                agency_id = matter.agency_id
        if agency_id is None:
            slug = _PROGRAM_ID_TO_AGENCY_SLUG.get(d.workflow_id)
            if slug is not None:
                agency_id = slug_to_id.get(slug)
        if agency_id is not None:
            d.agency_id = agency_id
            decision_updates += 1
    session.flush()

    # ── Alerts ────────────────────────────────────────────────────
    alert_updates = 0
    alerts = session.query(Alert).filter(Alert.agency_id.is_(None)).all()
    for a in alerts:
        if a.matter_id is not None:
            matter = session.get(Matter, a.matter_id)
            if matter is not None and matter.agency_id is not None:
                a.agency_id = matter.agency_id
                alert_updates += 1
    session.flush()

    log.info(
        "agency_id backfill: matters=%d decisions=%d alerts=%d",
        matter_updates,
        decision_updates,
        alert_updates,
    )


def _upsert_agency_scope(
    session: Session,
    *,
    user: User,
    agency: Agency,
    granted_by: User,
    includes_descendants: bool = True,
    notes: str | None = None,
) -> None:
    """Idempotent cross-agency grant. Skips insertion if an active grant
    for the same (user, agency) pair already exists."""
    existing = (
        session.query(UserAgencyScope)
        .filter_by(user_id=user.id, agency_id=agency.id, revoked_at=None)
        .one_or_none()
    )
    if existing is not None:
        return
    session.add(
        UserAgencyScope(
            id=uuid.uuid4(),
            user_id=user.id,
            agency_id=agency.id,
            includes_descendants=includes_descendants,
            granted_by=granted_by.id,
            notes=notes,
        )
    )
    session.flush()
    log.info(
        "granted cross-agency scope: user=%s agency=%s descendants=%s",
        user.username,
        agency.agency_slug,
        includes_descendants,
    )


def _upsert_tenant(session: Session, *, has_oversight: bool = True) -> Tenant:
    # has_oversight kept as a no-op kwarg for call-site compatibility; the
    # billing-tier gate was removed (single-tenant, oversight always on).
    tenant = session.get(Tenant, TENANT_ID)
    if tenant is None:
        tenant = Tenant(
            tenant_id=TENANT_ID,
            name="United States Federal Government",
            org_type="FEDERAL_GOVERNMENT",
            regulator=None,
            asset_size_band=None,
        )
        session.add(tenant)
        session.flush()
        log.info("inserted organization %s", TENANT_ID)
    return tenant


def _upsert_user(
    session: Session,
    *,
    username: str,
    email: str,
    name: str,
    title: str,
    role: str,
    password_hash: str,
    tier: str = "federal",
    participant_org_id: uuid.UUID | None = None,
    agency: Agency | None = None,
) -> User:
    user = session.query(User).filter_by(username=username).one_or_none()
    if user is None:
        user = User(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            agency_id=agency.id if agency is not None else None,
            username=username,
            email=email,
            password_hash=password_hash,
            name=name,
            title=title,
            role=role,
            status="active",
            email_verified=True,
            tier=tier,
            participant_org_id=participant_org_id,
        )
        session.add(user)
        session.flush()
        log.info(
            "inserted user %s (%s, tier=%s, agency=%s)",
            username,
            role,
            tier,
            agency.agency_slug if agency else "—",
        )
    elif agency is not None and user.agency_id != agency.id:
        # Backfill agency assignment on existing rows so re-running the
        # seed after the tenancy migration lands doesn't leave users
        # unassigned.
        user.agency_id = agency.id
        session.flush()
        log.info(
            "backfilled agency %s onto existing user %s",
            agency.agency_slug,
            username,
        )
    return user


def _upsert_authority(
    session: Session,
    *,
    user: User,
    workflow_id: str,
    level: int,
    granted_by: User,
    limits: dict[str, Any] | None = None,
    oversight_role: str | None = None,
    oversight_domains_owned: list[str] | None = None,
    oversight_can_record_committee_action: bool = False,
) -> None:
    existing = (
        session.query(UserWorkflowAuthority)
        .filter_by(user_id=user.id, workflow_id=workflow_id, revoked_at=None)
        .one_or_none()
    )
    if existing is None:
        session.add(
            UserWorkflowAuthority(
                id=uuid.uuid4(),
                user_id=user.id,
                workflow_id=workflow_id,
                level=level,
                limits=limits,
                granted_by=granted_by.id,
                oversight_role=oversight_role,
                oversight_domains_owned=oversight_domains_owned,
                oversight_can_record_committee_action=oversight_can_record_committee_action,
            )
        )
        session.flush()
        log.info(
            "inserted authority user=%s workflow=%s level=%s%s",
            user.username,
            workflow_id,
            level,
            f" oversight_role={oversight_role}" if oversight_role else "",
        )


def _upsert_override(
    session: Session,
    *,
    workflow_id: str,
    config_key: str,
    value: Any,
    modified_by: User,
    change_note: str | None = None,
) -> None:
    """Idempotently set a tenant override.

    Append-only model — a re-run with a different value writes a new row
    and supersedes the prior one (to mimic the OverrideManager's audit
    behaviour). For the seed we keep things simple: if an active override
    on the same key already exists with the same value, do nothing.
    """
    existing = (
        session.query(AgencySemanticOverride)
        .filter_by(
            tenant_id=TENANT_ID,
            workflow_id=workflow_id,
            config_key=config_key,
            superseded_at=None,
        )
        .one_or_none()
    )
    if existing is not None and existing.config_value == value:
        return
    if existing is not None:
        existing.superseded_at = datetime.now(UTC)
    session.add(
        AgencySemanticOverride(
            id=uuid.uuid4(),
            tenant_id=TENANT_ID,
            workflow_id=workflow_id,
            config_key=config_key,
            config_value=value,
            modified_by=modified_by.id,
            change_note=change_note,
        )
    )
    session.flush()
    log.info(
        "inserted tenant override workflow=%s key=%s value=%s",
        workflow_id,
        config_key,
        value,
    )


def _upsert_supervisor(
    session: Session,
    *,
    user: User,
    supervisor: User,
    workflow_id: str | None,
) -> None:
    existing = (
        session.query(UserSupervisor)
        .filter_by(
            user_id=user.id,
            supervisor_id=supervisor.id,
            workflow_id=workflow_id,
            effective_to=None,
        )
        .one_or_none()
    )
    if existing is None:
        session.add(
            UserSupervisor(
                id=uuid.uuid4(),
                tenant_id=TENANT_ID,
                user_id=user.id,
                supervisor_id=supervisor.id,
                workflow_id=workflow_id,
            )
        )
        session.flush()
        log.info(
            "inserted supervisor user=%s supervisor=%s workflow=%s",
            user.username,
            supervisor.username,
            workflow_id,
        )


def _upsert_usaspending_connector(session: Session) -> None:
    """Seed the USASpending.gov connector. Idempotent on slug."""
    existing = (
        session.query(Connector).filter_by(slug="usaspending").one_or_none()
    )
    last_sync = datetime.now(UTC) - timedelta(hours=18)
    next_sync = datetime.now(UTC) + timedelta(hours=6)
    if existing is None:
        session.add(
            Connector(
                slug="usaspending",
                name="USASpending.gov",
                source_description="Public federal awards & sub-awards · no auth required",
                description=(
                    "Prime + sub awards across all federal agencies. "
                    "Hash-chained ledger, append-only ingestion, "
                    "tier-skip signal detection."
                ),
                status="connected",
                filter_label="Department of Health and Human Services",
                schedule_cron="0 4 * * *",
                schedule_label="daily · 04:00 UTC",
                last_sync_at=last_sync,
                last_sync_record_count=3421,
                last_window_start=date(2024, 10, 1),
                last_window_end=date(2024, 12, 31),
                next_sync_at=next_sync,
                integrity_verified=True,
                integrity_verified_at=last_sync,
                feeds_workflow_ids=["cdbg", "nih-r01", "treasury-disbursement"],
            )
        )
        log.info("Seeded USASpending.gov connector")


def _upsert_placeholder_connectors(session: Session) -> None:
    """Seed placeholder rows for connectors referenced in the demo but not
    yet wired to a live producer. Each row carries a plausible status,
    schedule, and last-sync fingerprint so the /settings/connectors surface
    tells the "signals come from federal-authoritative sources" story
    without pretending every connector is live.

    Idempotent on slug. Real connectors will overwrite these rows when
    they ship.
    """
    now = datetime.now(UTC)

    placeholders = [
        {
            "slug": "sam-gov-entity",
            "name": "SAM.gov Entity",
            "source_description": "Federal entity registrations · UEI, CAGE, POC · API-keyed",
            "description": (
                "Authoritative federal entity records. Used to enrich fund-flow "
                "nodes with legal name, UEI, address, authorised official."
            ),
            "status": "connected",
            "filter_label": "Active registrations",
            "schedule_cron": "0 6 * * *",
            "schedule_label": "daily · 06:00 UTC",
            "last_sync_at": now - timedelta(hours=14),
            "last_sync_record_count": 118422,
            "last_window_start": date(2026, 6, 1),
            "last_window_end": date(2026, 7, 1),
            "next_sync_at": now + timedelta(hours=10),
            "integrity_verified": True,
            "integrity_verified_at": now - timedelta(hours=14),
            "feeds_workflow_ids": ["cdbg", "nih-r01", "medicaid", "snap"],
        },
        {
            "slug": "sam-gov-exclusions",
            "name": "SAM.gov Exclusions",
            "source_description": "Government-wide active exclusions · 2 CFR 180 · API-keyed",
            "description": (
                "Suspension and debarment records the awarding official must "
                "check before every federal award. Powers the "
                "sam_gov_exclusion signal."
            ),
            "status": "connected",
            "filter_label": "Active exclusions only",
            "schedule_cron": "*/30 * * * *",
            "schedule_label": "every 30 minutes",
            "last_sync_at": now - timedelta(minutes=12),
            "last_sync_record_count": 87604,
            "last_window_start": date(2026, 6, 1),
            "last_window_end": date(2026, 7, 2),
            "next_sync_at": now + timedelta(minutes=18),
            "integrity_verified": True,
            "integrity_verified_at": now - timedelta(minutes=12),
            "feeds_workflow_ids": ["grant-debarment", "cdbg", "medicaid"],
        },
        {
            "slug": "hhs-oig-leie",
            "name": "HHS OIG LEIE",
            "source_description": "List of Excluded Individuals and Entities · 42 CFR 1001 · monthly snapshot",
            "description": (
                "HHS Office of Inspector General exclusion list. Match "
                "prohibits payment from federal health-care programs. "
                "Powers the leie_exclusion signal."
            ),
            "status": "connected",
            "filter_label": "All exclusion reasons",
            "schedule_cron": "0 5 1 * *",
            "schedule_label": "monthly · 1st of month · 05:00 UTC",
            "last_sync_at": now - timedelta(days=2, hours=7),
            "last_sync_record_count": 78321,
            "last_window_start": date(2026, 6, 1),
            "last_window_end": date(2026, 7, 1),
            "next_sync_at": now + timedelta(days=28),
            "integrity_verified": True,
            "integrity_verified_at": now - timedelta(days=2, hours=7),
            "feeds_workflow_ids": ["grant-debarment", "medicaid"],
        },
        {
            "slug": "treasury-dnp",
            "name": "Treasury Do Not Pay",
            "source_description": "IPERIA cross-source match service · TIN-scoped access · pending pilot credentials",
            "description": (
                "Working-system match against DMF, SAM Exclusions, CAIVRS, "
                "and Treasury delinquent-debt. Powers the treasury_dnp_match "
                "signal. Pilot access requested; credentials pending."
            ),
            "status": "degraded",
            "filter_label": "Pilot: HHS/CMS payments only",
            "schedule_cron": "0 3 * * *",
            "schedule_label": "daily · 03:00 UTC (awaiting credentials)",
            "last_sync_at": now - timedelta(days=6),
            "last_sync_record_count": 12,
            "last_window_start": date(2026, 6, 25),
            "last_window_end": date(2026, 6, 25),
            "next_sync_at": None,
            "integrity_verified": False,
            "integrity_verified_at": None,
            "feeds_workflow_ids": ["medicaid", "treasury-disbursement"],
        },
        {
            "slug": "usda-fns-paris",
            "name": "USDA FNS PARIS",
            "source_description": "Public Assistance Reporting Information System · cross-state duplicate detection · not yet configured",
            "description": (
                "Cross-state benefit-duplication check for SNAP, TANF, and "
                "child-nutrition programs. Powers the duplicate_claim and "
                "phantom_subrecipient signals. Connection pending USDA "
                "FNS system-access approval."
            ),
            "status": "disconnected",
            "filter_label": None,
            "schedule_cron": None,
            "schedule_label": "not yet scheduled",
            "last_sync_at": None,
            "last_sync_record_count": None,
            "last_window_start": None,
            "last_window_end": None,
            "next_sync_at": None,
            "integrity_verified": False,
            "integrity_verified_at": None,
            "feeds_workflow_ids": ["snap"],
        },
    ]

    for spec in placeholders:
        existing = (
            session.query(Connector).filter_by(slug=spec["slug"]).one_or_none()
        )
        if existing is not None:
            continue
        session.add(Connector(**spec))
        log.info("Seeded %s connector (%s)", spec["name"], spec["status"])


def seed(*, include_apex: bool = True) -> None:
    """Insert dev seed data.

    ``include_apex`` defaults to True for full demo coverage. Tests that
    synthesise their own decision data and assert against deterministic
    counts pass ``include_apex=False`` to skip the seeded apex cycles
    and decisions.

    These are NON-PRODUCTION demo accounts (example.org addresses, a shared
    password from REASONBOOK_SEED_PASSWORD). Never enable demo seeding in a
    production deployment.
    """
    if not DEMO_PASSWORD:
        raise RuntimeError(
            "REASONBOOK_SEED_PASSWORD is not set. Demo seeding needs a password "
            "(no default ships in code). Set REASONBOOK_SEED_PASSWORD and retry."
        )
    log.warning("seeding NON-PRODUCTION demo accounts (example.org) — do not use in production")
    pw = _hash(DEMO_PASSWORD)

    with session_scope() as session:
        _upsert_tenant(session)

        # Federal agency hierarchy sits on top of the single organization.
        agencies = _seed_agencies(session)

        sarah = _upsert_user(
            session,
            username="sarah.mitchell",
            email="sarah.mitchell@example.org",
            name="Sarah Mitchell",
            title="Director, Office of Extramural Research",
            role="admin",
            password_hash=pw,
            agency=agencies["nih-oer"],
        )
        jamie = _upsert_user(
            session,
            username="jamie.kim",
            email="jamie.kim@example.org",
            name="Jamie Kim",
            title="Program Officer (Extramural)",
            role="member",
            password_hash=pw,
            agency=agencies["nih-oer"],
        )
        marcus = _upsert_user(
            session,
            username="marcus.webb",
            email="marcus.webb@example.org",
            name="Marcus Webb",
            title="Chief Program Integrity Officer",
            role="member",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        _upsert_user(
            session,
            username="david.park",
            email="david.park@example.org",
            name="David Park",
            title="OIG Liaison",
            role="member",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        # Marcus @ HHS: explicit grant to NIH + NIH-OER so he can see
        # descendant decisions per the "explicit, not implicit" rule.
        _upsert_agency_scope(
            session,
            user=marcus,
            agency=agencies["hhs"],
            granted_by=sarah,
            includes_descendants=True,
            notes="CPIO cross-bureau read across HHS descendants",
        )

        # ── Demo personas (narratives v1.0 §2) ─────────────────────────
        # 12 additional personas bring the seed to the full 16-persona
        # roster the demo narratives reference. C-suite expansion (Priya,
        # Daniel) carry their own apex roles + workflow ownership; the
        # workflow VPs cover one operational workflow each so every
        # workflow has a named owner; the three board personas exist for
        # cycle-ratification narratives (5, 6) — they cannot own apex
        # decisions, only ratify them via oversight_can_record_committee_action.
        priya = _upsert_user(
            session,
            username="priya.shah",
            email="priya.shah@example.org",
            name="Priya Shah",
            title="Senior Advisor for Policy",
            role="admin",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        daniel = _upsert_user(
            session,
            username="daniel.ortiz",
            email="daniel.ortiz@example.org",
            name="Daniel Ortiz",
            title="Senior Advisor for Budget",
            role="admin",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        walter = _upsert_user(
            session,
            username="walter.knox",
            email="walter.knox@example.org",
            name="Walter Knox",
            title="Inspector General",
            role="member",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        linda = _upsert_user(
            session,
            username="linda.peters",
            email="linda.peters@example.org",
            name="Linda Peters",
            title="Audit Committee Chair",
            role="member",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        gerald = _upsert_user(
            session,
            username="gerald.tan",
            email="gerald.tan@example.org",
            name="Gerald Tan",
            title="Oversight Liaison",
            role="member",
            password_hash=pw,
            agency=agencies["hhs"],
        )
        # Walter is IG — grant cross-agency read across HUD + DoD so
        # the oversight demo can span multiple departments (matches
        # OIG cross-agency-examiner archetype from Commit 2 demo arcs).
        _upsert_agency_scope(
            session,
            user=walter,
            agency=agencies["hud"],
            granted_by=sarah,
            includes_descendants=True,
            notes="IG cross-agency read on HUD",
        )
        _upsert_agency_scope(
            session,
            user=walter,
            agency=agencies["dod"],
            granted_by=sarah,
            includes_descendants=True,
            notes="IG cross-agency read on DoD",
        )
        _upsert_agency_scope(
            session,
            user=walter,
            agency=agencies["state"],
            granted_by=sarah,
            includes_descendants=True,
            notes="IG cross-agency read on State",
        )
        _upsert_agency_scope(
            session,
            user=walter,
            agency=agencies["usda"],
            granted_by=sarah,
            includes_descendants=True,
            notes="IG cross-agency read on USDA",
        )
        # HHS descendants (NIH, NIH-OER) are already covered by Walter's
        # implicit HHS primary; no need for an explicit descendant grant
        # on his own department.
        _upsert_agency_scope(
            session,
            user=walter,
            agency=agencies["hhs"],
            granted_by=sarah,
            includes_descendants=True,
            notes="IG descendant cascade within HHS",
        )

        # Entitlements were retired in the DG-substrate cleanup:
        # single-tenant DP has no per-workflow gating, so we no longer
        # need to insert tenant_entitlements rows for every program_id
        # a decision might land under. Row visibility is enforced by
        # apply_tier_scope only.

        # ── Connector registry ─────────────────────────────────────────
        # The USASpending.gov collector is the first federal-system data
        # source wired into DP. Run state surfaces at /settings/connectors.
        _upsert_usaspending_connector(session)
        _upsert_placeholder_connectors(session)

        # ── Apex (federalized v2.0) ────────────────────────────────────
        # Post-pivot personas: agency_head / cpio / cco / cfo for the
        # executive grants; inspector_general + audit_committee_chair as
        # the two oversight personas that record committee action.
        if include_apex:
            # Sarah owns apex as the agency head with authority across all
            # 9 domains. Agency head parallels the legacy CEO in the
            # corporate framing (can_own_domain returns True for any
            # domain when oversight_role == 'agency_head').
            _upsert_authority(
                session,
                user=sarah,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=5,
                granted_by=sarah,
                oversight_role="agency_head",
                oversight_domains_owned=list(DECISION_DOMAINS),
            )
            # Marcus carries CPIO apex authority for the program-integrity
            # domains (fraud-loss tolerance + subrecipient/vendor oversight
            # + the governance program itself).
            _upsert_authority(
                session,
                user=marcus,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=4,
                granted_by=sarah,
                oversight_role="cpio",
                oversight_domains_owned=[
                    "fraud_loss_tolerance",
                    "subrecipient_and_vendor_oversight",
                    "governance_improvement",
                ],
            )
            # Priya owns the congressional_and_regulatory_posture apex
            # domain (CCO — coordinates GAO / OIG / OMB / Congress response).
            _upsert_authority(
                session,
                user=priya,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=4,
                granted_by=sarah,
                oversight_role="cco",
                oversight_domains_owned=["congressional_and_regulatory_posture"],
            )
            # Daniel owns appropriations_and_obligations as CFO.
            _upsert_authority(
                session,
                user=daniel,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=4,
                granted_by=sarah,
                oversight_role="cfo",
                oversight_domains_owned=["appropriations_and_obligations"],
            )
            # Oversight personas — record committee / IG action but do
            # NOT own apex decisions. oversight_can_record_committee_action gates
            # the special "noted_by_committee" / "endorsed_by_committee"
            # activities (DB column kept under its legacy name until the
            # rename migration; the predicate reads it through
            # can_record_board_action()).
            #
            # Walter is the agency's Inspector General (statutorily
            # independent; co-located).
            _upsert_authority(
                session,
                user=walter,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=7,
                granted_by=sarah,
                oversight_role="inspector_general",
                oversight_domains_owned=[],
                oversight_can_record_committee_action=True,
            )
            # Linda chairs the agency's internal audit committee.
            _upsert_authority(
                session,
                user=linda,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=6,
                granted_by=sarah,
                oversight_role="audit_committee_chair",
                oversight_domains_owned=[],
                oversight_can_record_committee_action=True,
            )
            # Gerald is the oversight liaison — coordinates with GAO /
            # OMB / Congressional staff. Staff role; cannot endorse or
            # own apex decisions but can link evidence.
            _upsert_authority(
                session,
                user=gerald,
                workflow_id=OVERSIGHT_WORKFLOW_ID,
                level=3,
                granted_by=sarah,
                oversight_role="oversight_liaison",
                oversight_domains_owned=[],
                oversight_can_record_committee_action=False,
            )
            _seed_apex_cycles_and_decisions(session, sarah=sarah, marcus=marcus)

        # ── Federal determinations through the promotion service ──────
        # Seeds the determination_ledger + a handful of promoted Decisions
        # for the new archetype/program model so the Caseload rail has
        # something to land on. Idempotent — keyed on (program_id,
        # input identifier).
        _seed_federal_determinations(
            session,
            tenant_id=TENANT_ID,
            jamie=jamie,
            marcus=marcus,
            sarah=sarah,
            agencies=agencies,
        )

        # ── Alerts corpus (ALERTS-SPEC.md §9 step 4) ──────────────────
        # 8 fake alerts mirroring the mockup at
        # docs/architecture/UI/alerts.html. All federal tier; tier scope
        # is a no-op until the tenancy migration lands. Idempotent —
        # skipped if any alerts already exist for the tenant.
        _seed_alerts(session, tenant_id=TENANT_ID)

        # ── Tenancy substrate: one CDBG matter + state/recipient users ─
        # TENANCY-MODEL.md §10 step 6. Exercises every tier (federal,
        # state, recipient) end-to-end so apply_tier_scope has real data
        # to filter against. Idempotent — re-seeding is a no-op via the
        # matter-create deterministic id + user-upsert username checks.
        _seed_tenancy_matter(session, jamie=jamie, password_hash=pw, agencies=agencies)

        # ── Real-data demo matter (USAspending pull) ─────────────────
        # Bootstraps the agency_catalog + recipient participant_orgs
        # from data/*.csv on first seed, then layers a second matter
        # whose names come from the real USAspending corpus. Keeps the
        # synthetic GA/OH/Delta matter alongside (tests rely on it);
        # this one is for screen captures and credibility checks.
        _seed_real_data_matter(session, jamie=jamie, agencies=agencies)

        # ── Healthy NIH-R01 exemplar (feature-tour demo, clean matter) ─
        # Direct-to-institution 2-tier award with zero adverse signals
        # and all control points cleared. Foil to the Central Valley
        # tier-skip matter — shows what a fully-governed case file looks
        # like when the playbook runs cleanly. Powers the "here's a
        # complete record" scene in the feature-tour narration.
        _seed_healthy_r01_matter(
            session,
            jamie=jamie,
            marcus=marcus,
            sarah=sarah,
            agencies=agencies,
        )

        # ── Fund-flow matters corpus (Tuesday demo) ──────────────────
        # 24 real federal awards from the USAspending collector via
        # docs/fund-flow/data/matters.json. Idempotent; the matter
        # service's deterministic-id check makes re-seeds no-ops.
        from scripts.import_matters import load_matters

        load_matters(session, agencies=agencies)

        # ── Tier-skip demo (Day 3 of Tuesday demo) ───────────────────
        # Two synthetic matters modelled on current high-profile
        # federal-fraud patterns — Minnesota Feeding Our Future-style
        # USDA child-nutrition bypass + California Medi-Cal-style
        # bypass. Generic recipient names (no defendants). Both render
        # as red-flagged tier-skip graphs.
        _plant_tier_skip_demo(
            session,
            jamie=jamie,
            agencies=agencies,
            ref="SIG-TIER-SKIP-MN-CHILD-NUTRITION",
            agency="Department of Agriculture",
            agency_short="USDA",
            expected_parent="Minnesota Department of Education",
            recipient="Twin Cities Nutrition Sponsor 042",
            amount_dollars=4_200_000,
            program_id="snap",
            body=(
                "$4,200,000 reached a Twin Cities nutrition sponsor "
                "directly from USDA Child Nutrition Programs, bypassing "
                "the Minnesota Department of Education prime-sponsor tier. "
                "Phantom-sub pattern consistent with recent MN child-"
                "nutrition prosecutions; flagged for governance review."
            ),
        )
        _plant_tier_skip_demo(
            session,
            jamie=jamie,
            agencies=agencies,
            ref="SIG-TIER-SKIP-CA-MEDICAL",
            agency="Department of Health and Human Services",
            agency_short="HHS",
            expected_parent="California Department of Health Care Services",
            recipient="Central Valley Behavioral Health Network",
            amount_dollars=1_800_000,
            program_id="medicaid",
            body=(
                "$1,800,000 reached a Central Valley behavioral-health "
                "vendor directly from HHS Medi-Cal federal-share, bypassing "
                "the California Department of Health Care Services prime-"
                "recipient tier. Tier-skip pattern consistent with recent "
                "CA Medi-Cal billing-vendor investigations."
            ),
        )
        # Colorado Medicaid tier-skip — neutral-state counterexample so
        # the demo doesn't sit only on politically-charged jurisdictions.
        _plant_tier_skip_demo(
            session,
            jamie=jamie,
            agencies=agencies,
            ref="SIG-TIER-SKIP-CO-MEDICAID",
            agency="Department of Health and Human Services",
            agency_short="HHS",
            expected_parent="Colorado Department of Health Care Policy and Financing",
            recipient="Front Range Behavioral Health Network",
            amount_dollars=2_400_000,
            program_id="medicaid",
            body=(
                "$2,400,000 reached a Front Range behavioral-health "
                "vendor directly from HHS state-Medicaid federal-share, "
                "bypassing the Colorado Department of Health Care Policy "
                "and Financing prime-recipient tier."
            ),
        )
        # Iowa child-nutrition tier-skip — matches the MN pattern in a
        # neutral jurisdiction so the tier-skip class stays legible even
        # if the viewer parks on the politically-adjacent examples.
        _plant_tier_skip_demo(
            session,
            jamie=jamie,
            agencies=agencies,
            ref="SIG-TIER-SKIP-IA-CHILD-NUTRITION",
            agency="Department of Agriculture",
            agency_short="USDA",
            expected_parent="Iowa Department of Education",
            recipient="Cedar Rapids Nutrition Sponsor 017",
            amount_dollars=3_100_000,
            program_id="snap",
            body=(
                "$3,100,000 reached a Cedar Rapids nutrition sponsor "
                "directly from USDA Child Nutrition Programs, bypassing "
                "the Iowa Department of Education prime-sponsor tier."
            ),
        )

        # Enrich the MN tier-skip matter with extra decision records so
        # the Matters inspector's Decision-records panel shows a real
        # collection (originating + investigation hold + authority
        # recommendation), not just the originating one. Demonstrates
        # the "matter = collection of decision records" framing.
        _plant_tier_skip_extra_decisions(
            session,
            matter_ref="SIG-TIER-SKIP-MN-CHILD-NUTRITION",
            actor=sarah,
        )

        # Plant per-tier acceptance decisions on every matter. Matches
        # the "every consequential participant has a decision" model —
        # state pass-throughs accept federal funds, recipients accept
        # the prime, sub-recipients accept the sub-award. Planter is
        # idempotent and correctly skips the federal-direct / state-
        # skipped sentinels.
        from reasonbook.models import Matter

        for b in session.query(Matter).all():
            _plant_tier_accept_decisions(session, matter_id=b.id, actor=sarah)

        # Materialize control points on the demo matter + walk a few
        # into cleared / named-gap so §5 Process adherence has real
        # rows to render. Keeps the tier-skip story consistent: state-
        # tier gates are named-gaps because the state was bypassed.
        _seed_control_points_for_central_valley(session, sarah=sarah)

        # Layer a second per-node signal on Central Valley so the
        # fund-flow visualization exercises multi-signal attribution:
        # tier_skip paints the state tier + adjacent edges red;
        # identity paints the subrecipient node red. Together they
        # read as "state was skipped AND the subrecipient has an
        # identity problem" on one graph.
        _plant_identity_signal_on_central_valley(session)

        # Seed the Register's non-matter branches: promote a couple of
        # tier-skip alerts (Cases) + create a few bare Decisions
        # (Decisions awaiting review). Without this the placeholder
        # branches read as empty even though the model supports them.
        _plant_register_demo_data(session, actor=sarah)

        # Final pass: stamp agency_id on every scope-carrier row that
        # slipped past the callsite plumbing (idempotent-noop matters,
        # tier-accept / tier-skip planted decisions, alerts). Idempotent —
        # only touches rows where agency_id IS NULL.
        _backfill_agency_ids(session, agencies=agencies)

        # Demo enrichment: give a handful of decisions real evidence
        # references + action timestamps + outcome narrative so the
        # composite card demos read like actual work instead of empty
        # stages. Idempotent — skips decisions with existing evidence.
        _plant_demo_variations(session)

        # Backfill planned_disbursement_at on matters with no adverse
        # signals + no open decisions — populates the Matters-first
        # Inbox's Incoming band without competing with Inflight/At-risk.
        _plant_planned_disbursements(session)

        # Claim a handful of the remaining Inflight matters' open
        # decisions for Jamie so the Matters-first Inbox has a real
        # Mine scope on the demo path (default landing shows "your
        # queue", not "all agency").
        _claim_inflight_decisions_for_demo(session, jamie=jamie)

        # Identity-resolution disputes — the third Register tab.
        _seed_disputes(
            session,
            tenant_id=TENANT_ID,
            agencies=agencies,
            opened_by=sarah,
        )

        # Central Valley activity timeline — spread the 8 seeded
        # decision_events across a plausible Jul-8 morning/afternoon
        # sequence so the Activity + Integrity drawers don't read as
        # "everything happened at 16:57 today." Rewalks the entire
        # hash chain after the created_at rewrite so tamper-evidence
        # stays intact.
        _backdate_central_valley_activity(session)

        # Requests-For-Response — powers the case-file "Awaiting
        # response" row + the Recipient Portal "Awaiting responses"
        # watchlist. Two RFRs: one on Central Valley (paired with the
        # tier-skip signal so the reviewer sees "we asked, they haven't
        # answered") and one on the healthy R01 (a Year-2 attestation
        # ask that reads clean and simple in the demo).
        _seed_rfrs_for_demo(session, marcus=marcus)


def _seed_rfrs_for_demo(session: Session, *, marcus: User) -> None:
    """Emit two demo RFRs. Idempotent on ``rfr_number``."""
    from reasonbook.matters.service import _idempotency_id
    from reasonbook.models import Matter, MatterNode

    now = datetime.now(UTC)

    plants = [
        {
            "rfr_number": "RFR-2026-07-05-4218",
            "matter_key": {
                "program_id": "medicaid",
                "awarding_agency": "Department of Health and Human Services",
                "period_label": "FY26",
                "federal_application_ref": "SIG-TIER-SKIP-CA-MEDICAL",
            },
            "target_party_name": "Central Valley Behavioral Health Network",
            "prompt_type": "attest_flow_path",
            "prompt_body": (
                "Attest the fund-flow chain that reached this recipient. "
                "The federal ledger shows a direct disbursement without a "
                "state pass-through; the state-tier acknowledgment is "
                "required before further obligation."
            ),
            "due_days_from_now": 4,
        },
        {
            "rfr_number": "RFR-2026-07-06-8842",
            "matter_key": {
                "program_id": "nih-r01",
                "awarding_agency": "Department of Health and Human Services",
                "period_label": "FY26",
                "federal_application_ref": "R01-HL-2025-0847",
            },
            "target_party_name": "Northeast University Medical School",
            "prompt_type": "accept_scope",
            "prompt_body": (
                "Accept the FY26 continuation scope as issued. Total "
                "commitment $840K; period of performance runs through "
                "2027-08-31. Signatory must be authorized to bind."
            ),
            "due_days_from_now": 9,
        },
    ]

    for spec in plants:
        # Idempotency — skip if the RFR already lands.
        existing = (
            session.query(RequestForResponse)
            .filter_by(rfr_number=spec["rfr_number"])
            .first()
        )
        if existing is not None:
            continue

        matter_id = _idempotency_id(**spec["matter_key"])  # type: ignore[arg-type]
        matter = session.get(Matter, matter_id)
        if matter is None:
            log.info(
                "rfr seed: matter for %s not found; skipping",
                spec["rfr_number"],
            )
            continue

        federal_root = (
            session.query(MatterNode)
            .filter_by(
                matter_id=matter.id, tier="federal", removed_at=None
            )
            .first()
        )
        session.add(
            RequestForResponse(
                id=uuid.uuid4(),
                rfr_number=spec["rfr_number"],
                matter_id=matter.id,
                matter_node_id=federal_root.id if federal_root else None,
                originating_decision_id=matter.originating_decision_id,
                target_party_name=spec["target_party_name"],
                prompt_type=spec["prompt_type"],
                prompt_body=spec["prompt_body"],
                due_at=now + timedelta(days=int(spec["due_days_from_now"])),
                status="open",
                issued_by_user_id=marcus.id,
            )
        )
        log.info("seeded rfr %s (matter=%s)", spec["rfr_number"], matter.id)

    session.flush()


def make_federal_decision_factory(
    *,
    tenant_id: str,
    actor: User,
    agencies: dict[str, Agency] | None = None,
) -> Any:
    """Build a promotion-service create_decision callback that drives
    promoted federal Decisions through the manager.

    Resolves P06 (P1 violation cited in reconcile v3_0 §3): the federal
    seed used to raw-INSERT Decision rows, leaving them mutable + empty
    of decision_events. This callback walks the canonical lifecycle so
    the trail is honest:

        create_decision   → assigned (owner known at promotion)
        claim_decision    → in_progress
        finalize_decision → decided    (when outcome is set)
        record_outcome    → closed     (when outcome is set)

    When outcome is None (in-review case), the Decision stops at
    in_progress — that's the honest state, not a faked finalize.
    Returns a callable suitable for ``record_determination(create_decision=...)``.
    """
    from reasonbook.decisions.manager import (
        claim_decision,
        create_decision,
        finalize_decision,
        record_outcome,
    )

    # Per-program → agency slug mapping. Federal seed programs run out
    # of specific agencies; stamp the promoted decisions with the right
    # scope carrier so cross-agency demos (Marcus @ HHS seeing
    # NIH-OER's stuff via descendant grant) light up correctly.
    _PROGRAM_TO_AGENCY_SLUG: dict[str, str] = {
        "nih-r01": "nih-oer",
        "nih-no-cost-extension": "nih-oer",
        "treasury-disbursement": "dod",
        "cdbg": "hud",
        "grant-debarment": "hhs",
    }

    def _agency_for_program(program_id: str) -> Agency | None:
        if agencies is None:
            return None
        slug = _PROGRAM_TO_AGENCY_SLUG.get(program_id)
        return agencies.get(slug) if slug else None

    def callback(payload: dict[str, Any], s: Session) -> uuid.UUID:
        case_id = (payload.get("inputs") or {}).get("case_id", "case")
        outcome = payload.get("outcome")
        program_id = payload["program_id"]
        agency_row = _agency_for_program(program_id)

        decision = create_decision(
            tenant_id=tenant_id,
            workflow_id=program_id,
            decision_type=payload["archetype_id"],
            title=case_id,
            created_by=actor.id,
            priority="medium",
            owner_id=actor.id,
            signal_source="federal_seed_dev",
            signal_summary=case_id,
            trigger_data=payload.get("inputs"),
            agency_id=agency_row.id if agency_row is not None else None,
            session=s,
        )
        claim_decision(decision_id=decision.id, user_id=actor.id, session=s)

        if outcome is not None:
            finalize_decision(
                decision_id=decision.id,
                user_id=actor.id,
                selected_option=outcome,
                rationale=f"Seed determination · ledger outcome={outcome}",
                session=s,
            )
            record_outcome(
                decision_id=decision.id,
                user_id=actor.id,
                outcome_text=f"Ledger outcome: {outcome}",
                session=s,
            )
        return decision.id

    return callback


def _seed_federal_determinations(
    session: Session,
    *,
    tenant_id: str,
    jamie: User,
    marcus: User,
    sarah: User,
    agencies: dict[str, Agency] | None = None,
) -> None:
    """Seed a small federal determination corpus.

    Covers three archetypes:
      * NIH-R01 (competitive_award, every_case) — 3 promoted Decisions
        spanning awarded / declined / in-review.
      * NIH-NCE (modification, every_case) — 2 promoted Decisions.
      * Treasury-disbursement (payment_authorization, on_trigger) —
        5 routine determinations (ledger only) plus 1 flagged
        determination promoted on the ``fraud_flag`` trigger.

    Plus one debarment + appeal pair against the adverse_action
    archetype to demonstrate the parent_ledger_id linkage.
    """
    from reasonbook.promotion import record_determination
    from reasonbook.semantic.engine import get_engine, init_engine

    # Idempotency guard: if anything is already on the ledger for this
    # tenant we treat the corpus as seeded and skip. seed_dev gets
    # invoked on every `make seed`; we don't want N copies stacking up.
    existing = session.execute(
        text(f"SELECT count(*) FROM {schema_prefix()}determination_ledger WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    ).scalar_one()
    if int(existing) > 0:
        log.info("federal determination corpus already seeded (%d rows)", existing)
        return

    try:
        get_engine()
    except Exception:  # noqa: BLE001 — first-run init
        init_engine()

    def _decision_factory(actor: User) -> Any:
        return make_federal_decision_factory(
            tenant_id=tenant_id, actor=actor, agencies=agencies
        )

    # NIH-R01 competitive_award — 3 promoted determinations.
    for case_id, basis, outcome in [
        ("R01-2026-001", {"impact_score": 14, "percentile": 6}, "awarded"),
        ("R01-2026-002", {"impact_score": 32, "percentile": 28}, "declined"),
        ("R01-2026-003", {"impact_score": 22, "percentile": 17}, None),
    ]:
        record_determination(
            tenant_id=tenant_id,
            program_id="nih-r01",
            inputs={"case_id": case_id, "applicant_id": str(jamie.id)},
            basis_result=basis,
            actor={"kind": "user", "id": str(jamie.id), "role": "program_officer"},
            outcome=outcome,
            rule_version="nih-fy2026-cycle-2",
            session=session,
            create_decision=_decision_factory(jamie),
        )

    # NIH no-cost-extension modification — 2 promoted determinations.
    for case_id, basis, outcome in [
        ("NCE-R01-2024-1287", {"extension_months": 12, "scope_change": False}, "approved"),
        ("NCE-R01-2025-0834", {"extension_months": 18, "scope_change": False}, "approved"),
    ]:
        record_determination(
            tenant_id=tenant_id,
            program_id="nih-no-cost-extension",
            inputs={"case_id": case_id, "requester_id": str(marcus.id)},
            basis_result=basis,
            actor={"kind": "user", "id": str(marcus.id), "role": "grants_management_officer"},
            outcome=outcome,
            rule_version="45-CFR-75.308",
            session=session,
            create_decision=_decision_factory(marcus),
        )

    # Treasury disbursement payment_authorization — 5 routine (ledger only)
    # plus one flagged on fraud_flag (promoted).
    for case_id in [
        "PAY-2026-Q2-A101",
        "PAY-2026-Q2-A102",
        "PAY-2026-Q2-A103",
        "PAY-2026-Q2-A104",
        "PAY-2026-Q2-A105",
    ]:
        record_determination(
            tenant_id=tenant_id,
            program_id="treasury-disbursement",
            inputs={"case_id": case_id, "amount_usd": 250_000},
            basis_result={"all_pass": True},
            actor={"kind": "system", "id": "treasury-pre-payment-screen"},
            outcome="paid",
            session=session,
        )
    record_determination(
        tenant_id=tenant_id,
        program_id="treasury-disbursement",
        inputs={"case_id": "PAY-2026-Q2-A106-FLAGGED", "amount_usd": 1_400_000},
        basis_result={"all_pass": False, "blocked_by": ["sam_exclusion"]},
        actor={"kind": "system", "id": "treasury-pre-payment-screen"},
        outcome="held_for_review",
        promotion_trigger="fraud_flag",
        session=session,
        create_decision=_decision_factory(sarah),
    )

    # adverse_action debarment + appeal — child links to parent.
    parent = record_determination(
        tenant_id=tenant_id,
        program_id="grant-debarment",
        inputs={
            "case_id": "DBR-2026-007",
            "respondent": "Acme Research LLC",
            "basis_category": "conviction",
        },
        basis_result={"recommendation": "debar", "duration_months": 36},
        actor={"kind": "user", "id": str(sarah.id), "role": "debarring_official"},
        outcome="sustained",
        session=session,
        create_decision=_decision_factory(sarah),
    )
    record_determination(
        tenant_id=tenant_id,
        program_id="grant-debarment",
        inputs={
            "case_id": "DBR-2026-007-APPEAL",
            "respondent": "Acme Research LLC",
            "filing": "appeal",
        },
        basis_result={"recommendation": "modify", "new_duration_months": 18},
        actor={"kind": "user", "id": str(sarah.id), "role": "debarring_official"},
        outcome="modified",
        parent_ledger_id=parent.ledger_id,
        session=session,
        create_decision=_decision_factory(sarah),
    )

    log.info("seeded federal determination corpus for tenant=%s", tenant_id)


def _seed_apex_cycles_and_decisions(session: Session, *, sarah: User, marcus: User) -> None:
    """Seed two oversight cycles and a small set of apex decisions.

    One concluded cycle (last quarter, 2 decided decisions with operational
    evidence drawn from federal programs) and one active cycle (this
    quarter, 1 in-flight decision). Idempotent — keyed on cycle name.

    DB tables retain the legacy ``board_cycles`` name until the rename
    migration; user-facing copy uses "oversight cycle."
    """
    today = datetime.now(UTC).date()
    last_quarter_start = today - timedelta(days=120)
    last_quarter_end = today - timedelta(days=30)
    this_quarter_start = today - timedelta(days=20)
    this_quarter_end = today + timedelta(days=70)

    concluded = _upsert_cycle(
        session,
        name="Q1 2026 Oversight Cycle",
        cycle_type="quarterly",
        cycle_start=last_quarter_start,
        cycle_end=last_quarter_end,
        meeting_date=last_quarter_end,
        status="concluded",
        created_by=sarah,
    )
    active = _upsert_cycle(
        session,
        name="Q2 2026 Oversight Cycle",
        cycle_type="quarterly",
        cycle_start=this_quarter_start,
        cycle_end=this_quarter_end,
        meeting_date=this_quarter_end,
        status="active",
        created_by=sarah,
    )

    # Decided OIG-finding response in the concluded cycle. Agency head
    # owns this; audit committee chair endorses post-decision.
    _upsert_apex_decision(
        session,
        decision_number="APX-2026-Q1-001",
        decision_type="oig_finding_response",
        title="OIG-26-014 finding response — SNAP eligibility-verification gap",
        priority="critical",
        status="decided",
        owner=sarah,
        cycle=concluded,
        decided_days_ago=45,
        target_outcome=(
            "Eligibility-verification gap closed across all state grantees "
            "before next IG follow-up; IP rate reduction documented within 12 months."
        ),
        rationale=(
            "OIG identified inconsistent verification of household composition "
            "across three state agencies, contributing to an estimated 1.2% "
            "improper-payment exposure. Agency concurs and commits to issuing "
            "updated sub-regulatory guidance within 90 days plus quarterly "
            "state reporting through close of finding."
        ),
        decision_payload={
            "domain": "congressional_and_regulatory_posture",
            "finding_id": "OIG-26-014",
            "response_type": "concur",
            "corrective_action": (
                "Issue updated guidance to state agencies; require quarterly "
                "verification-sample reporting; agency-internal review at "
                "Q3 milestone."
            ),
            "target_close_date": (last_quarter_end + timedelta(days=270)).isoformat(),
            "primary_rationale": (
                "Improper-payment exposure estimated at 1.2% is above the "
                "agency's annual target; remediation timeline is achievable."
            ),
            "governance_path": [
                {
                    "body": "executive_leadership",
                    "date": (last_quarter_end - timedelta(days=14)).isoformat(),
                    "action": "approved",
                },
                {
                    "body": "audit_committee",
                    "date": last_quarter_end.isoformat(),
                    "action": "endorsed",
                },
            ],
        },
    )

    # Decided appropriations strategy in Q1 cycle.
    _upsert_apex_decision(
        session,
        decision_number="APX-2026-Q1-002",
        decision_type="appropriations_strategy",
        title="FY26 obligation pacing — front-load Q1/Q2 to clear backlog",
        priority="high",
        status="decided",
        owner=sarah,
        cycle=concluded,
        decided_days_ago=40,
        target_outcome=(
            "FY26 obligations 55% complete by end of Q2 to clear prior-year "
            "carryover and de-risk year-end execution."
        ),
        rationale=(
            "Prior-year carryover of $340M and Continuing Resolution risk "
            "warrant accelerated obligation pacing in the first half. "
            "Treasury and OMB notified; contingency reserve retained at 4%."
        ),
        decision_payload={
            "domain": "appropriations_and_obligations",
            "fiscal_year": 2026,
            "action_type": "obligation_pacing",
            "primary_rationale": (
                "Front-load Q1/Q2 obligations to clear carryover and reduce "
                "Continuing Resolution exposure."
            ),
        },
    )

    # Active fraud-tolerance limit change in the Q2 cycle. Marcus carries
    # cpio oversight_role — owns fraud_loss_tolerance domain.
    _upsert_apex_decision(
        session,
        decision_number="APX-2026-Q2-001",
        decision_type="fraud_tolerance_limit_change",
        title="Tighten fraud-loss tolerance on payment_authorization",
        priority="critical",
        status="open",
        owner=marcus,
        cycle=active,
        decided_days_ago=None,
        target_outcome=None,
        rationale=None,
        decision_payload={
            "domain": "fraud_loss_tolerance",
            "archetype": "payment_authorization",
            "limit_direction": "tighten",
            "primary_rationale": "",
        },
    )

    _seed_oversight_findings(session, sarah=sarah, cycle=concluded)


def _seed_oversight_findings(
    session: Session, *, sarah: User, cycle: OversightCycle
) -> None:
    """Seed a small set of realistic findings on the Q1 concluded cycle.

    Idempotent — keyed on (tenant_id, finding_number). Covers OIG, GAO,
    Single Audit, and internal-audit sources so the FindingsPane
    demonstrates the full source-facet range. Cites matter UUIDs from
    the seeded matter set when available so the cited_matter_ids array
    round-trips through the API.
    """
    from reasonbook.models import Matter

    now = datetime.now(UTC)

    # Grab a couple of seeded matters to cite. Any matters will do; we
    # want the array populated for the "Cites N matters" display.
    matter_rows = session.query(Matter).limit(3).all()
    cited = [m.id for m in matter_rows[:2]] if matter_rows else []

    rows = [
        {
            "finding_number": "F-2026-Q1-001",
            "title": "SNAP eligibility-verification gap across three state agencies",
            "observation": (
                "OIG audit sampled 1,200 SNAP determinations across "
                "three state grantees and found inconsistent "
                "verification of household composition. Estimated "
                "improper-payment exposure: 1.2% of FY26 issuance "
                "for the sampled states."
            ),
            "source": "oig",
            "severity": "critical",
            "status": "closed",
            "citations": [
                "OIG-26-014",
                "7 CFR 273.2",
                "2 CFR 200 Subpart F",
            ],
            "disposition": (
                "Agency concurred. Updated sub-regulatory guidance "
                "issued 2026-05-14; quarterly state reporting begun "
                "for FY26 Q3. Finding closed on 2026-06-01."
            ),
            "opened_days_ago": 110,
            "closed_days_ago": 30,
        },
        {
            "finding_number": "F-2026-Q1-002",
            "title": "Do Not Pay coverage gap on high-value Medicaid disbursements",
            "observation": (
                "GAO review found that 4.7% of disbursements above "
                "$500k were not screened against the Treasury Do Not "
                "Pay working system before authorisation, contrary "
                "to IPERIA obligations."
            ),
            "source": "gao",
            "severity": "high",
            "status": "closed",
            "citations": [
                "GAO-26-102",
                "IPERIA §5",
                "31 USC §3321 note",
            ],
            "disposition": (
                "CMS committed to universal DNP pre-authorisation "
                "screening. Pilot connector shipped 2026-06-20; full "
                "rollout on track for FY27 Q1. Finding closed pending "
                "next-cycle verification."
            ),
            "opened_days_ago": 95,
            "closed_days_ago": 25,
        },
        {
            "finding_number": "F-2026-Q1-003",
            "title": "Single Audit report late from two CDBG entitlement grantees",
            "observation": (
                "Two CDBG entitlement communities filed their FY25 "
                "Single Audit reports more than 9 months after the "
                "end of their audit period, in violation of 2 CFR "
                "200.512."
            ),
            "source": "single_audit",
            "severity": "medium",
            "status": "closed",
            "citations": ["2 CFR 200.512", "OMB M-24-15"],
            "disposition": (
                "Both grantees filed by 2026-05-15 under a corrective "
                "action plan; future non-compliance escalates to "
                "high-risk designation."
            ),
            "opened_days_ago": 80,
            "closed_days_ago": 20,
        },
        {
            "finding_number": "F-2026-Q1-004",
            "title": "Internal audit — matter-level authority gates bypassed on 3 CDBG decisions",
            "observation": (
                "Internal audit's random-sample review found three "
                "CDBG award decisions closed without recording the "
                "state pass-through authority acknowledgment. Not a "
                "process failure — an operator training gap."
            ),
            "source": "internal_audit",
            "severity": "low",
            "status": "under_appeal",
            "citations": ["Internal Audit 26-Q1-08"],
            "disposition": None,
            "opened_days_ago": 45,
            "closed_days_ago": None,
        },
    ]

    for r in rows:
        existing = (
            session.query(OversightFinding)
            .filter_by(tenant_id=TENANT_ID, finding_number=r["finding_number"])
            .one_or_none()
        )
        if existing is not None:
            continue
        opened_at = now - timedelta(days=int(r["opened_days_ago"]))
        closed_at = (
            now - timedelta(days=int(r["closed_days_ago"]))
            if r["closed_days_ago"] is not None
            else None
        )
        session.add(
            OversightFinding(
                tenant_id=TENANT_ID,
                cycle_id=cycle.id,
                finding_number=r["finding_number"],
                title=r["title"],
                observation=r["observation"],
                source=r["source"],
                severity=r["severity"],
                status=r["status"],
                cited_matter_ids=cited if r["source"] != "internal_audit" else cited[:1],
                citations=r["citations"],
                disposition=r["disposition"],
                opened_at=opened_at,
                opened_by=sarah.id,
                closed_at=closed_at,
                closed_by=sarah.id if closed_at is not None else None,
            )
        )
    session.flush()
    log.info("seeded %d oversight findings on cycle '%s'", len(rows), cycle.name)


def _upsert_cycle(
    session: Session,
    *,
    name: str,
    cycle_type: str,
    cycle_start: date,
    cycle_end: date,
    meeting_date: date,
    status: str,
    created_by: User,
) -> OversightCycle:
    existing = session.query(OversightCycle).filter_by(tenant_id=TENANT_ID, name=name).one_or_none()
    if existing is not None:
        return existing
    cycle = OversightCycle(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        name=name,
        cycle_type=cycle_type,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        status=status,
        meeting_date=meeting_date,
        created_by=created_by.id,
    )
    session.add(cycle)
    session.flush()
    log.info("inserted oversight cycle '%s' status=%s", name, status)
    return cycle


def _upsert_apex_decision(
    session: Session,
    *,
    decision_number: str,
    decision_type: str,
    title: str,
    priority: str,
    status: str,
    owner: User,
    cycle: OversightCycle,
    decided_days_ago: int | None,
    target_outcome: str | None,
    rationale: str | None,
    decision_payload: dict[str, Any],
) -> Decision:
    existing = (
        session.query(Decision)
        .filter_by(tenant_id=TENANT_ID, decision_number=decision_number)
        .one_or_none()
    )
    if existing is not None:
        return existing

    now = datetime.now(UTC)
    sla_deadline = datetime.combine(cycle.cycle_end, datetime.min.time(), tzinfo=UTC)
    decided_at = now - timedelta(days=decided_days_ago) if decided_days_ago is not None else None
    decision = Decision(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        decision_number=decision_number,
        workflow_id=OVERSIGHT_WORKFLOW_ID,
        decision_type=decision_type,
        title=title,
        priority=priority,
        status=status,
        sla_hours=2160,
        sla_deadline=sla_deadline,
        sla_status="on_track",
        signal_captured_at=now - timedelta(days=60),
        signal_source="oversight_cycle_planning",
        owner_id=owner.id,
        created_by=owner.id,
        assigned_at=now - timedelta(days=55),
        owner_authority_level=5 if owner.username == "sarah.mitchell" else 4,
        decided_at=decided_at,
        rationale=rationale,
        target_outcome=target_outcome,
        oversight_cycle_id=cycle.id,
        decision_payload=decision_payload,
    )
    session.add(decision)
    session.flush()
    log.info(
        "inserted apex decision %s (%s, status=%s)",
        decision_number,
        decision_type,
        status,
    )
    return decision


def _seed_alerts(session: Session, *, tenant_id: str) -> None:
    """Seed 8 fake alerts mirroring the mockup. Federal tier, idempotent."""
    from datetime import UTC, datetime, timedelta

    existing = session.execute(
        text(f"SELECT count(*) FROM {schema_prefix()}alerts WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    ).scalar_one()
    if int(existing) > 0:
        log.info("alerts corpus already seeded (%d rows)", existing)
        return

    now = datetime.now(UTC)
    # (severity, source, target_program_id, title, body, age_minutes)
    # Every alert routes to grant-debarment in this prototype — its
    # adverse_action archetype is promotes=every_case, so a promote
    # action reliably instantiates a Decision regardless of source.
    # Producer-specific routing comes when the producers are real.
    # Every row's `catalog_kind` MUST resolve against an AlertCategory id
    # declared in dp/workflows/00-signal-vocabulary/config.yaml. That
    # invariant is enforced at the end of this function so the demo
    # signal stream stays in lockstep with the catalog vocabulary.
    rows = [
        (
            "critical", "fraud_risk_screening", "treasury_dnp_match", "grant-debarment",
            "Treasury Do Not Pay match — vendor V-8841",
            "Payment authorization · $1.2M disbursement matched a Treasury Do Not Pay record. Release blocked.",
            9,
        ),
        (
            "critical", "flow_graph", "fund_diversion", "grant-debarment",
            "Fund diversion — CA / USDA pass-through",
            "Formula allocation · $4.2M passed downstream against a $3.9M federal award (+$300K unaccounted).",
            60,
        ),
        (
            "high", "identity", "ssn_multiple_claimants", "grant-debarment",
            "SSN tied to 3 claimants",
            "Eligibility determination · One verified SSN resolves to three identities across SNAP and Medicaid in two states.",
            120,
        ),
        (
            "high", "flow_graph", "phantom_subrecipient", "grant-debarment",
            "Phantom subrecipient — no downstream activity",
            "Formula allocation · Subrecipient received pass-through funds with no disbursement or vendor payment in 90 days.",
            180,
        ),
        (
            "high", "fraud_risk_screening", "leie_exclusion", "grant-debarment",
            "LEIE exclusion — provider P-7782",
            "Payment authorization · Provider appears on the HHS exclusions list (LEIE). Disbursement held.",
            360,
        ),
        (
            "medium", "fraud_risk_screening", "sam_gov_exclusion", "grant-debarment",
            "SAM.gov exclusion hit — contractor C-2241",
            "Competitive award · Awardee appears on the SAM.gov exclusions list. Flagged before authority decision.",
            300,
        ),
        (
            "medium", "flow_graph", "benefit_stacking", "grant-debarment",
            "Benefit stacking — concurrent programs",
            "Eligibility determination · Beneficiary drawing concurrent benefits across two programs beyond eligibility.",
            60 * 24,
        ),
        (
            "medium", "identity", "duplicate_claim", "grant-debarment",
            "Duplicate claim — same identity, two states",
            "Recertification · Same resolved identity filing in two states. Possible cross-state duplicate.",
            60 * 24 + 30,
        ),
    ]

    # Validate every catalog_kind against the semantic vocabulary before
    # writing rows. Fails fast if a seed row references an undeclared id.
    _assert_signal_kinds_declared([r[2] for r in rows])

    for severity, source, catalog_kind, program_id, title, body, age_minutes in rows:
        detected_at = now - timedelta(minutes=age_minutes)
        # signal_ref.kind is the AlertCategory id — resolves in the
        # Semantic Catalog. source_id preserves the human-readable
        # source label for the audit story.
        signal_ref = {
            "kind": catalog_kind,
            "source_id": title.split(" — ")[0].lower().replace(" ", "_"),
        }
        subject_entity = _fake_subject(source, title)
        from reasonbook.models import Alert

        session.add(
            Alert(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                source=source,
                signal_ref=signal_ref,
                severity=severity,
                subject_entity=subject_entity,
                title=title,
                body=body,
                target_program_id=program_id,
                detected_at=detected_at,
                current_status="new",
            )
        )
    log.info("seeded %d alerts for tenant %s", len(rows), tenant_id)


def _assert_signal_kinds_declared(kinds: list[str]) -> None:
    """Assert every seed-emitted signal kind resolves in the Semantic Catalog.

    Reads dp/workflows/00-signal-vocabulary/config.yaml via the engine
    and confirms each ``signal_ref.kind`` the seed is about to write is
    a declared AlertCategory id. If a seed row references an undeclared
    kind, the whole seed fails fast — this is the invariant that keeps
    the catalog authoritative.
    """
    from reasonbook.semantic.engine import get_engine, init_engine

    try:
        engine = get_engine()
    except Exception:  # noqa: BLE001 — engine not yet initialised
        init_engine()
        engine = get_engine()
    declared: set[str] = set()
    for wf_id in engine.workflow_ids():
        cfg = engine.get_config(wf_id)
        for a in cfg.alert_categories:
            declared.add(a.id)
    undeclared = [k for k in kinds if k not in declared]
    if undeclared:
        raise ValueError(
            "seed emits signal kinds not declared in the semantic catalog: "
            f"{sorted(set(undeclared))}. Declare them in "
            "dp/workflows/00-signal-vocabulary/config.yaml first."
        )


def _fake_subject(source: str, title: str) -> dict[str, str]:
    """Plausible subject_entity shape per source kind."""
    if source == "fraud_risk_screening":
        return {"kind": "vendor", "id": "V-8841", "display_name": "Vendor V-8841"}
    if source == "flow_graph":
        return {"kind": "participant_org", "id": "PO-USDA-CA", "display_name": "CA / USDA pass-through"}
    return {"kind": "person", "id": "redacted-ssn-hash", "display_name": "Person (PII vaulted)"}


# Deterministic UUIDs for the demo orgs so re-seeding doesn't fork ids
# and tests can refer to them by name. Georgia + Ohio derive from the
# canonical state catalog (scripts/import_usaspending.US_STATES) so the
# matter picker shows a single Georgia / Ohio row sourced from the same
# place as the rest of the 50-state list. Delta CDC stays synthetic —
# it's the demo recipient that exercises the recipient tier alongside
# the real USAspending recipients loaded by the importer.
from scripts.import_usaspending import state_org_id  # noqa: E402

_GEORGIA_ORG_ID = state_org_id("GA")
_OHIO_ORG_ID = state_org_id("OH")
_DELTA_RECIPIENT_ID = uuid.UUID("0000df00-0000-0000-0000-0000000d0001")
_NORTHEAST_UMS_ID = uuid.UUID("0000df00-0000-0000-0000-0000000d0002")


def _seed_tenancy_matter(
    session: Session,
    *,
    jamie: User,
    password_hash: str,
    agencies: dict[str, Agency],
) -> None:
    """Insert one CDBG matter + state/recipient users + per-tier sample data.

    Per TENANCY-MODEL.md §10 step 6. Idempotent — replays land in the
    matter-create idempotency check; user upserts gate on username.

    Three demo participant orgs (Georgia, Ohio, Delta CDC) get
    deterministic UUIDs so a re-seed reuses them and the per-tier demo
    users stay stable.
    """
    from decimal import Decimal

    from reasonbook.matters.service import (
        RecipientSpec,
        StakeholderSpec,
        create_matter,
    )
    from reasonbook.models import ParticipantOrg
    from reasonbook.semantic.engine import get_engine, init_engine

    # create_matter reads program defaults off the SemanticEngine.
    # Ensure it's initialised (idempotent; cheap if already loaded).
    try:
        get_engine()
    except Exception:
        init_engine()

    # 1. Participant orgs.
    # Georgia + Ohio land in participant_orgs via the canonical state
    # catalog (importer's load_states; bootstrapped in
    # _seed_real_data_matter below). This call only ensures Delta CDC —
    # the synthetic demo recipient that exercises the recipient tier
    # alongside the real USAspending recipients.
    from scripts.import_usaspending import load_states

    # Make sure the state list is in the DB before the matter references
    # Georgia / Ohio. Idempotent — re-seeds skip existing rows.
    load_states(session)

    if session.get(ParticipantOrg, _DELTA_RECIPIENT_ID) is None:
        session.add(
            ParticipantOrg(
                id=_DELTA_RECIPIENT_ID,
                kind="recipient",
                display_name="Delta CDC",
            )
        )
    session.flush()

    # 2. State and recipient users — tier-scoped so the demo exercises
    # apply_tier_scope without admin override. Three users, one per
    # participant org. Federal users (jamie/marcus/etc.) keep their
    # default federal tier.
    _upsert_user(
        session,
        username="elena.ross",
        email="elena.ross@state.example.org",
        name="Elena Ross",
        title="Georgia Program Director",
        role="member",
        password_hash=password_hash,
        tier="state",
        participant_org_id=_GEORGIA_ORG_ID,
    )
    _upsert_user(
        session,
        username="paul.tate",
        email="paul.tate@state.example.org",
        name="Paul Tate",
        title="Ohio Program Director",
        role="member",
        password_hash=password_hash,
        tier="state",
        participant_org_id=_OHIO_ORG_ID,
    )
    _upsert_user(
        session,
        username="rita.alvarez",
        email="rita.alvarez@recipient.example.org",
        name="Rita Alvarez",
        title="Delta CDC Certifying Officer",
        role="member",
        password_hash=password_hash,
        tier="recipient",
        participant_org_id=_DELTA_RECIPIENT_ID,
    )

    # 3. The CDBG matter. create_matter handles its own idempotency on
    # the (program_id, awarding_agency, period_label, federal_application_ref)
    # key — repeat seeds are no-ops.
    awarding_agency_str = "Department of Housing and Urban Development"
    hud_agency = _agency_for_awarding_agency(agencies, awarding_agency_str)
    matter = create_matter(
        program_id="cdbg",
        # Use the real agency display_name from the catalog so the
        # Register reads consistently across the synthetic + real-data
        # matters. No more bare "HUD" stub.
        awarding_agency=awarding_agency_str,
        amount_obligated=Decimal("12000000.00"),
        period_label="FY26",
        terms="Uniform Guidance 2 CFR 200",
        federal_application_ref="HUD-CDBG-2026-DEMO",
        states=[
            StakeholderSpec(participant_org_id=_GEORGIA_ORG_ID),
            StakeholderSpec(participant_org_id=_OHIO_ORG_ID),
        ],
        recipients=[
            RecipientSpec(
                parent_state_org_id=_GEORGIA_ORG_ID,
                participant_org_id=_DELTA_RECIPIENT_ID,
            ),
        ],
        actor_user_id=jamie.id,
        tenant_id=TENANT_ID,
        agency_id=hud_agency.id if hud_agency else None,
        session=session,
    )
    log.info("seeded tenancy matter %s (CDBG / FY26)", matter.id)


_REAL_DATA_BUNDLE_REF = "USASP-CDBG-2026-REAL-DEMO"


def _seed_real_data_matter(
    session: Session, *, jamie: User, agencies: dict[str, Agency]
) -> None:
    """One additional matter whose stakeholders are real USAspending entities.

    On first run, bootstraps ``agency_catalog`` + recipient
    ``participant_orgs`` from ``data/*.csv`` (the loader is idempotent;
    subsequent calls hit the short-circuit path). Then creates one CDBG
    matter whose awarding_agency is a real federal agency and whose
    recipient leaves are real USAspending entities.

    Note: the matter service requires recipients to attach to a state
    pass-through (federal → state → recipient). This matter uses
    California as its state-tier parent — distinct from the synthetic
    seed's Georgia/Ohio so tests that look up nodes by participant_org_id
    stay deterministic across the two matters.

    Skipped when the data/ directory is unavailable (e.g. CI without
    the demo fixtures) — the synthetic matter is enough on its own.
    """
    from decimal import Decimal

    from reasonbook.matters.service import RecipientSpec, StakeholderSpec, create_matter
    from reasonbook.models import AgencyCatalog, ParticipantOrg
    from scripts.import_usaspending import DATA_DIR, load_all, state_org_id

    if not DATA_DIR.exists():
        log.info("data/ not present; skipping real-data matter")
        return

    # Idempotency: if the catalog is empty, run the loader; otherwise
    # assume a prior seed already loaded it.
    catalog_count = session.query(AgencyCatalog).count()
    if catalog_count == 0:
        load_all(session)

    # Pick a real awarding agency. Prefer HUD (matches the CDBG program);
    # fall back to the first agency by display name.
    hud = (
        session.query(AgencyCatalog)
        .filter(AgencyCatalog.display_name.ilike("%housing and urban development%"))
        .first()
    )
    if hud is None:
        hud = (
            session.query(AgencyCatalog).order_by(AgencyCatalog.display_name).first()
        )
    if hud is None:
        log.info("no agencies loaded; skipping real-data matter")
        return

    # Pick the first 2 recipients (sorted by display_name) so re-seeds
    # reproduce the same matter deterministically.
    recipients = (
        session.query(ParticipantOrg)
        .filter(ParticipantOrg.kind == "recipient")
        .filter(ParticipantOrg.id != _DELTA_RECIPIENT_ID)
        .order_by(ParticipantOrg.display_name)
        .limit(2)
        .all()
    )
    if len(recipients) < 1:
        log.info("no recipients loaded; skipping real-data matter")
        return

    # create_matter is itself idempotent on the (program_id, agency,
    # period_label, federal_application_ref) tuple — re-runs return the
    # existing row without writing.
    hud_agency = _agency_for_awarding_agency(agencies, hud.display_name)
    matter = create_matter(
        program_id="cdbg",
        awarding_agency=hud.display_name,
        amount_obligated=Decimal("8500000.00"),
        period_label="FY26",
        terms="Uniform Guidance 2 CFR 200",
        federal_application_ref=_REAL_DATA_BUNDLE_REF,
        states=[StakeholderSpec(participant_org_id=state_org_id("CA"))],
        recipients=[
            RecipientSpec(
                parent_state_org_id=state_org_id("CA"),
                participant_org_id=r.id,
            )
            for r in recipients
        ],
        actor_user_id=jamie.id,
        tenant_id=TENANT_ID,
        agency_id=hud_agency.id if hud_agency else None,
        session=session,
    )
    log.info(
        "seeded real-data matter %s (agency=%s, recipients=%d)",
        matter.id,
        hud.display_name,
        len(recipients),
    )


# Healthy NIH-R01 exemplar — the "clean matter" foil to Central Valley.
# Direct-to-institution 2-tier award, zero adverse signals, all control
# points cleared. Powers the feature-tour demo's "here's what a fully-
# governed matter looks like when the playbook runs cleanly" scene.
_HEALTHY_R01_REF = "R01-HL-2025-0847"
_HEALTHY_R01_RECIPIENT = "Northeast University Medical School"


def _seed_healthy_r01_matter(
    session: Session,
    *,
    jamie: User,
    marcus: User,
    sarah: User,
    agencies: dict[str, Agency],
) -> None:
    """Seed the healthy NIH-R01 exemplar for the feature-tour demo.

    Shape:
      - HHS/NIH awarding, direct-to-institution (2-tier: NIH → university)
      - $3.2M total commitment, $840K obligated in FY26 (Year 2 of 4)
      - Zero adverse signals
      - All federal + recipient control points cleared
      - Five decision records across the lifecycle:
        1. Originating merit-reviewed award (auto by create_matter)
        2. Tier-accept from the recipient (auto by _plant_tier_accept_decisions)
        3. Year-1 startup evidence accepted (modification)
        4. Year-1 RPPR accepted (recertification)
        5. No-cost extension approved (modification)

    Idempotent — matter uses deterministic id, extras keyed on title.
    """
    from decimal import Decimal

    from reasonbook.matters.service import RecipientSpec, create_matter
    from reasonbook.models import MatterNode, ParticipantOrg
    from reasonbook.semantic.engine import get_engine, init_engine

    try:
        get_engine()
    except Exception:  # noqa: BLE001
        init_engine()

    # 1. Recipient participant_org — fictional university, deterministic id
    #    so re-seeds hit the same row.
    if session.get(ParticipantOrg, _NORTHEAST_UMS_ID) is None:
        session.add(
            ParticipantOrg(
                id=_NORTHEAST_UMS_ID,
                kind="recipient",
                display_name=_HEALTHY_R01_RECIPIENT,
                code="northeast-ums",
            )
        )
        session.flush()

    # 2. Matter — HHS/NIH awarding, direct-to-institution (no state layer).
    awarding_agency_str = "Department of Health and Human Services"
    hhs_agency = _agency_for_awarding_agency(agencies, awarding_agency_str)
    matter = create_matter(
        program_id="nih-r01",
        awarding_agency=awarding_agency_str,
        amount_obligated=Decimal("840000.00"),
        period_label="FY26",
        terms=(
            "R01 Research Project Grant — 4-year period of performance, "
            "Year 2 of 4. Direct-to-institution award; 45 CFR 75 applies. "
            "PI: Dr. Alicia Nguyen. Grant title: Molecular mechanisms of "
            "pediatric leukemia resistance. Total commitment: $3.2M."
        ),
        federal_application_ref=_HEALTHY_R01_REF,
        states=[],
        recipients=[
            RecipientSpec(
                parent_state_org_id=None,
                participant_org_id=_NORTHEAST_UMS_ID,
            ),
        ],
        actor_user_id=jamie.id,
        tenant_id=TENANT_ID,
        agency_id=hhs_agency.id if hhs_agency else None,
        session=session,
    )

    # 3. Backfill node amounts so the fund-flow graph renders edge labels.
    for n in (
        session.query(MatterNode)
        .filter_by(matter_id=matter.id, removed_at=None)
        .all()
    ):
        if n.tier == "recipient" and n.amount is None:
            n.amount = matter.amount_obligated
    session.flush()

    log.info("seeded healthy R01 matter %s (%s)", matter.id, _HEALTHY_R01_REF)

    # 4. Plant lifecycle decisions (idempotent on title).
    _plant_healthy_r01_lifecycle_decisions(
        session, matter_id=matter.id, jamie=jamie, marcus=marcus, sarah=sarah
    )

    # 5. Materialize + clear all control points (clean §5 process adherence).
    _clear_healthy_r01_control_points(session, matter_id=matter.id, actor=sarah)


def _plant_healthy_r01_lifecycle_decisions(
    session: Session,
    *,
    matter_id: uuid.UUID,
    jamie: User,
    marcus: User,
    sarah: User,
) -> None:
    """Plant 3 additional decision records on the healthy R01 matter.

    All three are advanced to 'decided' via direct field writes plus a
    'finalized' event on the ledger — the seed bypasses the authority
    gate in ``finalize_decision`` so we don't have to wire per-workflow
    action allowlists for demo data. The event chain still records the
    finalize step so §6 audit-chain counts increment correctly.

    Idempotent on decision title within the matter.
    """
    from datetime import timedelta

    from reasonbook.decisions.manager import _log_event, claim_decision, create_decision
    from reasonbook.models import Decision, Matter, MatterNode

    matter = session.get(Matter, matter_id)
    if matter is None:
        return
    federal_root = (
        session.query(MatterNode)
        .filter_by(matter_id=matter_id, tier="federal", removed_at=None)
        .first()
    )
    if federal_root is None:
        return

    # Finalize the originating award decision so the matter reads as
    # live (Year 2 of 4) rather than "award still open." Same field-
    # write pattern as the lifecycle plants below.
    if matter.originating_decision_id is not None:
        originating = session.get(Decision, matter.originating_decision_id)
        if originating is not None and originating.status != "decided":
            if originating.status == "open":
                claim_decision(
                    decision_id=originating.id, user_id=jamie.id, session=session
                )
                originating = session.get(Decision, originating.id)
            old_status = originating.status
            originating.status = "decided"
            originating.decided_at = datetime.now(UTC) - timedelta(days=550)
            originating.selected_option = "award"
            originating.rationale = (
                "Merit-reviewed award — impact score 14, percentile 6. "
                "Council-recommended for funding. Award granted per NIH "
                "R01 program guidelines; institutional assurance current."
            )
            _log_event(
                session,
                decision=originating,
                user_id=jamie.id,
                action="finalized",
                old_status=old_status,
                new_status="decided",
                comment="award",
                metadata={"seeded": True},
            )
            session.flush()

    existing_titles = {
        d.title
        for d in session.query(Decision).filter(Decision.matter_id == matter_id).all()
    }

    now = datetime.now(UTC)

    plants = [
        {
            "title": "Year-1 startup evidence accepted",
            "workflow_id": "nih-r01",
            "decision_type": "modification",
            "signal_source": "milestone.year_1_startup",
            "signal_summary": (
                "Grantee submitted institutional assurance renewal, IRB "
                "approval, and updated PI effort statement. All within "
                "Year-1 startup window."
            ),
            "selected_option": "accept",
            "rationale": (
                "Startup evidence complete and within window; no findings. "
                "Approval per 45 CFR 75.308."
            ),
            "owner": marcus,
            "days_ago": 380,
        },
        {
            "title": "Year-1 Research Performance Progress Report accepted",
            "workflow_id": "nih-r01",
            "decision_type": "recertification",
            "signal_source": "milestone.rppr_year_1",
            "signal_summary": (
                "PI Nguyen submitted the RPPR on time. Publications, "
                "trainee outcomes, and human-subjects update reviewed by "
                "the program officer."
            ),
            "selected_option": "accept",
            "rationale": (
                "RPPR complete. Progress on stated aims; publications "
                "consistent with proposal scope; no COI updates. "
                "Continuing Year 2 without conditions."
            ),
            "owner": jamie,
            "days_ago": 210,
        },
        {
            "title": "No-cost extension approved — 12 months",
            "workflow_id": "nih-no-cost-extension",
            "decision_type": "modification",
            "signal_source": "grantee_request.nce",
            "signal_summary": (
                "Grantee requested a 12-month no-cost extension to "
                "complete the final aim (single-cell resistance mapping). "
                "No scope change. No additional funds."
            ),
            "selected_option": "approve",
            "rationale": (
                "Request meets 45 CFR 75.308(d)(2). Remaining aim is in "
                "the approved scope; PI effort continues. Extension "
                "granted through end of Year 5 (2028-08-31). No additional "
                "obligation."
            ),
            "owner": marcus,
            "days_ago": 45,
        },
    ]

    for spec in plants:
        if spec["title"] in existing_titles:
            continue

        owner: User = spec["owner"]  # type: ignore[assignment]
        d = create_decision(
            tenant_id=TENANT_ID,
            workflow_id=spec["workflow_id"],  # type: ignore[arg-type]
            decision_type=spec["decision_type"],  # type: ignore[arg-type]
            title=spec["title"],  # type: ignore[arg-type]
            created_by=owner.id,
            priority="medium",
            owner_id=owner.id,
            signal_source=spec["signal_source"],  # type: ignore[arg-type]
            signal_summary=spec["signal_summary"],  # type: ignore[arg-type]
            matter_id=matter_id,
            matter_node_id=federal_root.id,
            fund_flow_path=[],
            agency_id=matter.agency_id,
            session=session,
        )
        # Advance: assigned → in_progress → decided. Bypass the authority
        # gate in finalize_decision by writing the terminal fields
        # directly; log the finalized event so the chain increments.
        claim_decision(decision_id=d.id, user_id=owner.id, session=session)
        d = session.get(Decision, d.id)  # refresh
        old_status = d.status
        decided_at = now - timedelta(days=spec["days_ago"])  # type: ignore[operator]
        d.status = "decided"
        d.decided_at = decided_at
        d.selected_option = spec["selected_option"]  # type: ignore[assignment]
        d.rationale = spec["rationale"]  # type: ignore[assignment]
        _log_event(
            session,
            decision=d,
            user_id=owner.id,
            action="finalized",
            old_status=old_status,
            new_status="decided",
            comment=spec["selected_option"],  # type: ignore[arg-type]
            metadata={"seeded": True},
        )
        session.flush()
        log.info(
            "planted healthy R01 decision %s (%s) — %s",
            d.decision_number,
            spec["decision_type"],
            spec["title"],
        )


def _clear_healthy_r01_control_points(
    session: Session, *, matter_id: uuid.UUID, actor: User
) -> None:
    """Materialize + clear every control point on the healthy R01 matter.

    Two-tier direct-to-institution matter — federal gates + recipient
    gates only. No state gates (no pass-through). All cleared: this is
    the "clean playbook" foil to Central Valley's named-gap tier-skip.

    Idempotent — only touches rows still 'pending'.
    """
    from datetime import timedelta

    from reasonbook.control_points.service import materialize_for_matter
    from reasonbook.models import ControlPoint, Matter
    from reasonbook.semantic.engine import get_engine, init_engine

    matter = session.get(Matter, matter_id)
    if matter is None:
        return

    try:
        get_engine()
    except Exception:  # noqa: BLE001
        init_engine()

    inserted = materialize_for_matter(matter_id, session=session)
    if inserted:
        log.info(
            "control-points seed: materialized %d rows on healthy R01",
            inserted,
        )

    now = datetime.now(UTC)
    federal_cleared_ago = timedelta(days=540)   # award-time diligence
    recipient_cleared_ago = timedelta(days=520)

    cps = (
        session.query(ControlPoint)
        .filter(ControlPoint.matter_id == matter_id)
        .all()
    )
    for cp in cps:
        if cp.status != "pending":
            continue
        if cp.tier == "federal":
            cp.status = "cleared"
            cp.cleared_by_user_id = actor.id
            cp.cleared_by_decision_id = matter.originating_decision_id
            cp.cleared_at = now - federal_cleared_ago
            cp.updated_at = now - federal_cleared_ago
        elif cp.tier == "recipient":
            cp.status = "cleared"
            cp.cleared_by_user_id = actor.id
            cp.cleared_by_decision_id = matter.originating_decision_id
            cp.cleared_at = now - recipient_cleared_ago
            cp.updated_at = now - recipient_cleared_ago
        # No state tier on this matter (direct-to-institution) — nothing
        # to walk at that layer.

    session.flush()
    log.info(
        "control-points seed: walked %d control points on healthy R01",
        len(cps),
    )


_TIER_SKIP_PSEUDO_STATE_DISPLAY = "— state skipped —"


def _plant_tier_skip_demo(
    session: Session,
    *,
    jamie: User,
    ref: str,
    agency: str,
    agency_short: str,
    expected_parent: str,
    recipient: str,
    amount_dollars: int,
    program_id: str,
    body: str,
    agencies: dict[str, Agency] | None = None,
) -> None:
    """Plant one synthetic tier-skip matter + linked alert.

    Mechanics:
      * Matter keyed on `ref` (federal_application_ref) — idempotent
        via create_matter's deterministic id.
      * State-tier node uses a sentinel display name — the FundFlowGraph
        renders it as a ghost "— state skipped —" so the visual reads
        "money skipped a tier" rather than a real state pass-through.
      * Alert row linked via matter_id with signal_ref.kind='tier_skip'
        and expected_parent set so the callout can name the bypassed
        agency.

    Skipped on re-runs: both the matter and the alert are looked up by
    deterministic keys before insert.
    """
    import uuid as _uuid
    from decimal import Decimal as _Decimal

    from reasonbook.matters.service import RecipientSpec, StakeholderSpec, create_matter
    from reasonbook.models import Alert, MatterNode, ParticipantOrg
    from scripts.import_matters import slugify
    from scripts.import_usaspending import NAMESPACE_DP_ENTITY as _NS

    # Recipient (the leaf that actually got the money). Upsert in
    # case the matters loader already created it.
    recip_slug = slugify(recipient)
    recip_id = _uuid.uuid5(_NS, f"recipient:{recip_slug}")
    if session.get(ParticipantOrg, recip_id) is None:
        session.add(
            ParticipantOrg(
                id=recip_id,
                kind="recipient",
                display_name=recipient,
                code=recip_slug,
            )
        )

    # Shared sentinel pseudo-state for ALL tier-skip plants — distinct
    # from the federal-direct sentinel so the UI tells them apart. One
    # row suffices regardless of how many tier-skip matters we plant.
    state_id = _uuid.uuid5(_NS, "state:_tier_skipped")
    if session.get(ParticipantOrg, state_id) is None:
        session.add(
            ParticipantOrg(
                id=state_id,
                kind="state",
                display_name=_TIER_SKIP_PSEUDO_STATE_DISPLAY,
                code="—",
            )
        )
    session.flush()

    amount = _Decimal(str(amount_dollars)).quantize(_Decimal("0.01"))
    agency_row = _agency_for_awarding_agency(agencies or {}, agency)
    matter = create_matter(
        program_id=program_id,
        awarding_agency=agency,
        amount_obligated=amount,
        period_label="FY26",
        terms=f"Synthetic tier-skip — planted for demo ({ref})",
        federal_application_ref=ref,
        states=[StakeholderSpec(participant_org_id=state_id)],
        recipients=[
            RecipientSpec(
                parent_state_org_id=state_id,
                participant_org_id=recip_id,
            ),
        ],
        actor_user_id=jamie.id,
        tenant_id=TENANT_ID,
        agency_id=agency_row.id if agency_row else None,
        session=session,
    )

    # Patch the per-node amounts so the graph renders edge labels.
    for n in (
        session.query(MatterNode)
        .filter_by(matter_id=matter.id, removed_at=None)
        .all()
    ):
        if n.tier in ("state", "recipient"):
            n.amount = amount

    existing_alert = (
        session.query(Alert)
        .filter_by(matter_id=matter.id)
        .filter(Alert.current_status.in_(("new", "reopened")))
        .first()
    )
    if existing_alert is None:
        session.add(
            Alert(
                tenant_id=TENANT_ID,
                source="flow_graph",
                signal_ref={
                    "kind": "tier_skip",
                    "skipped_tier": "state",
                    "expected_parent": expected_parent,
                    "is_synthetic": True,
                },
                severity="high",
                subject_entity={
                    "kind": "participant_org",
                    "id": str(recip_id),
                    "display_name": recipient,
                },
                matter_id=matter.id,
                title=(
                    f"Tier-skip — {agency_short} paid subrecipient directly"
                ),
                body=body,
                target_program_id="grant-debarment",
                current_status="new",
            )
        )

    session.flush()
    log.info(
        "planted tier-skip demo: matter %s + alert (recipient=%s, amount=$%s)",
        matter.id,
        recipient,
        amount,
    )


def _seed_control_points_for_central_valley(
    session: Session, *, sarah: User
) -> None:
    """Materialize control points for the Central Valley demo matter
    and walk them into a demo-quality mix.

    - Federal tier gates: cleared (federal did its diligence).
    - State tier gates: named-gaps (the state was bypassed — this IS
      the tier-skip audit story, on the record with reasons rather
      than silent skips).
    - Recipient tier: on_adverse_action cleared (LEIE screen ran at
      award time), on_closeout + on_modification remain pending (the
      matter hasn't closed and hasn't been modified).

    Idempotent — reruns leave existing statuses alone. Skips silently
    if the Central Valley matter isn't seeded (test fixture path).
    """
    import uuid as _uuid
    from datetime import timedelta

    from reasonbook.matters.service import _idempotency_id
    from reasonbook.models import ControlPoint, Matter
    from reasonbook.semantic.engine import get_engine, init_engine

    matter = session.get(
        Matter,
        _idempotency_id(
            program_id="medicaid",
            awarding_agency="Department of Health and Human Services",
            period_label="FY26",
            federal_application_ref="SIG-TIER-SKIP-CA-MEDICAL",
        ),
    )
    if matter is None:
        log.info(
            "control-points seed: Central Valley matter not present; skipping"
        )
        return

    try:
        get_engine()
    except Exception:  # noqa: BLE001
        init_engine()

    from reasonbook.control_points.service import materialize_for_matter

    inserted = materialize_for_matter(matter.id, session=session)
    if inserted:
        log.info(
            "control-points seed: materialized %d rows on Central Valley",
            inserted,
        )

    now = datetime.now(UTC)

    cps = (
        session.query(ControlPoint)
        .filter(ControlPoint.matter_id == matter.id)
        .all()
    )
    federal_cleared_ago = timedelta(days=38)
    state_gap_ago = timedelta(days=30)
    recipient_cleared_ago = timedelta(days=35)
    state_reason = (
        "State pass-through bypassed under HHS emergency Medi-Cal "
        "federal-share disbursement authority; California DHCS "
        "acknowledgment reconstructed post hoc via signed variance "
        "memo (Var-2026-04-11). Flagged for OIG review — see §3 "
        "tier-skip signal."
    )
    for cp in cps:
        # Idempotency: only touch rows still 'pending'. Reseeds don't
        # regress a clearance an operator recorded in-product.
        if cp.status != "pending":
            continue
        if cp.tier == "federal":
            cp.status = "cleared"
            cp.cleared_by_user_id = sarah.id
            cp.cleared_by_decision_id = matter.originating_decision_id
            cp.cleared_at = now - federal_cleared_ago
            cp.updated_at = now - federal_cleared_ago
        elif cp.tier == "state":
            cp.status = "skipped"
            cp.named_gap_reason = state_reason
            cp.cleared_by_user_id = sarah.id
            cp.cleared_at = now - state_gap_ago
            cp.updated_at = now - state_gap_ago
        elif cp.tier == "recipient" and cp.trigger_event == "on_adverse_action":
            cp.status = "cleared"
            cp.cleared_by_user_id = sarah.id
            cp.cleared_by_decision_id = matter.originating_decision_id
            cp.cleared_at = now - recipient_cleared_ago
            cp.updated_at = now - recipient_cleared_ago
        # Other recipient rows stay pending.

    session.flush()
    log.info(
        "control-points seed: walked %d control points on Central Valley",
        len(cps),
    )
    _ = _uuid  # keep import silenced when the model uses uuid elsewhere


# Causal priority for lifecycle actions on a single decision. Used as a
# tie-breaker when multiple events share a Postgres NOW() (transaction-
# start) timestamp — without it, ORDER BY (created_at, id) falls back to
# random uuid4, which will happily interleave a decision's own created /
# assigned / claimed events. Higher-number = later stage; equal numbers
# read as "same stage, order undefined."
#
# Kept aligned with the state machine in dp/decisions/manager.py — if a
# new lifecycle action lands there, add it here so the seed ordering
# stays honest. Non-lifecycle events (comment, attachment_*, stage_edit,
# matter_created / node_established that are appended after the
# originating create) get an intermediate slot so they sort into the
# right region without needing per-action calibration.
_LIFECYCLE_ACTION_PRIORITY: dict[str, int] = {
    "created": 0,
    "matter_created": 1,
    "node_established": 2,
    "assigned": 3,
    "claim": 4,  # legacy naming; current code writes 'claimed'
    "claimed": 4,
    "finalize": 5,
    "action": 6,
    "outcome": 7,
    "defer": 8,
    "escalate": 8,
    "attachment_added": 20,
    "attachment_removed": 21,
    "stage_edit": 22,
    "comment": 30,
}

# Stage index for the strict lifecycle-order assertion. Only the causal
# spine (created → assigned → claimed → finalize → outcome) is checked;
# side actions (comments, attachments, matter/node events) are ignored so
# they can appear at any point without tripping the guard.
_LIFECYCLE_STAGE_INDEX: dict[str, int] = {
    "created": 0,
    "assigned": 1,
    "claim": 2,
    "claimed": 2,
    "finalize": 3,
    "action": 3,
    "outcome": 4,
}


def _assert_lifecycle_order(
    session: Session, decision_ids: list[uuid.UUID]
) -> None:
    """Fail loudly if any decision records a lifecycle event out of order.

    A decision must not record ``claimed`` before ``assigned``, and must
    not record either before ``created``. Same rule for finalize/outcome.
    Walks the ledger in the same order the chain does (``created_at, id``)
    and asserts each decision's stage index is monotonically non-
    decreasing. Repeated events at the same stage are tolerated; regress
    is not.

    Note (§14.3): once ledger ordering moves onto a monotonic sequence
    number, this check should sort by that sequence instead. Both must
    agree in direction — a chain that is sequence-valid but timestamp-
    backwards is the same defect wearing a different hat.
    """
    if not decision_ids:
        return
    rows = list(
        session.execute(
            text(
                "SELECT decision_id, action, created_at, id "
                f"FROM {schema_prefix()}decision_events "
                "WHERE decision_id = ANY(:ids) "
                "  AND action IN ('created', 'assigned', 'claim', 'claimed', "
                "                 'finalize', 'action', 'outcome') "
                "ORDER BY created_at, id"
            ),
            {"ids": decision_ids},
        ).all()
    )
    max_seen: dict[uuid.UUID, int] = {}
    for row in rows:
        stage = _LIFECYCLE_STAGE_INDEX[row.action]
        prev = max_seen.get(row.decision_id, -1)
        if stage < prev:
            raise AssertionError(
                f"lifecycle order violation on decision {row.decision_id}: "
                f"event {row.action!r} at {row.created_at.isoformat()} "
                f"regresses stage {stage} after a stage {prev} event. "
                f"Required order: created → assigned → claimed → "
                f"finalize → outcome."
            )
        max_seen[row.decision_id] = max(prev, stage)


def _backdate_central_valley_activity(session: Session) -> None:
    """Backdate Central Valley's decision_events across a plausible
    Jul-8 morning → afternoon timeline, then rewalk the entire hash
    chain so tamper-evidence stays intact after the created_at rewrite.

    Without this, every seeded event lands at the same wall-clock
    second (whenever the seed runs), and the Activity + Integrity
    drawers read as fixture data. The rewalk touches every row in
    ``decision_events`` — cheap for demo-scale data (~few hundred
    events) and keeps ``verify_chain()`` green.

    Idempotent: reruns produce the same wall clock (based on the
    first CV event's date) and the same chain hashes.
    """
    from datetime import time as _time

    from reasonbook.config import get_settings
    from reasonbook.integrity.hash_chain import HASHED_FIELDS, compute_hash
    from reasonbook.matters.service import _idempotency_id
    from reasonbook.models import Matter

    # This demo-polish routine (backdating + chain rewalk) uses PostgreSQL-only
    # raw SQL (ANY(array), UUID arrays). It is cosmetic — on SQLite the seeded
    # events keep their insert-time timestamps and the ORM hook already
    # produced a valid hash chain. Skip it on SQLite.
    if not get_settings().is_postgres:
        log.info("activity-backdate: skipped on SQLite (PostgreSQL-only demo polish)")
        return

    matter = session.get(
        Matter,
        _idempotency_id(
            program_id="medicaid",
            awarding_agency="Department of Health and Human Services",
            period_label="FY26",
            federal_application_ref="SIG-TIER-SKIP-CA-MEDICAL",
        ),
    )
    if matter is None:
        log.info("activity-backdate: Central Valley matter missing; skipping")
        return

    cv_decision_ids = [
        r[0]
        for r in session.execute(
            text(
                f"SELECT id FROM {schema_prefix()}decisions WHERE matter_id = :matter_id"
            ),
            {"matter_id": matter.id},
        ).all()
    ]
    if not cv_decision_ids:
        log.info("activity-backdate: no CV decisions found; skipping")
        return

    # Anchor to the earliest existing event's date so the demo reads
    # as "today morning → today afternoon" regardless of when the seed
    # was last run. Falls back to now() if no events exist yet.
    earliest = session.execute(
        text(
            f"SELECT MIN(created_at) FROM {schema_prefix()}decision_events "
            "WHERE decision_id = ANY(:ids)"
        ),
        {"ids": cv_decision_ids},
    ).scalar()
    if earliest is None:
        log.info("activity-backdate: no CV events yet; skipping")
        return
    anchor_date = earliest.astimezone(UTC).date()

    def _at(hour: int, minute: int) -> datetime:
        return datetime.combine(anchor_date, _time(hour, minute), tzinfo=UTC)

    # Assign timestamps by (decision_role, action) pair — not by sorted
    # position — so causal correctness doesn't depend on the sort
    # producing a specific order. The chain rewalk downstream reads
    # ORDER BY created_at, id, so as long as each (decision, action)
    # lands at the right wall-clock time, the drawer's order matches
    # the causal spine.
    originating_id = matter.originating_decision_id
    tier_accept = (
        session.execute(
            text(
                f"SELECT id FROM {schema_prefix()}decisions "
                "WHERE matter_id = :matter_id AND id != :originating_id "
                "ORDER BY created_at, decision_number "
                "LIMIT 1"
            ),
            {"matter_id": matter.id, "originating_id": originating_id},
        ).scalar()
    )

    # Two update sets. `by_action`: one row per (decision, action);
    # `by_row_id`: one row per event id (needed for node_established
    # which fires multiple times per decision).
    by_action: list[tuple[uuid.UUID, str, datetime]] = []
    by_row_id: list[tuple[uuid.UUID, datetime]] = []

    # DEC-0040 (federal originating): matter set-up, morning cluster.
    if originating_id is not None:
        by_action.append((originating_id, "created", _at(9, 15)))
        by_action.append((originating_id, "matter_created", _at(9, 22)))
        # node_established fires per tier — order by row id for
        # determinism, then assign 9:24 / 9:26 / 9:30 / +2min offsets.
        node_times = [_at(9, 24), _at(9, 26), _at(9, 30)]
        node_rows = list(
            session.execute(
                text(
                    f"SELECT id FROM {schema_prefix()}decision_events "
                    "WHERE decision_id = :d AND action = 'node_established' "
                    "ORDER BY id"
                ),
                {"d": originating_id},
            ).all()
        )
        for idx, r in enumerate(node_rows):
            ts = (
                node_times[idx]
                if idx < len(node_times)
                else node_times[-1] + timedelta(minutes=(idx - 2))
            )
            by_row_id.append((r.id, ts))

    # DEC-0081 (tier-accept, recipient acceptance): midday create +
    # assign, afternoon claim. Causal order enforced by explicit map,
    # not by sort ordering.
    if tier_accept is not None:
        by_action.append((tier_accept, "created", _at(12, 47)))
        by_action.append((tier_accept, "assigned", _at(13, 3)))
        by_action.append((tier_accept, "claimed", _at(15, 14)))

    for decision_id, action, ts in by_action:
        session.execute(
            text(
                f"UPDATE {schema_prefix()}decision_events "
                "SET created_at = :ts "
                "WHERE decision_id = :d AND action = :a"
            ),
            {"ts": ts, "d": decision_id, "a": action},
        )
    for row_id, ts in by_row_id:
        session.execute(
            text(
                f"UPDATE {schema_prefix()}decision_events "
                "SET created_at = :ts WHERE id = :id"
            ),
            {"ts": ts, "id": row_id},
        )

    # Anything on Central Valley not covered by the plan (unlikely, but
    # possible if the seed grows) gets a stable timestamp after the
    # afternoon claim so the drawer stays plausible.
    tail_start = _at(15, 20)
    unscheduled = list(
        session.execute(
            text(
                f"SELECT id FROM {schema_prefix()}decision_events "
                "WHERE decision_id = ANY(:ids) "
                "  AND action != 'node_established' "
                "  AND action NOT IN ('created', 'matter_created', "
                "                     'assigned', 'claimed') "
                "ORDER BY created_at, id"
            ),
            {"ids": cv_decision_ids},
        ).all()
    )
    for idx, r in enumerate(unscheduled):
        session.execute(
            text(
                f"UPDATE {schema_prefix()}decision_events "
                "SET created_at = :ts WHERE id = :id"
            ),
            {"ts": tail_start + timedelta(minutes=idx), "id": r.id},
        )
    session.flush()

    # Fail loudly if any decision's ledger reads claim-before-assigned or
    # either-before-created. The chain would still verify — hashes are
    # over content, not causality — but the story it tells would be a
    # lie. Cheaper to detect at seed time than to catch in a demo.
    _assert_lifecycle_order(session, cv_decision_ids)

    # Rewalk the entire chain — Central Valley events moved earlier in
    # the ORDER BY, so every downstream event's prev_hash + hash needs
    # to be recomputed. Same walk as verify_chain(), but writing the
    # new hashes back instead of asserting them.
    all_rows = (
        session.execute(
            text(
                "SELECT id, decision_id, tenant_id, workflow_id, user_id, "
                "       action, old_status, new_status, comment, metadata, "
                "       created_at "
                f"FROM {schema_prefix()}decision_events "
                "ORDER BY created_at, id"
            )
        )
        .mappings()
        .all()
    )

    prev = ""
    for row in all_rows:
        row_dict = {k: row[k] for k in HASHED_FIELDS}
        new_hash = compute_hash(prev, row_dict)
        session.execute(
            text(
                f"UPDATE {schema_prefix()}decision_events SET prev_hash = :prev, "
                "hash = :h WHERE id = :id"
            ),
            {"prev": prev, "h": new_hash, "id": row["id"]},
        )
        prev = new_hash
    session.flush()
    log.info(
        "activity-backdate: rewrote %d CV events + rewalked %d chain rows",
        len(by_action) + len(by_row_id),
        len(all_rows),
    )


def _plant_identity_signal_on_central_valley(session: Session) -> None:
    """Attach a second, per-node identity signal to Central Valley.

    Per docs/architecture/fund-flow-visual-rules.md the fund-flow
    visualization now attributes red to specific elements — so a
    matter carrying BOTH a tier-skip (state-tier attribution) AND an
    identity conflict (subrecipient attribution) reads as two distinct
    problems on one graph. Central Valley is our demo of that layering.

    Idempotent on (matter_id, signal_ref.kind='ssn_multiple_claimants').
    """
    import uuid as _uuid

    from reasonbook.matters.service import _idempotency_id
    from reasonbook.models import Alert, Matter
    from scripts.import_matters import slugify
    from scripts.import_usaspending import NAMESPACE_DP_ENTITY as _NS

    matter = session.get(
        Matter,
        _idempotency_id(
            program_id="medicaid",
            awarding_agency="Department of Health and Human Services",
            period_label="FY26",
            federal_application_ref="SIG-TIER-SKIP-CA-MEDICAL",
        ),
    )
    if matter is None:
        log.info(
            "identity-signal seed: Central Valley matter not present; skipping"
        )
        return

    recip_slug = slugify("Central Valley Behavioral Health Network")
    recip_id = _uuid.uuid5(_NS, f"recipient:{recip_slug}")

    existing = (
        session.query(Alert)
        .filter(Alert.matter_id == matter.id)
        .filter(Alert.current_status.in_(("new", "reopened")))
        .all()
    )
    for a in existing:
        if (a.signal_ref or {}).get("kind") == "ssn_multiple_claimants":
            return  # already planted

    session.add(
        Alert(
            tenant_id=TENANT_ID,
            source="identity",
            signal_ref={
                "kind": "ssn_multiple_claimants",
                "source_id": "ssn_tied_to_3_claimants",
            },
            severity="high",
            subject_entity={
                "kind": "participant_org",
                "id": str(recip_id),
                "display_name": "Central Valley Behavioral Health Network",
            },
            matter_id=matter.id,
            title="SSN tied to 3 claimants",
            body=(
                "Eligibility determination · One verified SSN resolves to "
                "three identities across SNAP and Medicaid in two states."
            ),
            target_program_id="grant-debarment",
            current_status="new",
        )
    )
    session.flush()
    log.info(
        "identity-signal seed: planted SSN-multiple-claimants alert on "
        "Central Valley (subject=%s)",
        recip_id,
    )


def _plant_tier_accept_decisions(
    session: Session,
    *,
    matter_id: uuid.UUID,
    actor: User,
    tenant_id: str = TENANT_ID,
) -> None:
    """Mint per-tier 'accept' decisions for a matter's downstream nodes.

    Every consequential participant in a matter has at least one
    decision they own — for non-federal tiers, the accept/reject of
    the funds passed to them. This planter walks the matter's active
    nodes (excluding the federal root, which already has the
    originating decision) and mints one acceptance decision per node,
    bound to that node via matter_node_id.

    Idempotent on (matter_id, matter_node_id) — re-runs skip nodes
    that already have a non-originating decision.
    """
    from reasonbook.decisions.manager import claim_decision, create_decision
    from reasonbook.models import Decision, Matter, MatterNode, ParticipantOrg

    matter = session.get(Matter, matter_id)
    if matter is None:
        return

    nodes = (
        session.query(MatterNode)
        .filter_by(matter_id=matter_id, removed_at=None)
        .order_by(MatterNode.added_at.asc())
        .all()
    )
    # Skip the federal root — its originating decision already exists.
    # Skip the "— federal direct —" pseudo-state — it's a placeholder
    # for shape, not a real participant making a decision.
    # Skip the "— state skipped —" sentinel — by definition there is
    # NO decision at that tier; the absence is the evidence.
    federal_direct = "— federal direct —"
    tier_skipped = "— state skipped —"

    org_ids = {n.participant_org_id for n in nodes if n.participant_org_id}
    org_lookup: dict[uuid.UUID, ParticipantOrg] = {}
    if org_ids:
        org_lookup = {
            o.id: o
            for o in session.query(ParticipantOrg)
            .filter(ParticipantOrg.id.in_(org_ids))
            .all()
        }

    for node in nodes:
        if node.tier == "federal" and node.parent_node_id is None:
            continue
        org = (
            org_lookup.get(node.participant_org_id)
            if node.participant_org_id
            else None
        )
        if org is None:
            continue
        if org.display_name in (federal_direct, tier_skipped):
            continue

        # Idempotency: skip if this node already has a non-originating
        # decision linked.
        existing = (
            session.query(Decision)
            .filter(
                Decision.matter_id == matter_id,
                Decision.matter_node_id == node.id,
            )
            .first()
        )
        if existing is not None:
            continue

        tier_label = {
            "state": "State pass-through",
            "recipient": "Recipient",
        }.get(node.tier, node.tier.title())
        title = f"{tier_label} accept — {org.display_name}"
        summary = (
            f"{org.display_name} ({tier_label.lower()}) "
            f"accepted ${matter.amount_obligated or 0:,.0f} for "
            f"{matter.awarding_agency} {matter.program_id} {matter.period_label or ''}."
        )
        d = create_decision(
            tenant_id=tenant_id,
            workflow_id=matter.program_id,
            decision_type=matter.federal_archetype,
            title=title,
            created_by=actor.id,
            priority="medium",
            owner_id=actor.id,
            signal_source="tier_accept",
            signal_summary=summary,
            matter_id=matter_id,
            matter_node_id=node.id,
            fund_flow_path=[],
            session=session,
        )
        # Advance to in_progress so it reads as actively accepted rather
        # than 'open'. We don't finalize all of them — leaves a mix of
        # statuses on the collection, more honest to real-world pace.
        claim_decision(decision_id=d.id, user_id=actor.id, session=session)
        log.info(
            "planted tier-accept decision %s for matter %s · %s",
            d.decision_number,
            matter_id,
            org.display_name,
        )

    session.flush()


def _plant_tier_skip_extra_decisions(
    session: Session, *, matter_ref: str, actor: User
) -> None:
    """Add investigation + authority decisions to a tier-skip matter so
    its Decision-records panel shows a real *collection*.

    Looks up the matter by federal_application_ref and only plants the
    extras if they aren't already present (idempotent on title).
    Decisions are created through reasonbook.decisions.manager so they walk the
    proper lifecycle and chain into decision_events cleanly.
    """
    from reasonbook.decisions.manager import (
        claim_decision,
        create_decision,
        finalize_decision,
    )
    from reasonbook.models import Decision, Matter, MatterNode

    # Find the matter. The federal_application_ref isn't stored as a
    # column, but the deterministic uuid5 derivation lets us recompute
    # the matter id if needed — for the demo we just match on terms.
    matter = (
        session.query(Matter)
        .filter(Matter.terms.like(f"%{matter_ref}%"))
        .first()
    )
    if matter is None:
        log.info("tier-skip enrich: matter for %s not found, skipping", matter_ref)
        return

    # Attach extras to the federal-root node — they're matter-level
    # decisions about the matter, not per-recipient.
    federal_root = (
        session.query(MatterNode)
        .filter_by(matter_id=matter.id, tier="federal", removed_at=None)
        .first()
    )
    if federal_root is None:
        return

    investigation_title = "Investigation hold — tier-skip referred for governance review"
    auth_title = "Recommendation: freeze further disbursement pending OIG review"

    existing_titles = {
        d.title
        for d in session.query(Decision).filter(Decision.matter_id == matter.id).all()
    }

    if investigation_title not in existing_titles:
        d = create_decision(
            tenant_id=TENANT_ID,
            workflow_id="grant-debarment",
            decision_type="adverse_action",
            title=investigation_title,
            created_by=actor.id,
            priority="high",
            owner_id=actor.id,
            signal_source="alert.flow_graph.tier_skip",
            signal_summary=(
                "Investigation opened from tier-skip alert. Awaiting "
                "evidence collection before authority recommendation."
            ),
            matter_id=matter.id,
            matter_node_id=federal_root.id,
            fund_flow_path=[],
            session=session,
        )
        # Advance to in_progress so the status chip reads "in progress".
        claim_decision(decision_id=d.id, user_id=actor.id, session=session)
        log.info("planted tier-skip investigation decision %s", d.decision_number)

    if auth_title not in existing_titles:
        d = create_decision(
            tenant_id=TENANT_ID,
            workflow_id="grant-debarment",
            decision_type="adverse_action",
            title=auth_title,
            created_by=actor.id,
            priority="high",
            owner_id=actor.id,
            signal_source="manual",
            signal_summary=(
                "Following investigation hold, recommendation to OIG to "
                "freeze further disbursement on this matter."
            ),
            matter_id=matter.id,
            matter_node_id=federal_root.id,
            fund_flow_path=[],
            session=session,
        )
        claim_decision(decision_id=d.id, user_id=actor.id, session=session)
        finalize_decision(
            decision_id=d.id,
            user_id=actor.id,
            selected_option="freeze_disbursement",
            rationale=(
                "Tier-skip pattern + pending OIG inquiry warrant precautionary "
                "freeze. Reversible on OIG advisement."
            ),
            session=session,
        )
        log.info("planted tier-skip authority decision %s", d.decision_number)

    session.flush()


def _idempotency_id_for_central_valley() -> uuid.UUID:
    """Deterministic matter id for the Central Valley demo matter —
    used by ``_plant_register_demo_data`` to keep its tier-skip alert
    'new' across reseeds. Kept as a helper so the constants stay next
    to the tier-skip plant call in ``main`` (SIG-TIER-SKIP-CA-MEDICAL)."""
    from reasonbook.matters.service import _idempotency_id

    return _idempotency_id(
        program_id="medicaid",
        awarding_agency="Department of Health and Human Services",
        period_label="FY26",
        federal_application_ref="SIG-TIER-SKIP-CA-MEDICAL",
    )


def _idempotency_id_for_healthy_r01() -> uuid.UUID:
    """Deterministic matter id for the healthy NIH-R01 exemplar —
    used by ``_plant_planned_disbursements`` to skip closing its
    active tier-accept decision (keeps the feature-tour narration's
    'still in progress' beat honest)."""
    from reasonbook.matters.service import _idempotency_id

    return _idempotency_id(
        program_id="nih-r01",
        awarding_agency="Department of Health and Human Services",
        period_label="FY26",
        federal_application_ref=_HEALTHY_R01_REF,
    )


def _plant_register_demo_data(session: Session, *, actor: User) -> None:
    """Seed the Register tree's non-matter branches.

    Cases — promote a couple of existing tier-skip alerts so the Cases
    branch isn't empty. The promotion path creates real Decisions linked
    back to the originating Alert via AlertDisposition.resulting_decision_id.

    Decisions awaiting review — create a few bare Decisions (no
    matter_id, status='open') so the Decisions branch shows
    lifecycle items that aren't yet matter-anchored.

    Idempotent: skips alerts that already have a promote disposition, and
    skips bare-decision creation when titles already exist.
    """
    from reasonbook.alerts.service import record_disposition
    from reasonbook.decisions.manager import create_decision
    from reasonbook.models import Alert, AlertDisposition

    # Promote tier-skip alerts → cases. Central Valley is deliberately
    # excluded — it's the demo's headline tier-skip matter and needs to
    # keep its "new" alert (drives the tree pill + case-file §3 Open
    # signals block). Anything else with an open signal is fair game.
    promotable = (
        session.query(Alert)
        .filter(Alert.tenant_id == TENANT_ID)
        .filter(Alert.current_status.in_(("new", "reopened")))
        .filter(Alert.matter_id != _idempotency_id_for_central_valley())
        .all()
    )
    for alert in promotable[:2]:
        already_promoted = (
            session.query(AlertDisposition)
            .filter_by(alert_id=alert.id, action="promote")
            .first()
            is not None
        )
        if already_promoted:
            continue
        try:
            record_disposition(
                alert_id=alert.id,
                action="promote",
                rationale=(
                    "Tier-skip pattern crossed the triage threshold — "
                    "promoting to a tracked Case for OIG referral workup."
                ),
                actor=actor,
                session=session,
            )
            log.info("promoted alert %s → case", alert.id)
        except Exception as exc:  # noqa: BLE001 — log + skip on bad row
            log.warning("alert %s could not be promoted: %s", alert.id, exc)

    # Bare Decisions awaiting review — open lifecycle items not yet
    # anchored to a matter. Three exemplars covering different workflows
    # so the branch shows variety.
    bare_specs = [
        {
            "title": "Subject-identity dispute — duplicate UEI on prime award",
            "workflow_id": "grant-debarment",
            "decision_type": "adverse_action",
            "priority": "medium",
            "signal_summary": (
                "Two recipients sharing a UEI flagged by identity "
                "resolution; pending adjudication before matter formation."
            ),
        },
        {
            "title": "Watch-list match — outbound disbursement requires confirm",
            "workflow_id": "treasury-disbursement",
            "decision_type": "screening",
            "priority": "high",
            "signal_summary": (
                "Pending Treasury disbursement matched a SAM exclusion "
                "candidate; awaiting compliance officer confirm."
            ),
        },
        {
            "title": "Eligibility review — prior debarment lookback",
            "workflow_id": "nih-r01",
            "decision_type": "eligibility_review",
            "priority": "low",
            "signal_summary": (
                "Routine pre-award eligibility review prompted by a stale "
                "debarment search hit; awaiting reviewer assignment."
            ),
        },
    ]

    from reasonbook.models import Decision

    existing_titles = {
        t
        for (t,) in session.query(Decision.title)
        .filter(Decision.tenant_id == TENANT_ID)
        .filter(Decision.matter_id.is_(None))
        .all()
    }
    for spec in bare_specs:
        if spec["title"] in existing_titles:
            continue
        d = create_decision(
            tenant_id=TENANT_ID,
            workflow_id=spec["workflow_id"],
            decision_type=spec["decision_type"],
            title=spec["title"],
            created_by=actor.id,
            priority=spec["priority"],
            signal_source="manual",
            signal_summary=spec["signal_summary"],
            session=session,
        )
        log.info("planted orphan decision %s", d.decision_number)

    session.flush()


if __name__ == "__main__":
    seed()
