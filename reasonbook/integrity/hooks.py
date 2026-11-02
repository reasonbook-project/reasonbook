# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy hook that chains every DecisionEvent (SEC-1).

Registered at app boot (via ``reasonbook.models.__init__``). The hook fires once
per ``Session.flush()``, collects every pending ``DecisionEvent`` in
``session.new``, reads the current DB head ONCE, and chains the whole
batch sequentially. This is the single chokepoint for hash-chaining —
every existing write site (manager, oversight, upstream/dispatch,
matters/service, matters/amendment) flows through it without code
changes.

Why ``before_flush`` (not ``before_insert``): a single flush can write N
sibling events (the matter service writes `matter_created` +
per-node `node_established` in one batch). Per-row hooks each read the
DB head via SELECT, but a pending sibling within the same flush is NOT
visible to that SELECT — so every sibling would chain against the
previous flush's tail and share a ``prev_hash``. ``before_flush`` sees
the whole batch via ``session.new`` and chains them in
(created_at, id) order.

If a row arrives with ``hash`` already set (test fixtures, the
migration backfill), the hook leaves it alone. The unique index on
``hash`` catches accidental duplicates.

See ``reasonbook/integrity/hash_chain.py`` for the canonical serialization
contract (SEC-4).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from reasonbook.integrity.hash_chain import chain_head, compute_hash
from reasonbook.models import DecisionEvent

log = logging.getLogger(__name__)

_REGISTERED = False


def _row_for_hash(target: DecisionEvent) -> dict[str, Any]:
    return {
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


def _on_before_flush(session: Session, _flush_context: Any, _instances: Any) -> None:
    pending: list[DecisionEvent] = [
        obj for obj in session.new if isinstance(obj, DecisionEvent) and not obj.hash
    ]
    if not pending:
        return

    # The model has Python-side ``default=uuid.uuid4`` for id and
    # ``server_default=func.now()`` for created_at — but some call sites
    # construct DecisionEvent without an explicit id (matter service's
    # _append_event), so Python's default fires only at INSERT time
    # (AFTER the hook). The hook itself must populate any missing id +
    # created_at BEFORE hashing so the canonical row matches what the
    # DB stores and what verify reads back.
    now = datetime.now(UTC)
    for ev in pending:
        if ev.id is None:
            ev.id = uuid.uuid4()
        if ev.created_at is None:
            ev.created_at = now
    pending.sort(key=lambda e: (e.created_at, e.id))

    head = chain_head(session)
    for ev in pending:
        ev.prev_hash = head
        ev.hash = compute_hash(head, _row_for_hash(ev))
        head = ev.hash


def register_hash_chain_hook() -> None:
    """Idempotently register the before_flush listener on Session.

    Safe to call multiple times — repeated app instantiation (Flask test
    clients) and Alembic env imports don't accumulate duplicate hooks.
    """
    global _REGISTERED
    if _REGISTERED:
        return
    event.listen(Session, "before_flush", _on_before_flush)
    _REGISTERED = True
    log.debug("hash_chain hook registered on Session.before_flush")
