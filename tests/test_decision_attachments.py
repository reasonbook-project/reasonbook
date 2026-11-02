# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Phase 7.5 Gate 2 — schema additions for attachments and comment convention.

Covers the v1.2 amendment §3 changes:

- Migration 0015 creates `{schema_prefix()}decision_attachments` with the expected
  columns, types, foreign keys, and indexes.
- Migration 0015 rolls back cleanly.
- The `DecisionAttachment` model round-trips through SQLAlchemy.
- Soft-delete via `superseded_at` keeps the row and is filterable.
- Comment events using the `action='comment'` convention round-trip on
  the existing `decision_events` table without DDL change.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from reasonbook.db import session_scope
from reasonbook.config import get_settings
from reasonbook.db import schema_prefix
from reasonbook.models import DecisionAttachment, DecisionEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        os.environ.get("DATABASE_URL", "postgresql+psycopg://dp:dp@localhost:5443/dp"),
    )
    return cfg


def _seed_tenant_user_decision(engine: Engine) -> tuple[str, uuid.UUID, uuid.UUID]:
    """Insert a minimal tenant + user + decision so attachments can FK to them.

    Returns ``(tenant_id, user_id, decision_id)``.
    """
    tenant_id = "att-test"
    user_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    with session_scope() as conn:
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}tenants (tenant_id, name, org_type)
                VALUES (:tid, 'Attachment Test CU', 'CREDIT_UNION')
            """),
            {"tid": tenant_id},
        )
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}users
                  (id, tenant_id, username, email, password_hash, name, role, status)
                VALUES (:uid, :tid, 'attu', 'a@x.com', 'x', 'Attu', 'member', 'active')
            """),
            {"uid": user_id, "tid": tenant_id},
        )
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}decisions
                  (id, tenant_id, decision_number, workflow_id, decision_type,
                   title, priority, status)
                VALUES
                  (:did, :tid, 'DG-2026-04-9001', '01-regulatory-compliance', 'bsa_aml_alert',
                   'Attachment fixture decision', 'medium', 'open')
            """),
            {"did": decision_id, "tid": tenant_id},
        )
    return tenant_id, user_id, decision_id


# ---------------------------------------------------------------------------
# Migration up — table shape, columns, FKs, indexes
# ---------------------------------------------------------------------------


def test_decision_attachments_table_exists(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    tables = set(inspector.get_table_names(schema=get_settings().db_schema))
    assert "decision_attachments" in tables


def test_decision_attachments_columns_and_types(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    cols = {c["name"]: c for c in inspector.get_columns("decision_attachments", schema=get_settings().db_schema)}

    expected = {
        "id",
        "decision_id",
        "stage",
        "filename",
        "content_type",
        "size_bytes",
        "storage_uri",
        "storage_backend",
        "uploaded_by",
        "uploaded_at",
        "description",
        "superseded_at",
    }
    missing = expected - cols.keys()
    assert not missing, f"missing columns on decision_attachments: {missing}"

    # Nullability — only `description` and `superseded_at` are nullable per §3.1.
    nullable = {name for name, info in cols.items() if info["nullable"]}
    assert nullable == {"description", "superseded_at"}, nullable


def test_decision_attachments_foreign_keys(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    fks = inspector.get_foreign_keys("decision_attachments", schema=get_settings().db_schema)
    fk_targets = {
        (fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0])
        for fk in fks
    }
    assert ("decision_id", "decisions", "id") in fk_targets
    assert ("uploaded_by", "users", "id") in fk_targets


def test_decision_attachments_indexes(clean_db: Engine) -> None:
    inspector = inspect(clean_db)
    idx_cols = {
        idx["name"]: tuple(idx["column_names"])
        for idx in inspector.get_indexes("decision_attachments", schema=get_settings().db_schema)
    }
    assert idx_cols.get("idx_decision_attachments_decision_stage") == (
        "decision_id",
        "stage",
    )
    assert idx_cols.get("idx_decision_attachments_decision_active") == (
        "decision_id",
        "superseded_at",
    )


# ---------------------------------------------------------------------------
# Migration down — clean rollback of just 0015
# ---------------------------------------------------------------------------


def test_decision_attachments_downgrade_drops_table(clean_db: Engine) -> None:
    """Roll 0015 → 0014 and confirm the table and indexes are gone, then re-upgrade."""
    cfg = _alembic_config()
    command.downgrade(cfg, "0014")

    inspector = inspect(clean_db)
    tables = set(inspector.get_table_names(schema=get_settings().db_schema))
    assert "decision_attachments" not in tables

    # Restore for subsequent tests in the session.
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Model round-trip — insert, query, soft-delete
# ---------------------------------------------------------------------------


def test_decision_attachment_round_trip(clean_db: Engine) -> None:
    _, user_id, decision_id = _seed_tenant_user_decision(clean_db)

    att_id = uuid.uuid4()
    with session_scope() as s:
        s.add(
            DecisionAttachment(
                id=att_id,
                decision_id=decision_id,
                stage="signal",
                filename="referral.pdf",
                content_type="application/pdf",
                size_bytes=12345,
                storage_uri="local://tmp/referral.pdf",
                storage_backend="local",
                uploaded_by=user_id,
                description="initial referral packet",
            )
        )

    with session_scope() as s:
        row = s.get(DecisionAttachment, att_id)
        assert row is not None
        assert row.decision_id == decision_id
        assert row.uploaded_by == user_id
        assert row.stage == "signal"
        assert row.filename == "referral.pdf"
        assert row.content_type == "application/pdf"
        assert row.size_bytes == 12345
        assert row.storage_uri == "local://tmp/referral.pdf"
        assert row.storage_backend == "local"
        assert row.description == "initial referral packet"
        assert row.superseded_at is None
        assert row.uploaded_at is not None  # server_default fills it


def test_decision_attachment_soft_delete_filters_active(clean_db: Engine) -> None:
    _, user_id, decision_id = _seed_tenant_user_decision(clean_db)

    active_id = uuid.uuid4()
    superseded_id = uuid.uuid4()
    with session_scope() as s:
        s.add(
            DecisionAttachment(
                id=active_id,
                decision_id=decision_id,
                stage="decision",
                filename="rationale-v2.pdf",
                content_type="application/pdf",
                size_bytes=1000,
                storage_uri="local://tmp/rationale-v2.pdf",
                storage_backend="local",
                uploaded_by=user_id,
            )
        )
        s.add(
            DecisionAttachment(
                id=superseded_id,
                decision_id=decision_id,
                stage="decision",
                filename="rationale-v1.pdf",
                content_type="application/pdf",
                size_bytes=900,
                storage_uri="local://tmp/rationale-v1.pdf",
                storage_backend="local",
                uploaded_by=user_id,
                superseded_at=datetime.now(UTC),
            )
        )

    with session_scope() as s:
        active = (
            s.query(DecisionAttachment)
            .filter(
                DecisionAttachment.decision_id == decision_id,
                DecisionAttachment.superseded_at.is_(None),
            )
            .all()
        )
        assert len(active) == 1
        assert active[0].id == active_id

        # Both rows still exist — append-only.
        all_rows = (
            s.query(DecisionAttachment).filter(DecisionAttachment.decision_id == decision_id).all()
        )
        assert len(all_rows) == 2


def test_decision_attachment_cascades_on_decision_delete(clean_db: Engine) -> None:
    _, user_id, decision_id = _seed_tenant_user_decision(clean_db)

    att_id = uuid.uuid4()
    with session_scope() as s:
        s.add(
            DecisionAttachment(
                id=att_id,
                decision_id=decision_id,
                stage="signal",
                filename="x.pdf",
                content_type="application/pdf",
                size_bytes=1,
                storage_uri="local://tmp/x.pdf",
                storage_backend="local",
                uploaded_by=user_id,
            )
        )

    # Deleting the parent decision should cascade-drop the attachment row.
    with clean_db.begin() as conn:
        conn.execute(
            text(f"DELETE FROM {schema_prefix()}decisions WHERE id = :did"),
            {"did": decision_id},
        )

    with session_scope() as s:
        assert s.get(DecisionAttachment, att_id) is None


# ---------------------------------------------------------------------------
# Comment convention — round-trip on existing decision_events table
# ---------------------------------------------------------------------------


def test_comment_event_convention_round_trip(clean_db: Engine) -> None:
    """Per amendment §3.2: action='comment', body in `comment`, `{stage_context, mentions}` in event_metadata.

    Validates the convention works against the existing schema with no DDL.
    No CHECK or enum constraints existence to test — there's nothing to
    constrain — so this is a positive round-trip only.
    """
    tenant_id, user_id, decision_id = _seed_tenant_user_decision(clean_db)

    other_user = uuid.uuid4()
    with clean_db.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO {schema_prefix()}users
                  (id, tenant_id, username, email, password_hash, name, role, status)
                VALUES (:uid, :tid, 'mention-target', 'm@x.com', 'x',
                        'Mention Target', 'member', 'active')
            """),
            {"uid": other_user, "tid": tenant_id},
        )

    event_id = uuid.uuid4()
    with session_scope() as s:
        s.add(
            DecisionEvent(
                id=event_id,
                decision_id=decision_id,
                tenant_id=tenant_id,
                workflow_id="01-regulatory-compliance",
                user_id=user_id,
                action="comment",
                old_status=None,
                new_status=None,
                comment="Worth a closer look — see @mention",
                event_metadata={
                    "stage_context": "general",
                    "mentions": [str(other_user)],
                },
            )
        )

    with session_scope() as s:
        row = s.get(DecisionEvent, event_id)
        assert row is not None
        assert row.action == "comment"
        assert row.comment == "Worth a closer look — see @mention"
        assert row.event_metadata is not None
        assert row.event_metadata["stage_context"] == "general"
        assert row.event_metadata["mentions"] == [str(other_user)]
        assert row.user_id == user_id


def test_comment_event_with_stage_context_per_anatomy_stage(clean_db: Engine) -> None:
    """The five `stage_context` values from §3.2 all round-trip without constraint."""
    tenant_id, user_id, decision_id = _seed_tenant_user_decision(clean_db)

    contexts = ["signal", "decision", "action", "outcome", "general"]
    event_ids: list[uuid.UUID] = []
    with session_scope() as s:
        for ctx in contexts:
            eid = uuid.uuid4()
            event_ids.append(eid)
            s.add(
                DecisionEvent(
                    id=eid,
                    decision_id=decision_id,
                    tenant_id=tenant_id,
                    workflow_id="01-regulatory-compliance",
                    user_id=user_id,
                    action="comment",
                    old_status=None,
                    new_status=None,
                    comment=f"comment in {ctx} context",
                    event_metadata={"stage_context": ctx, "mentions": []},
                )
            )

    with session_scope() as s:
        rows = (
            s.query(DecisionEvent)
            .filter(DecisionEvent.id.in_(event_ids))
            .order_by(DecisionEvent.created_at.asc())
            .all()
        )
        seen_contexts: set[str] = set()
        for r in rows:
            assert r.event_metadata is not None
            seen_contexts.add(r.event_metadata["stage_context"])
        assert seen_contexts == set(contexts)
        assert all(r.action == "comment" for r in rows)
