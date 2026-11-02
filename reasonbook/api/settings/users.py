# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""User CRUD for administrators.

The local admin invites, edits, and deactivates users in the single
Organization.
"""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from flask import Blueprint, Response, g, jsonify, request

from reasonbook.auth.decorators import require_admin
from reasonbook.auth.users import hash_password
from reasonbook.db import session_scope
from reasonbook.models import User

bp = Blueprint("settings_users", __name__)

VALID_ROLES = ("admin", "member")
VALID_STATUSES = ("active", "inactive", "locked", "pending_invite")


def _user_dict(u: User) -> dict[str, Any]:
    return {
        "id": str(u.id),
        "tenant_id": u.tenant_id,
        "username": u.username,
        "email": u.email,
        "name": u.name,
        "title": u.title,
        "role": u.role,
        "status": u.status,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "login_count": u.login_count,
        "created_at": u.created_at.isoformat(),
        "updated_at": u.updated_at.isoformat(),
    }


def _generate_invite_password() -> str:
    """16-char alphanumeric — used as the temporary password for new invites."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


@bp.get("/settings/users")
@require_admin
def list_users() -> tuple[Response, int]:
    auth = g.auth
    with session_scope() as session:
        rows = session.query(User).filter(User.tenant_id == auth.tenant).order_by(User.name).all()
        items = [_user_dict(u) for u in rows]
    return jsonify({"items": items}), 200


@bp.get("/settings/users/<user_id>")
@require_admin
def get_user(user_id: str) -> tuple[Response, int]:
    auth = g.auth
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({"error": "invalid user id"}), 400
    with session_scope() as session:
        u = session.get(User, uid)
        if u is None or u.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        return jsonify(_user_dict(u)), 200


@bp.post("/settings/users")
@require_admin
def invite_user() -> tuple[Response, int]:
    """Create a new user in the caller's tenant. Returns the user + temp password.

    The temp password is shown to the admin once at creation; the user is
    created in `pending_invite` status so the auth flow can flip them to
    `active` after a real password reset.
    """
    auth = g.auth
    body = cast(dict[str, Any], request.get_json(silent=True) or {})

    username = (body.get("username") or "").strip().lower()
    email = (body.get("email") or "").strip()
    name = (body.get("name") or "").strip()
    role = body.get("role", "member")
    title = body.get("title")

    if not username or not email or not name:
        return jsonify({"error": "username, email, name required"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": f"invalid role; must be one of {VALID_ROLES}"}), 400

    temp_password = _generate_invite_password()

    with session_scope() as session:
        existing = session.query(User).filter(User.username == username).one_or_none()
        if existing is not None:
            return jsonify({"error": "username already taken"}), 409

        user = User(
            id=uuid.uuid4(),
            tenant_id=auth.tenant,
            username=username,
            email=email,
            password_hash=hash_password(temp_password),
            name=name,
            title=title,
            role=role,
            status="pending_invite",
            invited_by=uuid.UUID(auth.sub),
        )
        session.add(user)
        session.flush()
        body_out = _user_dict(user)
        body_out["temp_password"] = temp_password

    return jsonify(body_out), 201


@bp.put("/settings/users/<user_id>")
@require_admin
def update_user(user_id: str) -> tuple[Response, int]:
    """Update name / title / role / status. Username and email are immutable
    via this endpoint — separate flows for those (audit-heavy)."""
    auth = g.auth
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({"error": "invalid user id"}), 400
    body = cast(dict[str, Any], request.get_json(silent=True) or {})

    with session_scope() as session:
        u = session.get(User, uid)
        if u is None or u.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404

        if "name" in body:
            u.name = str(body["name"]).strip()
        if "title" in body:
            u.title = body["title"] or None
        if "role" in body:
            if body["role"] not in VALID_ROLES:
                return jsonify({"error": "invalid role"}), 400
            u.role = body["role"]
        if "status" in body:
            if body["status"] not in VALID_STATUSES:
                return jsonify({"error": "invalid status"}), 400
            u.status = body["status"]

        u.updated_at = datetime.now(UTC)
        session.flush()
        return jsonify(_user_dict(u)), 200


@bp.delete("/settings/users/<user_id>")
@require_admin
def deactivate_user(user_id: str) -> tuple[Response, int]:
    """Soft-delete via status='inactive'. The row stays for audit history."""
    auth = g.auth
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        return jsonify({"error": "invalid user id"}), 400
    with session_scope() as session:
        u = session.get(User, uid)
        if u is None or u.tenant_id != auth.tenant:
            return jsonify({"error": "not found"}), 404
        if str(u.id) == auth.sub:
            return jsonify({"error": "cannot deactivate yourself"}), 400

        u.status = "inactive"
        u.updated_at = datetime.now(UTC)
        session.flush()
        return jsonify(_user_dict(u)), 200
