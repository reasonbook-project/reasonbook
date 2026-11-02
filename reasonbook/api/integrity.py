# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SEC-1 hash-chain verification endpoints.

Allows an auditor (IG / 3PAO) to replay the
full ``decision_events`` chain from genesis and confirm tamper-evidence.
Read-only; safe to expose to monitoring as well.

Also carries the per-matter chain-query endpoint that powers the
Inspector's Integrity drawer: this matter's slice of the chain +
global verify status, ordered.

See ``reasonbook/integrity/hash_chain.py`` for the underlying chain walk and
``docs/architecture/fedRAMP/COMPLIANCE-REGISTER.md`` (SEC-1) for context.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from flask import Blueprint, Response, jsonify
from sqlalchemy import text

from reasonbook.auth.decorators import require_auth
from reasonbook.db import schema_prefix, session_scope
from reasonbook.integrity import verify_chain

bp = Blueprint("integrity", __name__)
log = logging.getLogger(__name__)


# Global chain genesis — every chain starts from the empty string, so
# the "genesis hash" surfaced in UIs is the canonical 64-zero digest.
GENESIS_HASH = "0" * 64


# Human-readable summary per event action. Extend as new actions land;
# unknown actions fall back to a title-cased rendering of the action
# string. This mapping is the drawer's copy of record — keep it here
# so the endpoint is a single UX surface.
_ACTION_SUMMARY: dict[str, str] = {
    "created": "Created",
    "assigned": "Assigned",
    "claim": "Claimed",
    "finalize": "Finalized",
    "action": "Action recorded",
    "outcome": "Outcome recorded",
    "defer": "Deferred",
    "escalate": "Escalated",
    "comment": "Comment posted",
    "attachment_added": "Attachment added",
    "attachment_removed": "Attachment removed",
    "stage_edit": "Stage edited",
    "ownership_transferred": "Ownership transferred",
    "matter_field_amended": "Matter field amended",
    # Internal event action names include "node"/"edge" — graph
    # vocabulary that's fine for the DB column but shouldn't leak into
    # user-facing copy on the inspector. Render as tier/trail language.
    "node_established": "Tier recorded",
    "matter_created": "Matter created",
}


def _serialize_chain_event(row: Any) -> dict[str, Any]:
    """Row → drawer-ready event dict.

    Keeps just what the Integrity drawer renders: timestamp, action,
    hash pointers, and the resolved actor + decision number.
    """
    action = row["action"]
    summary = _ACTION_SUMMARY.get(action, action.replace("_", " ").capitalize())
    created_at = row["created_at"]
    # Raw SQL returns a datetime on PostgreSQL but a string on SQLite.
    ts = created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
    return {
        "event_id": str(row["id"]),
        "ts": ts,
        "action": action,
        "summary": summary,
        "decision_number": row["decision_number"],
        "actor_name": row["actor_name"],
        "hash": row["hash"],
        "prev_hash": row["prev_hash"],
    }


@bp.get("/integrity/verify-chain")
@require_auth
def get_verify_chain() -> tuple[Response, int]:
    """Walk the chain; return verification status + head hash + counts.

    Auth: any authenticated user — the response is the integrity claim
    itself (ok/broken + count + head hash), not the ledger contents.
    Federal oversight users must be able to prove the audit trail is
    intact end-to-end.

    Response shape (on success or detected break) matches
    :meth:`reasonbook.integrity.VerifyResult.as_dict`:

    .. code-block:: json

        {
          "ok": true,
          "total_events": 45,
          "head_hash": "8d44…",
          "broken_at_id": null,
          "broken_at_index": null,
          "expected_hash": null,
          "actual_hash": null
        }
    """
    with session_scope() as s:
        result = verify_chain(s)
    payload = result.as_dict()
    if not result.ok:
        log.warning("hash chain verification failed: %s", payload)
    return jsonify(payload), 200


@bp.get("/integrity/matters/<uuid:matter_id>/chain")
@require_auth
def get_matter_chain(matter_id: uuid.UUID) -> tuple[Response, int]:
    """Return this matter's slice of the chain + global verify status.

    Powers the Inspector's Integrity drawer. The ``verified`` flag
    reflects a walk of the **global** chain (single-tenant, global
    chain by design — see ``hash_chain.py``); per-matter events are
    returned so the drawer can render the recent chain trail with
    ``hash ← prev_hash`` pointers.

    Response shape:

    .. code-block:: json

        {
          "matter_id": "…",
          "head_hash": "…",       // hash of this matter's most recent event
          "prev_hash": "…",       // its prev_hash pointer
          "genesis_hash": "0…0",  // canonical global genesis
          "event_count": 24,
          "verified": true,
          "events": [
            {"event_id": "…", "ts": "…", "action": "finalize",
             "summary": "Finalized", "decision_number": "DEC-0036",
             "actor_name": "Sarah Rios", "hash": "…", "prev_hash": "…"}
          ]
        }
    """
    _sp = schema_prefix()
    with session_scope() as s:
        verify_result = verify_chain(s)
        rows = (
            s.execute(
                text(
                    "SELECT e.id, e.decision_id, e.user_id, e.action, "
                    "       e.metadata, e.created_at, e.hash, e.prev_hash, "
                    "       u.name AS actor_name, "
                    "       d.decision_number AS decision_number "
                    f"FROM {_sp}decision_events e "
                    f"LEFT JOIN {_sp}users u ON u.id = e.user_id "
                    f"LEFT JOIN {_sp}decisions d ON d.id = e.decision_id "
                    "WHERE e.decision_id IN ("
                    f"  SELECT id FROM {_sp}decisions WHERE matter_id = :matter_id"
                    ") "
                    "ORDER BY e.created_at, e.id"
                ),
                {"matter_id": matter_id},
            )
            .mappings()
            .all()
        )

    events = [_serialize_chain_event(row) for row in rows]
    if events:
        head = events[-1]
        head_hash: str | None = head["hash"]
        prev_hash: str | None = head["prev_hash"]
    else:
        head_hash = None
        prev_hash = None

    return (
        jsonify(
            {
                "matter_id": str(matter_id),
                "head_hash": head_hash,
                "prev_hash": prev_hash,
                "genesis_hash": GENESIS_HASH,
                "event_count": len(events),
                "verified": verify_result.ok,
                "events": events,
            }
        ),
        200,
    )
