# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Account lockout: fire conditions, unlock paths, constant-time padding.

Uses the existing seeded Riverdale data (Jamie Kim with the seed's
DEMO_PASSWORD) as the test user. Login rate-limiting is disabled in v1.0;
token store is mocked with a per-test in-memory dict.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy.engine import Engine

from reasonbook.app import create_app
from reasonbook.auth.lockout import LOCKOUT_THRESHOLD
from reasonbook.db import session_scope
from reasonbook.models import User, UserAudit
from scripts.seed_dev import DEMO_PASSWORD

JAMIE_USERNAME = "jamie.kim"
JAMIE_PASSWORD = DEMO_PASSWORD


@pytest.fixture()
def app(seeded: Engine) -> Iterator[Flask]:  # noqa: ARG001
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def lockout_tokens(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """In-memory store for unlock magic-link tokens."""
    store: dict[str, str] = {}
    counter = {"n": 0}

    def _mint(user_id: str) -> str:
        counter["n"] += 1
        token = f"unlock-{counter['n']}"
        store[token] = str(user_id)
        return token

    def _consume(token: str) -> str | None:
        return store.pop(token, None)

    import reasonbook.api.auth as auth_module
    import reasonbook.auth.tokens as tokens_module

    monkeypatch.setattr(tokens_module, "mint_unlock_token", _mint)
    monkeypatch.setattr(tokens_module, "consume_unlock_token", _consume)
    monkeypatch.setattr(auth_module, "mint_unlock_token", _mint)
    monkeypatch.setattr(auth_module, "consume_unlock_token", _consume)
    return store


def _login(client: FlaskClient, *, password: str, ip: str = "10.0.0.1") -> Any:
    return client.post(
        "/api/auth/login",
        json={"username": JAMIE_USERNAME, "password": password},
        headers={"X-Forwarded-For": ip},
    )


def _get_jamie() -> User:
    with session_scope() as s:
        user = s.query(User).filter(User.username == JAMIE_USERNAME).one()
        s.expunge(user)
        return user


# ---------------------------------------------------------------------------
# Lockout fire
# ---------------------------------------------------------------------------


def test_consecutive_failures_lock_account_at_threshold(
    client: FlaskClient,
    lockout_tokens: dict[str, str],
    captured_login_emails: list[dict[str, Any]],
) -> None:
    """Tenth consecutive failure locks the account; one email is sent."""
    # Rotate IPs so the per-IP / per-account rate limits don't preempt
    # the lockout — lockout threshold (10) > rate limits (10 IP, 5 account)
    # but the rate limit returns 429 before authenticate runs once the
    # counter trips. Rotating IPs keeps IP counter under cap; per-account
    # counter trips at the 6th failure — to drive 10 consecutive failures
    # cleanly we need different per-account behaviors. Easiest path:
    # bypass the rate limit altogether by widening the limits for this
    # test via the existing helper monkeypatch.
    import reasonbook.api.auth as auth_module

    # Bump both limits well past the lockout threshold so the rate-limit
    # branch never fires inside this test.
    object.__setattr__  # silence unused warning  # noqa: B018
    saved_ip_limit = auth_module.LOGIN_IP_LIMIT
    saved_acct_limit = auth_module.LOGIN_ACCOUNT_LIMIT
    auth_module.LOGIN_IP_LIMIT = 1000
    auth_module.LOGIN_ACCOUNT_LIMIT = 1000
    try:
        for _ in range(LOCKOUT_THRESHOLD):
            resp = _login(client, password="wrong")
            assert resp.status_code in (401, 423)
    finally:
        auth_module.LOGIN_IP_LIMIT = saved_ip_limit
        auth_module.LOGIN_ACCOUNT_LIMIT = saved_acct_limit

    user = _get_jamie()
    assert user.locked_at is not None
    assert user.lock_reason is not None
    assert "consecutive failed login" in user.lock_reason.lower()

    # Exactly one lockout email (not one per failed attempt).
    lockout_subjects = [e for e in captured_login_emails if "locked" in e["subject"].lower()]
    assert len(lockout_subjects) == 1
    assert "unlock" in lockout_subjects[0]["body"].lower()

    # Audit row written.
    with session_scope() as s:
        audits = (
            s.query(UserAudit)
            .filter(UserAudit.user_id == user.id, UserAudit.action == "locked")
            .all()
        )
        assert len(audits) == 1


def test_locked_account_returns_423_regardless_of_password(
    client: FlaskClient,
    lockout_tokens: dict[str, str],
    captured_login_emails: list[dict[str, Any]],
) -> None:
    """Once locked, even the correct password returns 423."""
    # Lock the user directly in the DB to avoid driving 10 failures.
    from datetime import UTC, datetime

    with session_scope() as s:
        user = s.query(User).filter(User.username == JAMIE_USERNAME).one()
        user.locked_at = datetime.now(UTC)
        user.lock_reason = "test setup"
        user.consecutive_failures = LOCKOUT_THRESHOLD

    resp = _login(client, password=JAMIE_PASSWORD)  # correct password
    assert resp.status_code == 423
    body = resp.get_json()
    assert body["error"] == "account_locked"


# ---------------------------------------------------------------------------
# Unlock paths
# ---------------------------------------------------------------------------


def test_magic_link_unlock_clears_lockout(
    client: FlaskClient,
    lockout_tokens: dict[str, str],
) -> None:
    """GET /auth/unlock-account?token=... clears locked_at."""
    from datetime import UTC, datetime

    with session_scope() as s:
        user = s.query(User).filter(User.username == JAMIE_USERNAME).one()
        user.locked_at = datetime.now(UTC)
        user.consecutive_failures = LOCKOUT_THRESHOLD
        user_id = str(user.id)

    # Mint an unlock token via the in-memory store directly.
    from reasonbook.auth.tokens import mint_unlock_token

    token = mint_unlock_token(user_id)

    resp = client.get(f"/api/auth/unlock-account?token={token}")
    assert resp.status_code == 200

    user_after = _get_jamie()
    assert user_after.locked_at is None
    assert user_after.consecutive_failures == 0


def test_password_reset_auto_unlocks(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful password reset clears lockout state in the same flow."""
    from datetime import UTC, datetime

    # In-memory reset token store
    store: dict[str, str] = {}
    counter = {"n": 0}

    def _mint(user_id: str) -> str:
        counter["n"] += 1
        token = f"reset-{counter['n']}"
        store[token] = str(user_id)
        return token

    def _consume(token: str) -> str | None:
        return store.pop(token, None)

    import reasonbook.api.auth as auth_module
    import reasonbook.auth.tokens as tokens_module

    monkeypatch.setattr(tokens_module, "mint_reset_token", _mint)
    monkeypatch.setattr(tokens_module, "consume_reset_token", _consume)
    monkeypatch.setattr(auth_module, "mint_reset_token", _mint)
    monkeypatch.setattr(auth_module, "consume_reset_token", _consume)

    with session_scope() as s:
        user = s.query(User).filter(User.username == JAMIE_USERNAME).one()
        user.locked_at = datetime.now(UTC)
        user.consecutive_failures = LOCKOUT_THRESHOLD
        user_id = str(user.id)

    token = _mint(user_id)

    resp = client.post(
        "/api/auth/reset-password",
        json={"token": token, "password": "fresh-strong-password-123"},
    )
    assert resp.status_code == 200

    user_after = _get_jamie()
    assert user_after.locked_at is None
    assert user_after.consecutive_failures == 0


# ---------------------------------------------------------------------------
# Constant-time padding
# ---------------------------------------------------------------------------


def test_constant_time_padding_bcrypt_called_on_unknown_user(
    client: FlaskClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bcrypt.checkpw runs for unknown users too — closes timing enumeration."""
    import bcrypt

    calls: list[Any] = []
    real_checkpw = bcrypt.checkpw

    def spy_checkpw(password: bytes, password_hash: bytes) -> bool:
        calls.append((password, password_hash))
        return real_checkpw(password, password_hash)

    monkeypatch.setattr("reasonbook.auth.users.bcrypt.checkpw", spy_checkpw)

    # Unknown username
    resp = client.post(
        "/api/auth/login",
        json={"username": "ghost@nowhere.invalid", "password": "anything"},
        headers={"X-Forwarded-For": "11.0.0.1"},
    )
    assert resp.status_code == 401
    assert len(calls) == 1, "bcrypt should run on unknown-user path for constant-time padding"
