# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Admin-only API — local administrative tools.

Gated by ``@require_admin`` — the single local admin role. Reasonbook is
single-tenant, so there is no cross-tenant support super-admin.
"""

from __future__ import annotations

import logging

from flask import Blueprint, Response, g, jsonify, request

from reasonbook.auth.decorators import require_admin
from reasonbook.auth.lockout import unlock as clear_lockout
from reasonbook.db import session_scope
from reasonbook.models import User, UserAudit

bp = Blueprint("admin", __name__)
log = logging.getLogger(__name__)


@bp.post("/admin/users/<user_id>/unlock")
@require_admin
def admin_unlock_user(user_id: str) -> tuple[Response, int]:
    """Admin override: clear lockout on a user.

    For support cases where a user can't recover via the email-unlock
    or password-reset paths (lost mailbox access, etc.). The acting admin
    is recorded in the audit row. Idempotent — calling on an unlocked
    account is a no-op.
    """
    actor = g.auth
    body = request.get_json(silent=True) or {}
    reason_note = (body.get("note") or "").strip() or None

    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            return jsonify({"error": "user not found"}), 404
        was_locked = user.locked_at is not None
        clear_lockout(
            user,
            session=s,
            reason="admin_override",
            actor_user_id=actor.sub,
        )
        if was_locked:
            s.add(
                UserAudit(
                    user_id=user.id,
                    changed_by=actor.sub,
                    action="unlocked",
                    audit_metadata={
                        "unlock_reason": "admin_override",
                        "actor_note": reason_note,
                    },
                )
            )
    return (
        jsonify(
            {
                "status": "ok",
                "was_locked": was_locked,
                "user_id": user_id,
            }
        ),
        200,
    )
