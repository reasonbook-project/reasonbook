# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Short-lived DB-backed tokens for email verification, reset, and unlock.

Three token kinds with different TTLs:

- ``verify`` — 7-day TTL. Issued at signup and on resend; consumed by
  ``GET /api/auth/verify-email``.
- ``reset`` — 1-hour TTL. Issued by ``POST /api/auth/forgot-password``;
  consumed by ``POST /api/auth/reset-password``.
- ``unlock`` — 1-hour TTL. Lockout magic-link; consumed by
  ``GET /api/auth/unlock-account``.

Tokens are 32-byte URL-safe random strings. Only the SHA-256 hash is
stored (in the ``auth_tokens`` table); consumption deletes the row so a
token works exactly once. No external cache — the single container's
database is the only dependency.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select

from reasonbook.db import session_scope
from reasonbook.models.auth_tokens import AuthToken

log = logging.getLogger(__name__)

VERIFY_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
RESET_TTL_SECONDS = 60 * 60  # 1 hour
UNLOCK_TTL_SECONDS = 60 * 60  # 1 hour — lockout magic-link token
TOKEN_BYTES = 32


class TokenStoreUnavailableError(RuntimeError):
    """Raised when the token store cannot be used.

    Retained for API compatibility with callers that fail closed on a
    store error. The DB-backed store does not raise it in normal
    operation; a genuine database error propagates as SQLAlchemy's own
    exception.
    """


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _mint(kind: str, user_id: str, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    with session_scope() as s:
        s.add(
            AuthToken(
                token_hash=_hash(token),
                kind=kind,
                user_id=uuid.UUID(str(user_id)),
                expires_at=expires_at,
            )
        )
    return token


def _consume(kind: str, token: str) -> str | None:
    """Look up, validate TTL, and delete a token. Returns user_id or None."""
    if not token:
        return None
    token_hash = _hash(token)
    with session_scope() as s:
        row = s.execute(
            select(AuthToken).where(
                AuthToken.token_hash == token_hash, AuthToken.kind == kind
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        user_id = str(row.user_id)
        expires_at = row.expires_at
        # Delete unconditionally (single-use), even if expired.
        s.execute(delete(AuthToken).where(AuthToken.token_hash == token_hash))
    # Normalize to aware UTC for comparison (SQLite stores naive).
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None
    return user_id


def mint_verify_token(user_id: str) -> str:
    """Mint a 7-day email-verification token for the given user."""
    return _mint("verify", user_id, VERIFY_TTL_SECONDS)


def consume_verify_token(token: str) -> str | None:
    """Consume an email-verification token. Returns user_id or None if invalid/expired."""
    return _consume("verify", token)


def mint_reset_token(user_id: str) -> str:
    """Mint a 1-hour password-reset token for the given user."""
    return _mint("reset", user_id, RESET_TTL_SECONDS)


def consume_reset_token(token: str) -> str | None:
    """Consume a password-reset token. Returns user_id or None if invalid/expired."""
    return _consume("reset", token)


def mint_unlock_token(user_id: str) -> str:
    """Mint a 1-hour lockout magic-link token for the given user."""
    return _mint("unlock", user_id, UNLOCK_TTL_SECONDS)


def consume_unlock_token(token: str) -> str | None:
    """Consume a lockout magic-link token. Returns user_id or None if invalid/expired."""
    return _consume("unlock", token)


__all__ = [
    "RESET_TTL_SECONDS",
    "UNLOCK_TTL_SECONDS",
    "VERIFY_TTL_SECONDS",
    "TokenStoreUnavailableError",
    "consume_reset_token",
    "consume_unlock_token",
    "consume_verify_token",
    "mint_reset_token",
    "mint_unlock_token",
    "mint_verify_token",
]
