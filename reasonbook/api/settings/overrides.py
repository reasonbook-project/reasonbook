# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Override management — set, supersede, and read history.

Wraps the OverrideManager from `reasonbook.semantic.overrides`. Validation and
allowlist checks happen there; this layer is HTTP plumbing + admin gating.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from flask import Blueprint, Response, g, jsonify, request

from reasonbook.auth.decorators import require_admin
from reasonbook.models import AgencySemanticOverride
from reasonbook.semantic.engine import get_engine
from reasonbook.semantic.overrides import (
    OverrideError,
    get_override_history,
    set_override,
    supersede_override,
)

bp = Blueprint("settings_overrides", __name__)


def _row(o: AgencySemanticOverride) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "tenant_id": o.tenant_id,
        "workflow_id": o.workflow_id,
        "config_key": o.config_key,
        "config_value": o.config_value,
        "modified_by": str(o.modified_by) if o.modified_by else None,
        "modified_at": o.modified_at.isoformat() if o.modified_at else None,
        "approved_by": str(o.approved_by) if o.approved_by else None,
        "approved_at": o.approved_at.isoformat() if o.approved_at else None,
        "change_note": o.change_note,
        "superseded_at": o.superseded_at.isoformat() if o.superseded_at else None,
    }


def _check_workflow(workflow_id: str) -> tuple[Response, int] | None:
    if not get_engine().has(workflow_id):
        return jsonify({"error": "unknown workflow_id"}), 404
    return None


@bp.get("/settings/workflows/<workflow_id>/config")
@require_admin
def workflow_config(workflow_id: str) -> tuple[Response, int]:
    """Return the merged config (base + tenant overrides) plus the
    overridable_keys allowlist so the UI can build the right input controls."""
    err = _check_workflow(workflow_id)
    if err is not None:
        return err
    auth = g.auth
    engine = get_engine()
    merged = engine.merged_config_for(auth.tenant, workflow_id)
    cfg = engine.get_config(workflow_id)
    return (
        jsonify({"config": merged, "overridable_keys": cfg.overridable_keys}),
        200,
    )


@bp.post("/settings/workflows/<workflow_id>/overrides")
@require_admin
def set_override_endpoint(workflow_id: str) -> tuple[Response, int]:
    err = _check_workflow(workflow_id)
    if err is not None:
        return err
    auth = g.auth
    body = cast(dict[str, Any], request.get_json(silent=True) or {})

    config_key = body.get("config_key")
    config_value = body.get("config_value")
    change_note = body.get("change_note")
    if not config_key or "config_value" not in body:
        return jsonify({"error": "config_key and config_value required"}), 400

    try:
        row = set_override(
            tenant_id=auth.tenant,
            workflow_id=workflow_id,
            config_key=config_key,
            config_value=config_value,
            modified_by=uuid.UUID(auth.sub),
            change_note=change_note,
        )
    except OverrideError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(_row(row)), 201


@bp.delete("/settings/workflows/<workflow_id>/overrides/<config_key>")
@require_admin
def supersede_override_endpoint(workflow_id: str, config_key: str) -> tuple[Response, int]:
    err = _check_workflow(workflow_id)
    if err is not None:
        return err
    auth = g.auth
    cleared = supersede_override(
        tenant_id=auth.tenant, workflow_id=workflow_id, config_key=config_key
    )
    if not cleared:
        return jsonify({"error": "no current override for that key"}), 404
    return jsonify({"status": "superseded"}), 200


@bp.get("/settings/workflows/<workflow_id>/overrides/history")
@require_admin
def history(workflow_id: str) -> tuple[Response, int]:
    err = _check_workflow(workflow_id)
    if err is not None:
        return err
    auth = g.auth
    rows = get_override_history(tenant_id=auth.tenant, workflow_id=workflow_id)
    return jsonify({"items": [_row(r) for r in rows]}), 200
