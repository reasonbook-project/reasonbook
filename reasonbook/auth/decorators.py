# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Auth decorators.

Read the session JWT from the ``reasonbook_session`` HTTP-only cookie,
verify it, and attach the decoded payload to ``flask.g.auth``. Routes can
then read ``g.auth.sub`` / ``g.auth.tenant`` / ``g.auth.role`` etc.

Tokens are short-lived (30 min by default). There is no server-side
revocation list in v1.0 — logout clears the client cookie only (see
README, Known limitations).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import jwt as pyjwt
from flask import g, jsonify, request

from reasonbook.auth.jwt import TokenPayload, verify_token

SESSION_COOKIE = "reasonbook_session"


def _unauthorized(message: str = "unauthorized") -> tuple[Any, int]:
    return jsonify({"error": message}), 401


def _forbidden(message: str = "forbidden", **extra: Any) -> tuple[Any, int]:
    body: dict[str, Any] = {"error": message}
    body.update(extra)
    return jsonify(body), 403


def _read_token() -> TokenPayload | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        return verify_token(token)
    except pyjwt.PyJWTError:
        return None


def require_auth(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Require a valid session JWT cookie. Sets ``g.auth`` on success."""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        payload = _read_token()
        if payload is None:
            return _unauthorized()
        g.auth = payload
        return fn(*args, **kwargs)

    return wrapper


# Retained as an alias so existing call sites keep working. With EULA
# enforcement removed, the "lenient" variant is identical to require_auth.
require_auth_lenient = require_auth


def require_admin(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Require a valid session JWT cookie + ``role == 'admin'``.

    Reasonbook is single-tenant with a single local admin role; there is
    no cross-tenant/support super-admin.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        payload = _read_token()
        if payload is None:
            return _unauthorized()
        if payload.role != "admin":
            return _forbidden("admin role required", role=payload.role)
        g.auth = payload
        return fn(*args, **kwargs)

    return wrapper
