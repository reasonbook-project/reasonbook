# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""v1.0 requirement tests: JWT expiry, re-chain forgery, scheduler dedup,
USAspending import."""

from __future__ import annotations

import uuid

import jwt as pyjwt
import pytest
from sqlalchemy.engine import Engine

from reasonbook.auth.jwt import issue_token, verify_token
from reasonbook.db import session_scope
from reasonbook.integrity.hash_chain import compute_hash, verify_chain
from reasonbook.models import Decision, DecisionEvent


# ---------------------------------------------------------------------------
# JWT expiry
# ---------------------------------------------------------------------------


def test_jwt_verifies_when_unexpired() -> None:
    token, payload = issue_token(user_id=str(uuid.uuid4()), tenant_id="us-federal", role="admin")
    decoded = verify_token(token)
    assert decoded.sub == payload.sub
    assert decoded.role == "admin"


def test_jwt_rejected_after_expiry() -> None:
    # Issue a token that is already expired.
    token, _ = issue_token(
        user_id=str(uuid.uuid4()), tenant_id="us-federal", role="admin", ttl_seconds=-1
    )
    with pytest.raises(pyjwt.ExpiredSignatureError):
        verify_token(token)


def test_jwt_rejects_tampered_signature() -> None:
    token, _ = issue_token(user_id=str(uuid.uuid4()), tenant_id="us-federal", role="admin")
    tampered = token[:-4] + ("aaaa" if token[-4:] != "aaaa" else "bbbb")
    with pytest.raises(pyjwt.PyJWTError):
        verify_token(tampered)


# ---------------------------------------------------------------------------
# Hash-chain re-chain forgery: tamper a row AND recompute its own hash but not
# its descendants' — the first descendant mismatch must still be caught.
# ---------------------------------------------------------------------------


def test_rechain_forgery_is_detected(seeded: Engine) -> None:
    with session_scope() as s:
        assert verify_chain(s).ok  # baseline: seeded chain is valid

        events = (
            s.query(DecisionEvent)
            .order_by(DecisionEvent.created_at, DecisionEvent.id)
            .all()
        )
        assert len(events) >= 3
        # Pick a middle event so it has at least one descendant.
        idx = len(events) // 2
        target = events[idx]

        # Tamper its content AND recompute its own hash so the row is
        # internally self-consistent (a naive re-chain forgery).
        target.comment = "FORGED CONTENT"
        row = {
            "id": target.id,
            "decision_id": target.decision_id,
            "tenant_id": target.tenant_id,
            "workflow_id": target.workflow_id,
            "user_id": target.user_id,
            "action": target.action,
            "old_status": target.old_status,
            "new_status": target.new_status,
            "comment": target.comment,
            "event_metadata": target.event_metadata,
            "created_at": target.created_at,
        }
        # Bypass the before_flush chaining hook by setting a non-empty hash.
        target.hash = compute_hash(target.prev_hash, row)
        s.flush()

        result = verify_chain(s)
        # The forged row verifies against its own prev_hash, but the NEXT
        # event's prev_hash now points at the old (pre-forgery) hash, so the
        # walk breaks at the first descendant.
        assert result.ok is False
        assert result.broken_at_index is not None
        assert result.broken_at_index > idx


# ---------------------------------------------------------------------------
# Scheduler / ingestion: runs cleanly and does not create duplicate decisions
# on repeated runs within an interval.
# ---------------------------------------------------------------------------


def test_ingestion_is_idempotent_no_duplicates(seeded: Engine) -> None:
    from reasonbook.ingestion.runner import run_ingestion

    with session_scope() as s:
        before = s.query(Decision).count()

    first = run_ingestion()
    with session_scope() as s:
        after_first = s.query(Decision).count()

    second = run_ingestion()
    with session_scope() as s:
        after_second = s.query(Decision).count()

    # Running ingestion again must not create duplicate decisions: the count
    # after the second run equals the count after the first.
    assert after_second == after_first
    # The second run creates nothing new (everything is deduped or absent).
    assert second.decisions_created == 0
    assert after_first >= before


def test_scheduler_registers_single_job(monkeypatch: pytest.MonkeyPatch) -> None:
    import types

    import reasonbook.scheduler as sched

    # Force-enable the scheduler in this test context (it is disabled by
    # default under testing) and ensure exactly one job is registered.
    monkeypatch.setattr(sched, "_scheduler", None)
    fake_settings = types.SimpleNamespace(
        run_scheduler=True, testing=False, ingestion_interval_minutes=5
    )
    monkeypatch.setattr(sched, "get_settings", lambda: fake_settings)
    scheduler = sched.start_scheduler()
    try:
        assert scheduler is not None
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].id == "reasonbook-ingestion"
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        sched._scheduler = None


# ---------------------------------------------------------------------------
# USAspending CSV import
# ---------------------------------------------------------------------------


def test_usaspending_import_loads_catalog(clean_db: Engine) -> None:
    from scripts.import_usaspending import load_agencies, load_recipients
    from reasonbook.models import AgencyCatalog, ParticipantOrg

    with session_scope() as s:
        load_agencies(s)
        load_recipients(s)

    with session_scope() as s:
        agencies = s.query(AgencyCatalog).count()
        orgs = s.query(ParticipantOrg).count()

    assert agencies > 0, "USAspending agency catalog import produced no rows"
    assert orgs > 0, "USAspending recipient import produced no rows"
