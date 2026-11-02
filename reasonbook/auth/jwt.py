# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""HS256 JWT issuance and verification.

The session token is an HS256 JWT signed with ``REASONBOOK_SECRET_KEY``.
A single shared secret (rather than an RSA key pair) keeps the
single-container deployment simple: one secret to configure, tokens
survive restarts, and there are no key files to manage. The application
factory fails fast when the secret is unset in production.

Tokens are short-lived (``REASONBOOK_JWT_TTL_MINUTES``, default 30).
Logout clears the client cookie only; there is no server-side revocation
list in v1.0 (see README, Known limitations).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt as pyjwt

from reasonbook.config import get_settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TokenPayload:
    """Decoded JWT claims."""

    sub: str  # user_id (UUID string)
    tenant: str  # organization id (single-tenant constant)
    role: str  # admin | member
    # Fund-flow tier (TENANCY-MODEL §3): tier ∈ {federal, state, recipient};
    # participant_org_id is the user's state/recipient org (NULL only when
    # tier='federal'). Carried in the JWT so apply_tier_scope can filter
    # without a per-request DB hop.
    tier: str
    participant_org_id: str | None  # UUID string or None for federal
    agency_id: str | None  # primary agency (UUID string) for federal-tier users
    jti: str  # unique token id
    iat: int
    exp: int


def issue_token(
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    tier: str = "federal",
    participant_org_id: str | None = None,
    agency_id: str | None = None,
    ttl_seconds: int | None = None,
) -> tuple[str, TokenPayload]:
    """Sign and return a session JWT plus its decoded payload."""
    settings = get_settings()
    now = int(time.time())
    ttl = ttl_seconds if ttl_seconds is not None else settings.jwt_ttl_minutes * 60
    jti = str(uuid.uuid4())
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tenant": tenant_id,
        "role": role,
        "tier": tier,
        "participant_org_id": participant_org_id,
        "agency_id": agency_id,
        "iss": settings.jwt_issuer,
        "jti": jti,
        "iat": now,
        "exp": now + ttl,
    }
    token = pyjwt.encode(claims, settings.secret_key, algorithm="HS256")
    return token, _payload_from_claims(claims)


def verify_token(token: str) -> TokenPayload:
    """Decode and verify a JWT. Raises ``jwt.PyJWTError`` subclasses on failure."""
    settings = get_settings()
    claims = pyjwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        options={"require": ["exp", "iat", "sub", "jti"]},
    )
    return _payload_from_claims(claims)


def decode_unverified(token: str) -> dict[str, Any]:
    """Decode without verifying the signature (grabs jti/exp on logout)."""
    return pyjwt.decode(token, options={"verify_signature": False})


def _payload_from_claims(claims: dict[str, Any]) -> TokenPayload:
    raw_org = claims.get("participant_org_id")
    raw_agency = claims.get("agency_id")
    return TokenPayload(
        sub=str(claims["sub"]),
        tenant=str(claims["tenant"]),
        role=str(claims.get("role", "member")),
        tier=str(claims.get("tier", "federal")),
        participant_org_id=str(raw_org) if raw_org else None,
        agency_id=str(raw_agency) if raw_agency else None,
        jti=str(claims["jti"]),
        iat=int(claims["iat"]),
        exp=int(claims["exp"]),
    )
