# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""JWT carries tenancy tier + participant_org_id (TENANCY §10 step 2)."""

from __future__ import annotations

import uuid

from reasonbook.auth.jwt import _payload_from_claims, issue_token, verify_token


def test_token_default_federal_tier() -> None:
    """Defaults preserve compatibility — federal / no org when not passed."""
    token, payload = issue_token(
        user_id=str(uuid.uuid4()),
        tenant_id="us-federal",
        role="member",
    )
    assert payload.tier == "federal"
    assert payload.participant_org_id is None

    # Round-trip through verify_token (decode + signature check).
    decoded = verify_token(token)
    assert decoded.tier == "federal"
    assert decoded.participant_org_id is None


def test_token_state_tier_with_org() -> None:
    org_id = str(uuid.uuid4())
    token, payload = issue_token(
        user_id=str(uuid.uuid4()),
        tenant_id="us-federal",
        role="member",
        tier="state",
        participant_org_id=org_id,
    )
    assert payload.tier == "state"
    assert payload.participant_org_id == org_id

    decoded = verify_token(token)
    assert decoded.tier == "state"
    assert decoded.participant_org_id == org_id


def test_token_recipient_tier_with_org() -> None:
    org_id = str(uuid.uuid4())
    _, payload = issue_token(
        user_id=str(uuid.uuid4()),
        tenant_id="us-federal",
        role="member",
        tier="recipient",
        participant_org_id=org_id,
    )
    assert payload.tier == "recipient"
    assert payload.participant_org_id == org_id


def test_legacy_token_without_tier_claims_defaults_federal() -> None:
    """Tokens issued pre-migration must keep working until natural expiry."""
    legacy_claims = {
        "sub": str(uuid.uuid4()),
        "tenant": "us-federal",
        "role": "member",
        "has_oversight": False,
        # No 'tier' or 'participant_org_id' claims.
        "jti": str(uuid.uuid4()),
        "iat": 1_700_000_000,
        "exp": 1_700_100_000,
    }
    payload = _payload_from_claims(legacy_claims)
    assert payload.tier == "federal"
    assert payload.participant_org_id is None
