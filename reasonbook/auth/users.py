# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""UserManager — authenticates and looks up users against the platform schema.

Ports legacy `auth/users.py`, dropped:

- The JSON-config fallback (legacy v1.4 path) is retired — Reasonbook is DB-only.
- The pbkdf2-via-werkzeug hash format is replaced with bcrypt to match the
  seed script and avoid the werkzeug dependency in core auth.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import bcrypt

from reasonbook.auth.lockout import is_locked, record_failure, record_success
from reasonbook.db import session_scope
from reasonbook.models import Tenant, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# Bcrypt cost (work factor / rounds). Default 12 (~250ms per hash) is the
# security floor for production. CI sets BCRYPT_TEST_COST=4 (~3ms) because
# the test suite does many hash + check pairs and the cost dominates wall
# time. Production MUST NOT set this — the variable name is the signal.
# The constant is read once at import; both _DUMMY_HASH and hash_password
# pick it up so constant-time-padding stays constant-time at whatever cost
# the runtime is using.
_BCRYPT_COST = int(os.environ.get("BCRYPT_TEST_COST", "12"))


# Precomputed at import. Used as the bcrypt target for unknown / inactive /
# locked users so authenticate()'s wall-clock timing is uniform across all
# negative paths — closes timing-based account enumeration that the rate
# limiter can't catch on the first attempt. The hash itself never matches
# any real password (we hash a fixed sentinel that no signup flow would
# produce — bcrypt hashes are 60 bytes and silent salts mean we'd never
# accidentally collide with a real user's hash).
_DUMMY_HASH = bcrypt.hashpw(
    b"__reasonbook_dummy_for_constant_time_padding__", bcrypt.gensalt(_BCRYPT_COST)
).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(_BCRYPT_COST)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class AuthResult:
    """Tagged outcome of an authentication attempt.

    The login handler branches on these flags; the wire response is
    intentionally uniform (401 for "invalid credentials" regardless of
    which negative path fired) so attackers can't distinguish unknown
    accounts, wrong passwords, or inactive accounts. ``locked`` /
    ``just_locked`` flow to the 423 + email path; ``user`` + ``authenticated``
    drives the success path.
    """

    user: User | None  # populated when the username resolves to a real account
    authenticated: bool  # True only on successful password match
    locked: bool  # True when the resolved account is currently locked
    just_locked: bool  # True when THIS call flipped the account into lockout


def authenticate(username: str, password: str) -> AuthResult:
    """Validate credentials and return a tagged ``AuthResult``.

    Constant-time discipline: bcrypt runs on every code path, including
    unknown users, inactive accounts, and locked accounts. Without this
    padding an attacker can distinguish the cases by wall-clock timing
    (bcrypt costs ~50ms; a username miss returns in microseconds).

    Lockout discipline: failed password checks on known active accounts
    increment ``consecutive_failures`` via ``lockout.record_failure``;
    reaching the threshold flips ``locked_at`` and surfaces via the
    ``just_locked`` flag so the handler can send the lockout email and
    write the audit row.
    """
    normalized = username.strip()
    with session_scope() as session:
        user = session.query(User).filter(User.username.ilike(normalized)).one_or_none()

        # Unknown user — pad with bcrypt to match the timing of the known-user
        # negative paths below, then return.
        if user is None:
            verify_password(password, _DUMMY_HASH)
            return AuthResult(user=None, authenticated=False, locked=False, just_locked=False)

        # Inactive account — same uniform-timing treatment. Caller sees the
        # same 401 as the unknown-user path.
        if user.status != "active":
            verify_password(password, _DUMMY_HASH)
            log.info("login rejected for username=%s status=%s", username, user.status)
            session.expunge(user)
            return AuthResult(user=user, authenticated=False, locked=False, just_locked=False)

        # Locked account — pad with bcrypt (uniform timing) and surface the
        # locked state. The handler returns 423 + a "check your email"
        # message; no per-attempt email since the email already went out at
        # the lockout-fire moment.
        if is_locked(user):
            verify_password(password, _DUMMY_HASH)
            session.expunge(user)
            return AuthResult(user=user, authenticated=False, locked=True, just_locked=False)

        # Real password check.
        if not verify_password(password, user.password_hash):
            just_locked = record_failure(user, session=session)
            session.expunge(user)
            return AuthResult(
                user=user,
                authenticated=False,
                locked=just_locked,  # if THIS call flipped lockout, account is now locked
                just_locked=just_locked,
            )

        # Success.
        record_success(user, session=session)
        user.last_login_at = datetime.now(UTC)
        user.login_count = (user.login_count or 0) + 1
        session.flush()
        session.expunge(user)
        return AuthResult(user=user, authenticated=True, locked=False, just_locked=False)


def get_user(user_id: str, *, session: Session | None = None) -> User | None:
    """Look up a user by id. Caller-managed session is preferred for hot paths."""
    if session is not None:
        return session.get(User, user_id)
    with session_scope() as managed:
        user = managed.get(User, user_id)
        if user is not None:
            managed.expunge(user)
        return user


def get_tenant(tenant_id: str, *, session: Session | None = None) -> Tenant | None:
    if session is not None:
        return session.get(Tenant, tenant_id)
    with session_scope() as managed:
        tenant = managed.get(Tenant, tenant_id)
        if tenant is not None:
            managed.expunge(tenant)
        return tenant


