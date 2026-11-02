# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SEC-1 + SEC-4 — canonical serialization and SHA-256 hash chain.

The append-only ``platform.decision_events`` table carries the full
lifecycle trail. P09 makes that trail **tamper-evident**: every event
stores ``prev_hash`` and ``hash``, computed as::

    hash = sha256_hex( prev_hash || canonical_event(this_row) )

A reviewer (IG, 3PAO) can re-walk the chain from genesis and detect any
after-the-fact mutation — see :func:`verify_chain`.

Chain scope is a **single global chain** for the deployment. DP is
single-tenant by design (federal government is the only customer;
``tenant_id`` on the row is DG-era SaaS carryover, retained for the
column it provides but not used to partition the chain).

The canonical serialization (SEC-4) is JSON with sorted keys, UTC ISO
timestamps with explicit ``Z`` for naive datetimes, ``str()`` over UUIDs,
and ``ensure_ascii=False`` so non-ASCII comments don't change shape
across environments.

Concurrency: the v1 implementation reads the chain head with a plain
``SELECT … ORDER BY created_at DESC LIMIT 1`` inside the same session as
the insert. Single-writer is the de-facto guarantee today (Flask + the
ingestion job rarely contends on the same matter at the same instant).
Multi-writer hardening — either a row-level lock on the head or a
dedicated Postgres sequence — is a SEC-1 follow-up (tracked alongside
P09 closeout).

See ``ARCHITECTURE_MASTER §7.2`` for design context;
``docs/architecture/fedRAMP/COMPLIANCE-REGISTER.md`` for the
requirement → code anchor.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# The immutable identity of an event. Mutating any of these fields after
# the row is written breaks the chain — that's the point. The chain
# columns themselves (prev_hash, hash) are NOT in this list; they are
# the chain *output*, not the chain *input*.
#
# Keep this list in sync with the migration 0040 inline copy.
HASHED_FIELDS: tuple[str, ...] = (
    "id",
    "decision_id",
    "tenant_id",
    "workflow_id",
    "user_id",
    "action",
    "old_status",
    "new_status",
    "comment",
    "metadata",  # DB column name; ORM attr is `event_metadata`
    "created_at",
)


def _serialize_value(value: Any) -> Any:
    """Per-field canonicalization rules (SEC-4).

    Datetimes are normalized to UTC and rendered naive with a trailing
    ``Z``. This keeps the canonical form identical whether the value is a
    tz-aware datetime (as the insert hook holds it, and as PostgreSQL
    returns it) or a naive datetime (as SQLite returns it after a
    round-trip) — so verify_chain produces the same hash on both dialects.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat() + "Z"
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict | list):
        return value  # let json.dumps + sort_keys handle nesting
    return str(value)


def canonical_event(event: dict[str, Any]) -> bytes:
    """Deterministic byte representation of an event row (SEC-4).

    Accepts either ORM-attribute keys (``event_metadata``) or DB-column
    keys (``metadata``); the ORM attribute is normalized to ``metadata``
    before hashing so the canonical form is single-sourced.
    """
    normalized: dict[str, Any] = dict(event)
    if "event_metadata" in normalized and "metadata" not in normalized:
        normalized["metadata"] = normalized.pop("event_metadata")

    out = {key: _serialize_value(normalized.get(key)) for key in HASHED_FIELDS}
    return json.dumps(out, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )


def compute_hash(prev_hash: str, event: dict[str, Any]) -> str:
    """SHA-256 hex digest of ``prev_hash || canonical_event(event)`` (SEC-1)."""
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(canonical_event(event))
    return h.hexdigest()


def _row_for_hash(event: Any) -> dict[str, Any]:
    """Build the hashed-field dict from a DecisionEvent ORM instance.

    Reading through the ORM (rather than raw SQL) guarantees the field
    types — ``created_at`` as a datetime, ``event_metadata`` as a dict —
    match what the insert hook hashed, so verification is identical on
    SQLite and PostgreSQL.
    """
    return {
        "id": event.id,
        "decision_id": event.decision_id,
        "tenant_id": event.tenant_id,
        "workflow_id": event.workflow_id,
        "user_id": event.user_id,
        "action": event.action,
        "old_status": event.old_status,
        "new_status": event.new_status,
        "comment": event.comment,
        "event_metadata": event.event_metadata,
        "created_at": event.created_at,
    }


def chain_head(session: Session) -> str:
    """Most recent event's ``hash``, or empty string if the chain is empty.

    ``ORDER BY created_at DESC, id DESC`` breaks ties deterministically
    when two events share a microsecond timestamp.
    """
    from reasonbook.models import DecisionEvent

    event = (
        session.query(DecisionEvent)
        .order_by(DecisionEvent.created_at.desc(), DecisionEvent.id.desc())
        .first()
    )
    return event.hash if event else ""


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of :func:`verify_chain`."""

    ok: bool
    total_events: int
    head_hash: str
    broken_at_id: uuid.UUID | None = None
    broken_at_index: int | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total_events": self.total_events,
            "head_hash": self.head_hash,
            "broken_at_id": str(self.broken_at_id) if self.broken_at_id else None,
            "broken_at_index": self.broken_at_index,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
        }


def verify_chain(session: Session) -> VerifyResult:
    """Walk the chain from genesis; assert each row's stored hash matches.

    Returns a :class:`VerifyResult` carrying the head hash and total
    count on success. On failure, ``broken_at_*`` identifies the first
    row whose stored hash diverges from the recomputed one — that's the
    row where tamper-evidence trips.
    """
    from reasonbook.models import DecisionEvent

    rows = (
        session.query(DecisionEvent)
        .order_by(DecisionEvent.created_at, DecisionEvent.id)
        .all()
    )

    prev = ""
    for index, event in enumerate(rows):
        stored_prev = event.prev_hash
        stored_hash = event.hash
        expected = compute_hash(prev, _row_for_hash(event))
        if stored_prev != prev or stored_hash != expected:
            return VerifyResult(
                ok=False,
                total_events=len(rows),
                head_hash=prev,
                broken_at_id=event.id,
                broken_at_index=index,
                expected_hash=expected,
                actual_hash=stored_hash,
            )
        prev = stored_hash

    return VerifyResult(ok=True, total_events=len(rows), head_hash=prev)
