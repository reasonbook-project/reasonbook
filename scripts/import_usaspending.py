# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Idempotent loader for USAspending CSV pulls (data/) + canonical US states.

Reads the three entity CSVs and upserts into:

  * ``platform.agency_catalog``  — agencies (111 rows).
  * ``platform.participant_orgs`` (kind='recipient') — recipients (431 rows).

Also loads the **canonical 50 US states + DC + 5 territories** into
``participant_orgs`` (kind='state') so the matter-drawer state picker
has a real source instead of seeded placeholders. This list is a
fixed reference dataset — not from USAspending — but lives in this
module so the loader is the single chokepoint for all participant-org
seeding.

Subrecipients are deferred for v1 — without the source events they'd
be 395 unlinked rows in the recipient picker. Re-enable when P25 lands.

Determinism: UUIDs are ``uuid5(NAMESPACE_DP_ENTITY, slug)``, where the
namespace is a fixed DP-wide constant. Re-running the loader against an
already-populated table is a no-op (the ``session.get(.., uuid5_id)``
short-circuits).

Provenance: the collector's ``entity_id`` slug ends up in
``agency_catalog.slug`` (its own column) and in ``participant_orgs.code``
(the existing free-form column). The CSV's source_event_id is NOT
imported — that field is the collector's own event ledger handle; when
P25 lands, the real connector will write into DP's event log directly
rather than backfilling it from a CSV.

Usage::

    uv run python -m scripts.import_usaspending             # --all (default)
    uv run python -m scripts.import_usaspending --agencies
    uv run python -m scripts.import_usaspending --recipients

Exit codes: 0 on success, 1 on missing files or DB error.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from reasonbook.db import session_scope
from reasonbook.models import AgencyCatalog, ParticipantOrg
from reasonbook.uploads.parser import parse_csv

log = logging.getLogger(__name__)

# Fixed namespace UUID — derived from the literal string
# "reasonbook.usaspending.entity" so it's stable across machines and code
# revisions. NEVER change this; doing so would change every derived id.
NAMESPACE_DP_ENTITY = uuid.UUID("dffc8b8d-3a14-5d9f-9826-3a8b6e0c5d52")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class LoadReport:
    inserted: int
    skipped: int

    def __str__(self) -> str:
        return f"inserted={self.inserted} skipped={self.skipped}"


def _slug_of(entity_id: str, prefix: str) -> str:
    """Strip the tier prefix from the collector's entity_id."""
    if not entity_id.startswith(prefix):
        raise ValueError(f"entity_id {entity_id!r} missing prefix {prefix!r}")
    return entity_id[len(prefix) :]


def _uuid_for(slug: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE_DP_ENTITY, slug)


def _read_rows(path: Path, *, tier: str) -> list[dict[str, str]]:
    """Read + filter rows to the expected tier."""
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("rb") as f:
        rows = parse_csv(f)
    # Drop rows where tier doesn't match (defensive — the dedicated
    # *_recipients / *_agencies files are tier-pure, but the parent
    # entities.csv is mixed).
    return [r for r in rows if r.get("tier") == tier]


def load_agencies(session: Session, path: Path | None = None) -> LoadReport:
    """Upsert the agency catalog from ``data/entities_agencies.csv``."""
    path = path or DATA_DIR / "entities_agencies.csv"
    rows = _read_rows(path, tier="agency")
    inserted = 0
    skipped = 0
    for row in rows:
        slug = _slug_of(row["entity_id"], "agency:")
        row_id = _uuid_for(slug)
        if session.get(AgencyCatalog, row_id) is not None:
            skipped += 1
            continue
        session.add(
            AgencyCatalog(
                id=row_id,
                slug=slug,
                display_name=row["name"],
                source="usaspending",
            )
        )
        inserted += 1
    session.flush()
    log.info("agency_catalog: %s", LoadReport(inserted=inserted, skipped=skipped))
    return LoadReport(inserted=inserted, skipped=skipped)


def load_recipients(session: Session, path: Path | None = None) -> LoadReport:
    """Upsert recipients from ``data/entities_recipients.csv`` into
    ``participant_orgs`` as ``kind='recipient'``.

    The collector's slug lands in ``participant_orgs.code`` so the row
    keeps its provenance. UEI is preserved when present (stored in the
    same ``code`` column today — when P25 brings explicit UEI/DUNS, the
    schema can grow a dedicated column without breaking this path).
    """
    path = path or DATA_DIR / "entities_recipients.csv"
    rows = _read_rows(path, tier="recipient")
    inserted = 0
    skipped = 0
    for row in rows:
        slug = _slug_of(row["entity_id"], "recipient:")
        row_id = _uuid_for(slug)
        if session.get(ParticipantOrg, row_id) is not None:
            skipped += 1
            continue
        # Store the UEI in `code` when present (it's the most useful
        # identifier); otherwise fall back to the slug so every row has
        # a non-null provenance marker.
        code = row.get("uei") or slug
        session.add(
            ParticipantOrg(
                id=row_id,
                kind="recipient",
                display_name=row["name"],
                code=code,
                parent_org_id=None,
            )
        )
        inserted += 1
    session.flush()
    log.info("participant_orgs (recipient): %s", LoadReport(inserted=inserted, skipped=skipped))
    return LoadReport(inserted=inserted, skipped=skipped)


# Canonical US states + DC + ITAR/territories that may appear in federal
# pass-through fund flows. USPS 2-letter codes. Static reference data —
# the source IS this list (the loader is authoritative for this slice).
US_STATES: tuple[tuple[str, str], ...] = (
    ("AL", "Alabama"), ("AK", "Alaska"), ("AZ", "Arizona"), ("AR", "Arkansas"),
    ("CA", "California"), ("CO", "Colorado"), ("CT", "Connecticut"),
    ("DE", "Delaware"), ("FL", "Florida"), ("GA", "Georgia"), ("HI", "Hawaii"),
    ("ID", "Idaho"), ("IL", "Illinois"), ("IN", "Indiana"), ("IA", "Iowa"),
    ("KS", "Kansas"), ("KY", "Kentucky"), ("LA", "Louisiana"), ("ME", "Maine"),
    ("MD", "Maryland"), ("MA", "Massachusetts"), ("MI", "Michigan"),
    ("MN", "Minnesota"), ("MS", "Mississippi"), ("MO", "Missouri"),
    ("MT", "Montana"), ("NE", "Nebraska"), ("NV", "Nevada"),
    ("NH", "New Hampshire"), ("NJ", "New Jersey"), ("NM", "New Mexico"),
    ("NY", "New York"), ("NC", "North Carolina"), ("ND", "North Dakota"),
    ("OH", "Ohio"), ("OK", "Oklahoma"), ("OR", "Oregon"),
    ("PA", "Pennsylvania"), ("RI", "Rhode Island"), ("SC", "South Carolina"),
    ("SD", "South Dakota"), ("TN", "Tennessee"), ("TX", "Texas"),
    ("UT", "Utah"), ("VT", "Vermont"), ("VA", "Virginia"),
    ("WA", "Washington"), ("WV", "West Virginia"), ("WI", "Wisconsin"),
    ("WY", "Wyoming"),
    # Federal district + territories that receive federal pass-through funds.
    ("DC", "District of Columbia"), ("PR", "Puerto Rico"),
    ("VI", "U.S. Virgin Islands"), ("GU", "Guam"),
    ("MP", "Northern Mariana Islands"), ("AS", "American Samoa"),
)


def state_org_id(code: str) -> uuid.UUID:
    """Deterministic UUID for the canonical state row keyed by USPS code.

    Stable across machines and revisions — re-seeds reuse the same id.
    Callers can derive a state's participant_org_id from its USPS code
    without touching the database.
    """
    return uuid.uuid5(NAMESPACE_DP_ENTITY, f"state:{code}")


def load_states(session: Session) -> LoadReport:
    """Upsert the canonical 50 US states + DC + 5 territories into
    ``participant_orgs`` as ``kind='state'``."""
    from reasonbook.models import ParticipantOrg  # local import for symmetry

    inserted = 0
    skipped = 0
    for code, name in US_STATES:
        row_id = state_org_id(code)
        if session.get(ParticipantOrg, row_id) is not None:
            skipped += 1
            continue
        session.add(
            ParticipantOrg(
                id=row_id,
                kind="state",
                display_name=name,
                code=code,
            )
        )
        inserted += 1
    session.flush()
    log.info("participant_orgs (state): %s", LoadReport(inserted=inserted, skipped=skipped))
    return LoadReport(inserted=inserted, skipped=skipped)


def load_all(session: Session) -> tuple[LoadReport, LoadReport, LoadReport]:
    return load_agencies(session), load_states(session), load_recipients(session)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--agencies", action="store_true")
    group.add_argument("--recipients", action="store_true")
    group.add_argument("--states", action="store_true")
    group.add_argument("--all", action="store_true", default=False)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    only_agencies = args.agencies
    only_recipients = args.recipients
    only_states = args.states
    do_all = args.all or not (only_agencies or only_recipients or only_states)

    try:
        with session_scope() as s:
            if do_all or only_agencies:
                load_agencies(s)
            if do_all or only_states:
                load_states(s)
            if do_all or only_recipients:
                load_recipients(s)
    except FileNotFoundError as exc:
        print(f"missing: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
