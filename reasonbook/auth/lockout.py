# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Account lockout — consecutive-failure counter with unlock paths.

Complements the per-IP / per-account rate limiter (in
``dp/auth/rate_limit.py``). The rate limiter caps burst pacing within
short windows; the lockout counter is a cross-window count that fires
after ``LOCKOUT_THRESHOLD`` total failures regardless of how slowly an
attacker paces under the rate-limit ceiling.

State lives on ``platform.users`` (migration 0032):

- ``consecutive_failures`` — rolling integer, zeroed on successful login.
- ``locked_at`` — timestamp when lockout fired; NULL when not locked.
- ``lock_reason`` — captured human-readable reason for the lock.

This module owns the state transitions. Side effects (sending the lockout
email, writing audit rows) are the caller's responsibility — handlers
have request context (IP, headers) that this module doesn't.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from reasonbook.models import User

log = logging.getLogger(__name__)


# Threshold deliberately above the per-account rate limit (5/15min) so the
# two defenses layer rather than racing. A burst attacker trips the rate
# limit first (gets 429s, has to wait); a patient attacker who paces under
# the rate limit gets caught here after 10 cumulative wrong passwords.
LOCKOUT_THRESHOLD = 10

_DEFAULT_REASON = f"{LOCKOUT_THRESHOLD} consecutive failed login attempts"


def is_locked(user: User) -> bool:
    """True when the user's account is currently locked."""
    return user.locked_at is not None


def record_failure(user: User, *, session: Session, reason: str | None = None) -> bool:
    """Increment ``consecutive_failures``; lock account when threshold reached.

    Returns True if this call flipped the account from unlocked to locked
    (the caller should then send the lockout email and write an audit
    row). Returns False if the account was already locked or the
    threshold wasn't reached.

    The session is flushed inside this function so the new state is
    visible to the surrounding transaction; the caller controls commit.
    """
    if user.locked_at is not None:
        # Already locked. Don't keep incrementing — counter freezes at
        # whatever it was when lockout fired.
        return False

    user.consecutive_failures = (user.consecutive_failures or 0) + 1
    just_locked = False
    if user.consecutive_failures >= LOCKOUT_THRESHOLD:
        user.locked_at = datetime.now(UTC)
        user.lock_reason = reason or _DEFAULT_REASON
        just_locked = True
        log.info(
            "account locked user_id=%s threshold=%d reason=%s",
            user.id,
            LOCKOUT_THRESHOLD,
            user.lock_reason,
        )
    session.flush()
    return just_locked


def record_success(user: User, *, session: Session) -> bool:
    """Zero ``consecutive_failures`` on successful authentication.

    Returns True when this call cleared an existing lockout (which only
    happens if a locked account somehow authenticates — defensive; the
    login handler should reject locked accounts before calling
    authenticate). Returns False in the normal case where no lockout was
    in place.
    """
    was_locked = user.locked_at is not None
    user.consecutive_failures = 0
    if was_locked:
        # Defensive: shouldn't normally happen because the handler rejects
        # locked accounts before authenticate runs. If it does, treat
        # successful auth as a valid unlock signal.
        user.locked_at = None
        user.lock_reason = None
        log.warning(
            "lockout cleared by successful authentication user_id=%s (handler should have rejected)",
            user.id,
        )
    session.flush()
    return was_locked


def unlock(
    user: User,
    *,
    session: Session,
    reason: str,
    actor_user_id: str | None = None,
) -> None:
    """Clear lockout state via an explicit unlock path.

    ``reason`` is one of ``"password_reset"``, ``"magic_link"``,
    ``"admin_override"``. The caller writes the audit row with the
    appropriate actor; this module just clears the state.
    """
    if user.locked_at is None:
        # No-op for unlocked accounts. Don't fail — admin clicking
        # "unlock" on an already-unlocked account is benign.
        return
    user.locked_at = None
    user.lock_reason = None
    user.consecutive_failures = 0
    session.flush()
    log.info(
        "account unlocked user_id=%s reason=%s actor=%s",
        user.id,
        reason,
        actor_user_id,
    )
