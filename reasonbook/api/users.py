# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Shared tenant-user list endpoint.

A minimal user list scoped to the caller's tenant. Distinct from
``reasonbook.api.settings.users``, which is admin-gated and exposes the rich
user-administration payload (invite, role updates, login_count, audit
metadata).

This endpoint exists because owner / assignment pickers should not be
admin-gated. The Governance Roadmap promote-modal needs it (Prompt 1);
the deferred bulk-Reassign in TODO.md Priority 23 will reuse it.

Auth: ``@require_auth`` — any authenticated user in the tenant can read
this list. Cross-tenant reads are impossible by tenant_id filter.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, Response, g, jsonify, request
from sqlalchemy import select

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.models import User

bp = Blueprint("users", __name__)


def _picker_row(user: User) -> dict[str, Any]:
    """Minimal shape for picker UIs — id, display name, title, role, status.

    Excludes email/username (PII not needed for assignment pickers) and the
    audit-metadata fields (created_at, login_count, etc.) that live on the
    heavier ``/settings/users`` admin endpoint.
    """
    return {
        "id": str(user.id),
        "name": user.name,
        "title": user.title,
        "role": user.role,
        "status": user.status,
    }


@bp.get("/users")
@require_auth
def list_users() -> tuple[Response, int]:
    """List tenant users for picker UIs.

    Query params:
      * ``status`` (optional) — filter to one status (e.g. ``active``).
        Omit to return all non-deleted users.
    """
    auth = g.auth
    status_filter = request.args.get("status")

    with session_scope() as session:
        stmt = select(User).where(User.tenant_id == auth.tenant).order_by(User.name)
        if status_filter:
            stmt = stmt.where(User.status == status_filter)
        rows = session.execute(stmt).scalars().all()
        items = [_picker_row(u) for u in rows]

    return jsonify({"items": items}), 200
