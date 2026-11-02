# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Organization settings — basics + organization profile.

Reasonbook is single-tenant: there is one Organization row. This surface
exposes the small set of organization-level fields an admin can edit:
identifier basics (name, regulator, asset band) and the ``tenant_profile``
JSON (peer group hints, fiscal year, board cadence, examiner contacts,
risk-appetite statement).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from flask import Blueprint, Response, g, jsonify, request

from reasonbook.auth.decorators import require_admin, require_auth
from reasonbook.db import session_scope
from reasonbook.models import Tenant

bp = Blueprint("settings_tenant", __name__)

VALID_ORG_TYPES = ("CREDIT_UNION", "COMMUNITY_BANK", "SAVINGS_INSTITUTION")
VALID_REGULATORS = ("NCUA", "FDIC", "OCC", "STATE")
VALID_ASSET_BANDS = ("small", "medium", "large", "very_large")

# tenant_profile JSONB schema. Authoritative key list lives here so the
# PATCH validator can reject unknown top-level keys without locking the
# shape — values inside the known keys are passed through as-is.
PROFILE_KEYS = frozenset(
    {
        "peer_group",
        "fiscal_year_start_month",
        "board_cadence",
        "examiner_contacts",
        "risk_appetite_statement",
    }
)


def _tenant_dict(t: Tenant) -> dict[str, Any]:
    return {
        "tenant_id": t.tenant_id,
        "name": t.name,
        "org_type": t.org_type,
        "regulator": t.regulator,
        "asset_size_band": t.asset_size_band,
        "tenant_profile": dict(t.tenant_profile or {}),
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }


@bp.get("/settings/tenant")
@require_auth
def get_tenant() -> tuple[Response, int]:
    """Return the tenant context — basics + profile."""
    auth = g.auth
    with session_scope() as session:
        t = session.get(Tenant, auth.tenant)
        if t is None:
            return jsonify({"error": "tenant not found"}), 404
        return jsonify(_tenant_dict(t)), 200


@bp.patch("/settings/tenant")
@require_admin
def patch_tenant() -> tuple[Response, int]:
    """Partial update. Body keys map to two storage locations:

    - ``name``, ``org_type``, ``regulator``, ``asset_size_band`` →
      organization columns.
    - ``tenant_profile`` → JSON on the organization row. Top-level keys
      validated against ``PROFILE_KEYS``; values are pass-through.
    """
    auth = g.auth
    body = cast(dict[str, Any], request.get_json(silent=True) or {})

    with session_scope() as session:
        t = session.get(Tenant, auth.tenant)
        if t is None:
            return jsonify({"error": "tenant not found"}), 404

        if "name" in body:
            name = (body.get("name") or "").strip()
            if not name:
                return jsonify({"error": "name cannot be empty"}), 400
            t.name = name

        if "org_type" in body:
            if body["org_type"] not in VALID_ORG_TYPES:
                return jsonify({"error": f"invalid org_type; one of {VALID_ORG_TYPES}"}), 400
            t.org_type = body["org_type"]

        if "regulator" in body:
            v = body["regulator"]
            if v is not None and v not in VALID_REGULATORS:
                return jsonify({"error": f"invalid regulator; one of {VALID_REGULATORS}"}), 400
            t.regulator = v

        if "asset_size_band" in body:
            v = body["asset_size_band"]
            if v is not None and v not in VALID_ASSET_BANDS:
                return jsonify(
                    {"error": f"invalid asset_size_band; one of {VALID_ASSET_BANDS}"}
                ), 400
            t.asset_size_band = v

        if "tenant_profile" in body:
            profile = body["tenant_profile"]
            if not isinstance(profile, dict):
                return jsonify({"error": "tenant_profile must be an object"}), 400
            unknown = set(profile.keys()) - PROFILE_KEYS
            if unknown:
                return (
                    jsonify(
                        {
                            "error": "unknown tenant_profile keys",
                            "unknown_keys": sorted(unknown),
                            "allowed": sorted(PROFILE_KEYS),
                        }
                    ),
                    400,
                )
            month = profile.get("fiscal_year_start_month")
            if month is not None and (not isinstance(month, int) or not 1 <= month <= 12):
                return jsonify({"error": "fiscal_year_start_month must be an integer 1-12"}), 400
            merged = dict(t.tenant_profile or {})
            merged.update(profile)
            t.tenant_profile = merged

        t.updated_at = datetime.now(UTC)
        session.flush()
        return jsonify(_tenant_dict(t)), 200
