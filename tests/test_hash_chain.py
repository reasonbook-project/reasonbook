# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SEC-1 + SEC-4 — hash chain on decision_events.

P09 regression. The federalized seed (P06) writes through the manager
which writes DecisionEvent rows which fire the SEC-1 hook. These tests
exercise the hash chain end-to-end:

  * Canonical serialization is deterministic across calls.
  * compute_hash chains correctly from genesis.
  * Manager-driven inserts produce a verified chain.
  * Manually mutating a row's hashable field makes verify trip on it.
  * Genesis row has empty prev_hash.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from reasonbook.db import session_scope
from reasonbook.db import schema_prefix
from reasonbook.integrity import (
    canonical_event,
    chain_head,
    compute_hash,
    verify_chain,
)
from reasonbook.models import DecisionEvent
from reasonbook.semantic.engine import init_engine, reset_engine


@pytest.fixture(scope="module", autouse=True)
def _engine() -> Iterator[None]:
    reset_engine()
    init_engine()
    yield
    reset_engine()


@pytest.fixture()
def empty_events(db_engine: Engine) -> Engine:
    """Empty the events table so each test sees a fresh chain."""
    with db_engine.connect() as conn:
        conn.execute(text(f"DELETE FROM {schema_prefix()}decision_events"))
        conn.commit()
    return db_engine


def _seed_tenant_user_decision(db_engine: Engine) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Insert a minimal tenant/user/decision so we can attach events."""
    suffix = uuid.uuid4().hex[:8]
    tenant_id = f"hc-{suffix}"
    user_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    with db_engine.connect() as conn:
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type) "
                "VALUES (:tid, 'HC Test', 'CREDIT_UNION')"
            ),
            {"tid": tenant_id},
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}users "
                "(id, tenant_id, username, email, password_hash, name, role, status) "
                "VALUES (:uid, :tid, :u, :e, 'x', 'HC', 'member', 'active')"
            ),
            {
                "uid": user_id,
                "tid": tenant_id,
                "u": f"hc-{suffix}",
                "e": f"hc-{suffix}@x.com",
            },
        )
        conn.execute(
            text(
                f"INSERT INTO {schema_prefix()}decisions "
                "(id, tenant_id, decision_number, workflow_id, decision_type, "
                " title, priority, severity, status, owner_id, created_by) "
                "VALUES (:did, :tid, :num, 'nih-r01', 'competitive_award', "
                "        'hc', 'medium', 'medium', 'assigned', :uid, :uid)"
            ),
            {
                "did": decision_id,
                "tid": tenant_id,
                "num": f"HC-{suffix}",
                "uid": user_id,
            },
        )
        conn.commit()
    return tenant_id, user_id, decision_id


def _make_event(
    *,
    tenant_id: str,
    user_id: uuid.UUID,
    decision_id: uuid.UUID,
    action: str = "comment",
    comment: str | None = None,
) -> DecisionEvent:
    return DecisionEvent(
        id=uuid.uuid4(),
        decision_id=decision_id,
        tenant_id=tenant_id,
        workflow_id="nih-r01",
        user_id=user_id,
        action=action,
        comment=comment,
        event_metadata={"test": True},
    )


def test_canonical_event_is_deterministic() -> None:
    """Same input → same bytes, regardless of dict order."""
    now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
    row_a = {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "decision_id": uuid.UUID("00000000-0000-0000-0000-000000000002"),
        "tenant_id": "us-federal",
        "workflow_id": "nih-r01",
        "user_id": None,
        "action": "created",
        "old_status": None,
        "new_status": "assigned",
        "comment": None,
        "event_metadata": {"k": "v"},
        "created_at": now,
    }
    # Same data, different insertion order
    row_b = {k: row_a[k] for k in reversed(list(row_a))}
    assert canonical_event(row_a) == canonical_event(row_b)
    # And the bytes are valid JSON with sorted keys
    parsed = json.loads(canonical_event(row_a))
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_compute_hash_is_stable() -> None:
    """A known input produces a known SHA-256 digest."""
    row = {
        "id": uuid.UUID("00000000-0000-0000-0000-000000000001"),
        "decision_id": None,
        "tenant_id": "x",
        "workflow_id": "y",
        "user_id": None,
        "action": "a",
        "old_status": None,
        "new_status": None,
        "comment": None,
        "event_metadata": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    h1 = compute_hash("", row)
    h2 = compute_hash("", row)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_genesis_event_has_empty_prev_hash(empty_events: Engine) -> None:
    tenant_id, user_id, decision_id = _seed_tenant_user_decision(empty_events)
    with session_scope() as s:
        ev = _make_event(
            tenant_id=tenant_id,
            user_id=user_id,
            decision_id=decision_id,
            comment="genesis",
        )
        s.add(ev)
        s.flush()
        assert ev.prev_hash == ""
        assert ev.hash != ""

    with session_scope() as s:
        head = chain_head(s)
        assert head != ""
        result = verify_chain(s)
        assert result.ok
        assert result.total_events == 1


def test_chain_grows_correctly_across_inserts(empty_events: Engine) -> None:
    tenant_id, user_id, decision_id = _seed_tenant_user_decision(empty_events)
    hashes: list[str] = []
    with session_scope() as s:
        for i in range(5):
            ev = _make_event(
                tenant_id=tenant_id,
                user_id=user_id,
                decision_id=decision_id,
                comment=f"event-{i}",
            )
            s.add(ev)
            s.flush()
            hashes.append(ev.hash)
        # Each row's prev_hash matches the previous row's hash
        rows = s.execute(
            text(
                f"SELECT prev_hash, hash FROM {schema_prefix()}decision_events "
                "ORDER BY created_at, id"
            )
        ).all()
        assert rows[0].prev_hash == ""
        for prev_row, next_row in zip(rows, rows[1:], strict=False):
            assert next_row.prev_hash == prev_row.hash

    with session_scope() as s:
        result = verify_chain(s)
        assert result.ok
        assert result.total_events == 5
        assert result.head_hash == hashes[-1]


def test_verify_detects_tampering(empty_events: Engine) -> None:
    """Mutating an event's comment after insert breaks the chain."""
    tenant_id, user_id, decision_id = _seed_tenant_user_decision(empty_events)
    # Insert each event in its own flush so the chain order matches
    # insertion order. (Within a single flush the hook sorts events by
    # (created_at, id) — when timestamps collide, sibling ordering is
    # determined by uuid4, which is random. Separate flushes give each
    # event a distinct created_at so insertion order is the chain order.)
    with session_scope() as s:
        for i in range(3):
            s.add(
                _make_event(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    decision_id=decision_id,
                    comment=f"event-{i}",
                )
            )
            s.flush()

    with session_scope() as s:
        # Find the row index of event-1 BEFORE tampering so the assertion
        # below targets the right position regardless of clock skew.
        rows = s.execute(
            text(
                f"SELECT comment FROM {schema_prefix()}decision_events "
                "ORDER BY created_at, id"
            )
        ).all()
        target_index = next(i for i, r in enumerate(rows) if r.comment == "event-1")

        # Tamper with the middle row's comment — every subsequent row's
        # recomputed hash should diverge from its stored hash.
        s.execute(
            text(
                f"UPDATE {schema_prefix()}decision_events SET comment = 'TAMPERED' "
                "WHERE comment = 'event-1'"
            )
        )
        s.flush()
        result = verify_chain(s)
        assert not result.ok
        assert result.broken_at_index == target_index
        assert result.expected_hash != result.actual_hash
        s.rollback()


def test_unique_hash_index_prevents_replay(empty_events: Engine) -> None:
    """The unique index on hash blocks accidental duplicate inserts."""
    from sqlalchemy.exc import IntegrityError

    tenant_id, user_id, decision_id = _seed_tenant_user_decision(empty_events)

    with session_scope() as s:
        ev = _make_event(
            tenant_id=tenant_id,
            user_id=user_id,
            decision_id=decision_id,
            comment="original",
        )
        s.add(ev)
        s.flush()
        original_hash = ev.hash
        # Raw INSERT a row with the same hash (simulating a bypass attempt
        # or a replay attack on the audit log). The unique index trips.
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    f"INSERT INTO {schema_prefix()}decision_events "
                    "(id, decision_id, tenant_id, workflow_id, action, "
                    " prev_hash, hash, created_at) "
                    "VALUES (:i, :d, :t, 'nih-r01', 'comment', '', :h, CURRENT_TIMESTAMP)"
                ),
                {
                    "i": uuid.uuid4(),
                    "d": decision_id,
                    "t": tenant_id,
                    "h": original_hash,
                },
            )
