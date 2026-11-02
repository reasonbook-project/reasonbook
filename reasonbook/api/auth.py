# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Session auth endpoints — login, logout, me, session, password reset."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import structlog
from flask import Blueprint, Response, current_app, g, jsonify, make_response, request

from reasonbook.auth.decorators import SESSION_COOKIE, require_auth, require_auth_lenient
from reasonbook.auth.jwt import issue_token
from reasonbook.auth.lockout import unlock as clear_lockout
from reasonbook.auth.rate_limit import (
    RateLimitResult,
    RateLimitStoreUnavailableError,
    check_rate_limit,
)
from reasonbook.auth.revocation import revoke
from reasonbook.auth.tokens import (
    TokenStoreUnavailableError,
    consume_reset_token,
    consume_unlock_token,
    consume_verify_token,
    mint_reset_token,
    mint_unlock_token,
    mint_verify_token,
)
from reasonbook.auth.users import AuthResult, authenticate, get_tenant, get_user, hash_password
from reasonbook.config import get_settings
from reasonbook.db import session_scope
from reasonbook.email.sender import send_email
from reasonbook.logging import hash_pii, hash_pii_for_log
from reasonbook.models import User, UserAudit
from reasonbook.oversight.authority import OversightCapabilities, resolve_oversight_capabilities

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)
slog = structlog.get_logger(__name__)


# Login rate-limit constants. Per the security plan: per-IP catches the
# spray case (one source against many accounts) cheaply; per-account catches
# the targeted case (many sources against one account) by hashing the
# username into the counter key.
LOGIN_IP_LIMIT = 10
LOGIN_IP_WINDOW_S = 5 * 60  # 5 minutes
LOGIN_ACCOUNT_LIMIT = 5
LOGIN_ACCOUNT_WINDOW_S = 15 * 60  # 15 minutes

# Forgot-password and resend-verification rate limits — email-bombing
# protection. Lower caps than login because the harm class is different:
# repeated emails to one address don't help an attacker discover anything;
# they just abuse our SMTP quota and annoy the user.
FORGOT_PASSWORD_LIMIT = 5
FORGOT_PASSWORD_WINDOW_S = 60 * 60  # 1 hour
RESEND_VERIFICATION_LIMIT = 3
RESEND_VERIFICATION_WINDOW_S = 60 * 60  # 1 hour


def _is_secure() -> bool:
    settings = current_app.config["SETTINGS"]
    return bool(settings.flask_env != "development")


def _set_session_cookie(resp: Response, token: str, *, max_age: int) -> None:
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=_is_secure(),
        samesite="Lax",
        path="/",
    )


def _clear_session_cookie(resp: Response) -> None:
    resp.delete_cookie(SESSION_COOKIE, path="/", samesite="Lax")


def _oversight_capabilities_dict(caps: OversightCapabilities | None) -> dict[str, Any] | None:
    if caps is None:
        return None
    return {
        "oversight_role": caps.oversight_role,
        "domains_owned": list(caps.domains_owned),
        "can_record_committee_action": caps.can_record_committee_action,
        "is_executive": caps.is_executive,
        "is_committee": caps.is_committee,
        "level": caps.level,
    }


def _user_payload(
    *,
    user: Any,
    tenant: Any,
    oversight_capabilities: OversightCapabilities | None = None,
) -> dict[str, Any]:
    # Agency chain: primary agency + parent walk, top-down. Feeds the
    # frontend's breadcrumb + org-scope UI (e.g. HHS › NIH › NIH-OER).
    # Computed here so the frontend doesn't have to walk the parent
    # pointer per request.
    from reasonbook.db import session_scope
    from reasonbook.models import Agency

    agency_chain: list[dict[str, Any]] = []
    primary_agency: dict[str, Any] | None = None
    if user.agency_id is not None:
        with session_scope() as session:
            current = session.get(Agency, user.agency_id)
            while current is not None:
                entry = {
                    "id": str(current.id),
                    "slug": current.agency_slug,
                    "name": current.name,
                    "short_name": current.short_name,
                    "depth": current.depth,
                }
                agency_chain.append(entry)
                if current.parent_agency_id is None:
                    break
                current = session.get(Agency, current.parent_agency_id)
        # Reverse: top-down (department → bureau → office).
        agency_chain.reverse()
        primary_agency = agency_chain[-1] if agency_chain else None

    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "title": user.title,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "tenant_name": tenant.name if tenant else None,
        # Tenancy tier per TENANCY-MODEL §3. Frontend uses this to gate
        # tier-restricted affordances (federal-only "Create matter"
        # button, state-only "Amend" actions on matter nodes).
        "tier": user.tier,
        "participant_org_id": (
            str(user.participant_org_id) if user.participant_org_id else None
        ),
        # Agency scope. Introduced with migration 0046 — DP is single-
        # tenant / multi-agency, and every federal-tier user belongs to
        # exactly one primary agency plus optional cross-agency grants.
        "agency_id": str(user.agency_id) if user.agency_id else None,
        "agency": primary_agency,
        "agency_chain": agency_chain,
        # Oversight capabilities — null for users without an oversight grant.
        # Drives the committee-action affordance on oversight Decision Detail.
        "oversight_capabilities": _oversight_capabilities_dict(oversight_capabilities),
    }


@bp.post("/auth/login")
def login() -> tuple[Response, int]:
    """Authenticate a user against the platform schema.

    Defense layers, in order:
      1. Per-IP rate limit (10/5min, all attempts counted).
      2. Constant-time ``authenticate()`` — bcrypt runs on every code path
         so timing doesn't leak account existence.
      3. Lockout check — 423 if the account is currently locked.
      4. Per-account rate limit (5/15min, failed attempts only) — only
         increments inside the failed-auth branch so legitimate users
         don't trip it. SHA-256-keyed for key hygiene.
      5. Lockout fire — record_failure inside authenticate() flips the
         account at 10 cumulative failures and surfaces via ``just_locked``.

    Login rate limiting is disabled in v1.0 (see README).
    """
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    ip = _client_ip()
    username_norm = username.lower()

    # 1. Per-IP rate limit. Counts every attempt regardless of outcome.
    try:
        ip_result = check_rate_limit(
            f"login_ip:{ip}",
            limit=LOGIN_IP_LIMIT,
            window_s=LOGIN_IP_WINDOW_S,
        )
    except RateLimitStoreUnavailableError:
        log.error("login rate-limit store unavailable; failing closed")
        return jsonify({"error": "service_unavailable"}), 503

    if not ip_result.allowed:
        _emit_rate_limit_log(limit_type="ip", ip=ip, email=username_norm)
        return _rate_limited_response(ip_result.retry_after_s)

    # 2. Authenticate (constant-time padding handled inside).
    result: AuthResult = authenticate(username, password)

    # 3. Locked account — 423 regardless of password correctness. Don't
    # send another email; the email already went out at lockout-fire.
    if result.locked and not result.just_locked:
        return (
            jsonify(
                {
                    "error": "account_locked",
                    "message": "Your account is temporarily locked. Check your email for an unlock link.",
                }
            ),
            423,
        )

    # 4. Successful authentication — issue the session and return.
    if result.authenticated and result.user is not None:
        user = result.user
        tenant = get_tenant(user.tenant_id)

        token, payload = issue_token(
            user_id=str(user.id),
            tenant_id=user.tenant_id,
            role=user.role,
            tier=user.tier,
            participant_org_id=(
                str(user.participant_org_id) if user.participant_org_id else None
            ),
            agency_id=str(user.agency_id) if user.agency_id else None,
        )
        with session_scope() as session:
            oversight_caps = resolve_oversight_capabilities(session, user_id=user.id)
        body_out = _user_payload(
            user=user,
            tenant=tenant,
            oversight_capabilities=oversight_caps,
        )
        resp = make_response(jsonify(body_out), 200)
        _set_session_cookie(resp, token, max_age=payload.exp - payload.iat)
        return resp, 200

    # 5. Failed authentication path. Per-account counter increments here so
    # legitimate users with rapid logins don't accidentally trip it.
    if username_norm:
        try:
            account_result: RateLimitResult = check_rate_limit(
                f"login_account:{hash_pii(username_norm)}",
                limit=LOGIN_ACCOUNT_LIMIT,
                window_s=LOGIN_ACCOUNT_WINDOW_S,
            )
        except RateLimitStoreUnavailableError:
            log.error("login account rate-limit store unavailable; failing closed")
            return jsonify({"error": "service_unavailable"}), 503

        if not account_result.allowed:
            _emit_rate_limit_log(limit_type="account", ip=ip, email=username_norm)
            return _rate_limited_response(account_result.retry_after_s)

    # 6. Lockout just fired on this attempt — fire email/audit, then
    # return the same uniform 423 a subsequent locked-account attempt
    # would see (no leak about how it happened).
    if result.just_locked and result.user is not None:
        _handle_lockout_fired(user=result.user, ip=ip)
        return (
            jsonify(
                {
                    "error": "account_locked",
                    "message": "Your account is temporarily locked. Check your email for an unlock link.",
                }
            ),
            423,
        )

    # 7. Generic invalid-credentials response. Identical for unknown
    # users, inactive accounts, and wrong-password-on-known-account.
    return jsonify({"error": "invalid credentials"}), 401


@bp.post("/auth/logout")
def logout() -> tuple[Response, int]:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        revoke(token)
    resp = make_response(jsonify({"status": "ok"}), 200)
    _clear_session_cookie(resp)
    return resp, 200


@bp.get("/auth/me")
@require_auth_lenient
def me() -> tuple[Response, int]:
    payload = g.auth
    from reasonbook.auth.users import get_user

    user = get_user(payload.sub)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    tenant = get_tenant(user.tenant_id)
    with session_scope() as session:
        oversight_caps = resolve_oversight_capabilities(session, user_id=user.id)
    return (
        jsonify(
            _user_payload(
                user=user,
                tenant=tenant,
                oversight_capabilities=oversight_caps,
            )
        ),
        200,
    )


@bp.get("/auth/session")
@require_auth_lenient
def session_check() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200


# ---------------------------------------------------------------------------
# Email verification + password reset
# ---------------------------------------------------------------------------

# Top-50 trivially weak passwords. Belt-and-suspenders: bcrypt is fine for
# storage, but rejecting these at password-set time prevents the most
# obvious credential-stuffing fodder. Sourced from the SecLists rockyou top-50.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "123456",
        "password",
        "12345678",
        "qwerty",
        "123456789",
        "12345",
        "1234",
        "111111",
        "1234567",
        "dragon",
        "123123",
        "baseball",
        "abc123",
        "football",
        "monkey",
        "letmein",
        "shadow",
        "master",
        "666666",
        "qwertyuiop",
        "123321",
        "mustang",
        "1234567890",
        "michael",
        "654321",
        "superman",
        "1qaz2wsx",
        "7777777",
        "121212",
        "000000",
        "qazwsx",
        "123qwe",
        "killer",
        "trustno1",
        "jordan",
        "jennifer",
        "zxcvbnm",
        "asdfgh",
        "hunter",
        "buster",
        "soccer",
        "harley",
        "batman",
        "andrew",
        "tigger",
        "sunshine",
        "iloveyou",
        "fuckme",
        "2000",
        "charlie",
    }
)


def _client_ip() -> str:
    """Return the request client IP.

    ProxyFix (registered in reasonbook/app.py) sets request.remote_addr to the
    leftmost X-Forwarded-For entry, so this is now the trusted client IP
    from DO App Platform's LB. Keeping the helper as a one-line wrapper
    so all rate-limit / audit-log call sites read consistently and so
    tests have a single mock target.
    """
    return request.remote_addr or "0.0.0.0"


def _emit_rate_limit_log(
    *,
    limit_type: str,
    ip: str,
    email: str | None,
) -> None:
    """Structured warning on every login 429.

    PII (IP and email) is SHA-256-hashed before emission so log
    aggregation can spot patterns ("same email tripped from 12 IPs in
    one hour") without parking raw PII in the log surface.
    """
    slog.warning(
        "login_rate_limit_tripped",
        limit_type=limit_type,
        ip_hash=hash_pii_for_log(ip),
        email_hash=hash_pii_for_log(email) if email else None,
    )


def _rate_limited_response(retry_after_s: int) -> tuple[Response, int]:
    """Uniform 429 response. Generic body — no leak about which limit tripped."""
    resp = make_response(jsonify({"error": "too_many_requests"}), 429)
    resp.headers["Retry-After"] = str(retry_after_s)
    return resp, 429


def _send_lockout_email(
    *,
    to_email: str,
    name: str,
    unlock_token: str,
    source_ip: str,
) -> None:
    """Best-effort lockout email. Never raises.

    Sent once at the moment of lockout fire (not per failed attempt).
    Carries two recovery paths so the user picks whichever fits:

    - Magic-link unlock — clicks the link, account unlocks, password
      unchanged. For the user who knows their password and was locked by
      an attacker spraying their account.
    - Password reset — separate link to the standard reset flow.
    """
    settings = get_settings()
    base = settings.app_url.rstrip("/")
    unlock_link = f"{base}/unlock-account?token={unlock_token}"
    reset_link = f"{base}/forgot-password"
    subject = "Your Reasonbook account was locked"
    body = (
        f"Hi {name},\n\n"
        f"We locked your Reasonbook account after too many failed sign-in "
        f"attempts. The most recent attempt came from IP {source_ip}.\n\n"
        f"If that was you, unlock without changing your password:\n\n"
        f"{unlock_link}\n\n"
        f"This link expires in 1 hour.\n\n"
        f"If it wasn't you, reset your password to be safe:\n\n"
        f"{reset_link}\n\n"
        f"— Reasonbook\n"
    )
    send_email(to_addr=to_email, subject=subject, body=body)


def _handle_lockout_fired(*, user: User, ip: str) -> None:
    """Side-effects when a failed login flips an account into lockout.

    Three things happen, all best-effort: mint an unlock token, send the
    email, write an audit row. Failures in any one log a warning but
    don't bubble up — the lockout itself is already persisted by
    ``record_failure``; this function just notifies the user and records
    the event.
    """
    user_id = str(user.id)
    try:
        unlock_token = mint_unlock_token(user_id)
    except TokenStoreUnavailableError as exc:
        log.warning("could not mint unlock token for locked user=%s: %s", user_id, exc)
        unlock_token = ""

    if unlock_token:
        try:
            _send_lockout_email(
                to_email=user.email,
                name=user.name,
                unlock_token=unlock_token,
                source_ip=ip,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("lockout email send failed for user=%s: %s", user_id, exc)

    try:
        with session_scope() as s:
            s.add(
                UserAudit(
                    user_id=user.id,
                    changed_by=user.id,
                    action="locked",
                    audit_metadata={
                        "lock_reason": user.lock_reason,
                        "trigger": "consecutive_login_failures",
                    },
                    ip_address=ip,
                )
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("lockout audit write failed for user=%s: %s", user_id, exc)


def _send_verification_email(*, to_email: str, name: str, token: str) -> None:
    """Best-effort verification email. Never raises."""
    settings = get_settings()
    link = f"{settings.app_url.rstrip('/')}/verify-email?token={token}"
    subject = "Verify your Reasonbook email"
    body = (
        f"Hi {name},\n\n"
        f"Welcome to Reasonbook. Confirm this email so we can "
        f"reach you about your account:\n\n"
        f"{link}\n\n"
        f"This link expires in 7 days. If you didn't sign up, you can ignore this email.\n\n"
        f"— Reasonbook\n"
    )
    send_email(to_addr=to_email, subject=subject, body=body)


def _send_password_reset_email(*, to_email: str, name: str, token: str) -> None:
    """Best-effort password-reset email. Never raises."""
    settings = get_settings()
    link = f"{settings.app_url.rstrip('/')}/reset-password?token={token}"
    subject = "Reset your Reasonbook password"
    body = (
        f"Hi {name},\n\n"
        f"Someone (hopefully you) asked to reset the password on your Reasonbook "
        f"account. Use this link to set a new one:\n\n"
        f"{link}\n\n"
        f"The link expires in 1 hour. If you didn't request this, you can ignore "
        f"the email — your existing password still works.\n\n"
        f"— Reasonbook\n"
    )
    send_email(to_addr=to_email, subject=subject, body=body)


@bp.get("/auth/verify-email")
def verify_email() -> tuple[Response, int]:
    """Consume a verification token and mark the user's email verified."""
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token required"}), 400

    try:
        user_id = consume_verify_token(token)
    except TokenStoreUnavailableError:
        return jsonify({"error": "verification temporarily unavailable"}), 503

    if user_id is None:
        return jsonify({"error": "invalid or expired token"}), 400

    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            return jsonify({"error": "user not found"}), 404
        if not user.email_verified:
            user.email_verified = True
            s.add(
                UserAudit(
                    user_id=user.id,
                    changed_by=user.id,
                    action="updated",
                    field_name="email_verified",
                    old_value="False",
                    new_value="True",
                    ip_address=_client_ip(),
                )
            )
    return jsonify({"status": "verified"}), 200


@bp.post("/auth/resend-verification")
@require_auth
def resend_verification() -> tuple[Response, int]:
    """Mint a fresh verification token for the current user and email it.

    Rate-limited per user to 3/hour — authenticated endpoint so 429 is
    safe (no enumeration concern; we already know the user). Fail-closed
    on a store error, consistent with the rest of the auth surface.
    """
    payload = g.auth
    user = get_user(payload.sub)
    if user is None:
        return jsonify({"error": "user not found"}), 404
    if user.email_verified:
        return jsonify({"status": "already verified"}), 200

    # Per-user rate limit keyed by user_id (already unique, no hashing
    # needed for key hygiene).
    try:
        rate = check_rate_limit(
            f"verifyresend_rate:{user.id}",
            limit=RESEND_VERIFICATION_LIMIT,
            window_s=RESEND_VERIFICATION_WINDOW_S,
        )
    except RateLimitStoreUnavailableError:
        log.error("resend-verification rate-limit store unavailable; failing closed")
        return jsonify({"error": "service_unavailable"}), 503

    if not rate.allowed:
        _emit_rate_limit_log(
            limit_type="resend_verification",
            ip=_client_ip(),
            email=user.email,
        )
        resp = make_response(jsonify({"error": "too_many_requests"}), 429)
        resp.headers["Retry-After"] = str(rate.retry_after_s)
        return resp, 429

    try:
        token = mint_verify_token(str(user.id))
    except TokenStoreUnavailableError:
        return jsonify({"error": "verification temporarily unavailable"}), 503

    _send_verification_email(to_email=user.email, name=user.name, token=token)
    return jsonify({"status": "sent"}), 200


@bp.post("/auth/forgot-password")
def forgot_password() -> tuple[Response, int]:
    """Issue a password-reset token if the email exists. Always returns 200.

    The same response shape on hit and miss prevents address enumeration.
    """
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not email:
        # Still return 200 to avoid leaking input-shape probing.
        return jsonify({"status": "sent"}), 200

    try:
        with session_scope() as s:
            user = s.query(User).filter(User.email.ilike(email)).one_or_none()
            if user is not None and user.status == "active":
                user_id = str(user.id)
                user_name = user.name
                user_email = user.email
                user_role = user.role
            else:
                user_id = None
                user_name = ""
                user_email = ""
                user_role = ""
    except Exception as exc:  # noqa: BLE001
        log.error("forgot-password lookup failed for email=%s: %s", email, exc)
        return jsonify({"status": "sent"}), 200

    # Email-bombing rate limit. Keyed by the request email (hashed for
    # key hygiene). Fail-closed silently — if the store errors or the
    # limit trips, we skip the mint+send but still return 200 with the
    # same body so no enumeration / outage signal leaks to the client.
    rate_ok = True
    try:
        rate_ok = check_rate_limit(
            f"pwreset_rate:{hash_pii(email)}",
            limit=FORGOT_PASSWORD_LIMIT,
            window_s=FORGOT_PASSWORD_WINDOW_S,
        ).allowed
    except RateLimitStoreUnavailableError:
        log.error("forgot-password rate-limit store unavailable; silently skipping send")
        rate_ok = False

    if not rate_ok:
        _emit_rate_limit_log(limit_type="forgot_password", ip=_client_ip(), email=email)

    if user_id is not None and rate_ok:
        try:
            token = mint_reset_token(user_id)
            _send_password_reset_email(to_email=user_email, name=user_name, token=token)
        except TokenStoreUnavailableError as exc:
            log.warning("could not mint reset token for user=%s: %s", user_id, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("password-reset email send failed for user=%s: %s", user_id, exc)

    # Tiny stall so timing-side-channel can't tell hit from miss.
    time.sleep(0.05)
    return jsonify({"status": "sent"}), 200


@bp.post("/auth/reset-password")
def reset_password() -> tuple[Response, int]:
    """Consume a password-reset token and set the new password."""
    body = request.get_json(silent=True) or {}
    token = (body.get("token") or "").strip()
    new_password = body.get("password") or ""

    if not token:
        return jsonify({"error": "token required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if new_password.lower() in COMMON_PASSWORDS:
        return jsonify({"error": "password is too common; pick something less guessable"}), 400

    try:
        user_id = consume_reset_token(token)
    except TokenStoreUnavailableError:
        return jsonify({"error": "reset temporarily unavailable"}), 503

    if user_id is None:
        return jsonify({"error": "invalid or expired token"}), 400

    new_hash = hash_password(new_password)
    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            return jsonify({"error": "user not found"}), 404
        was_locked = user.locked_at is not None
        user.password_hash = new_hash
        user.password_changed_at = datetime.now(UTC)
        user.must_change_password = False
        # Successful password reset auto-unlocks. The reset flow proves
        # control of the user's email; if they were locked by an attacker
        # spraying their account, this is the canonical recovery path.
        if was_locked:
            clear_lockout(user, session=s, reason="password_reset", actor_user_id=user_id)
            s.add(
                UserAudit(
                    user_id=user.id,
                    changed_by=user.id,
                    action="unlocked",
                    audit_metadata={"unlock_reason": "password_reset"},
                    ip_address=_client_ip(),
                )
            )
        s.add(
            UserAudit(
                user_id=user.id,
                changed_by=user.id,
                action="password_reset",
                ip_address=_client_ip(),
            )
        )
    return jsonify({"status": "ok"}), 200


@bp.get("/auth/unlock-account")
def unlock_account() -> tuple[Response, int]:
    """Consume a lockout magic-link token and clear the user's lockout state.

    For the legitimate user who knows their password — they were locked
    by an attacker spraying their account, and don't want to change
    their password just to recover. Token is mailed at lockout-fire and
    expires after 1 hour.
    """
    token = (request.args.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token required"}), 400

    try:
        user_id = consume_unlock_token(token)
    except TokenStoreUnavailableError:
        return jsonify({"error": "unlock temporarily unavailable"}), 503

    if user_id is None:
        return jsonify({"error": "invalid or expired token"}), 400

    with session_scope() as s:
        user = s.get(User, user_id)
        if user is None:
            return jsonify({"error": "user not found"}), 404
        if user.locked_at is None:
            # Already unlocked — idempotent no-op. Return 200 so the
            # frontend's success page renders.
            return jsonify({"status": "ok", "message": "Account is already unlocked."}), 200
        clear_lockout(user, session=s, reason="magic_link", actor_user_id=user_id)
        s.add(
            UserAudit(
                user_id=user.id,
                changed_by=user.id,
                action="unlocked",
                audit_metadata={"unlock_reason": "magic_link"},
                ip_address=_client_ip(),
            )
        )
    return jsonify({"status": "ok"}), 200
