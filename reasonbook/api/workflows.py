# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Workflow API — list entitled workflows, serve merged tenant config,
and handle Sprint 3 manual uploads."""

from __future__ import annotations

import csv
import io
import logging

from flask import Blueprint, Response, g, jsonify, make_response, request

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.semantic.engine import get_engine
from reasonbook.semantic.schema import UploadSchema
from reasonbook.uploads import (
    parse_csv,
    parse_json,
    validate_rows,
    write_rows,
)
from reasonbook.uploads.writer import WriterError

log = logging.getLogger(__name__)

bp = Blueprint("workflows", __name__)


@bp.get("/workflows")
@require_auth
def list_workflows() -> tuple[Response, int]:
    """All loaded workflows. Single-tenant / federal-integrity DP has no
    per-tenant entitlement gating anymore — every authenticated user sees
    every registered workflow."""
    engine = get_engine()
    return jsonify({"workflows": engine.list_summaries()}), 200


@bp.get("/workflows/<workflow_id>/config")
@require_auth
def get_workflow_config(workflow_id: str) -> tuple[Response, int]:
    """Full merged config (base + tenant overrides) for one workflow."""
    engine = get_engine()
    if not engine.has(workflow_id):
        return jsonify({"error": "unknown workflow", "workflow_id": workflow_id}), 404
    merged = engine.merged_config_for(g.auth.tenant, workflow_id)
    return jsonify(merged), 200


# ---------------------------------------------------------------------------
# Phase 14 — Schema Explorer export
#
# Same merged config the explorer renders, downloadable as YAML or JSON for
# audit / review / sharing. Read-only — no write side. Auditors and admins
# pasting the config to email or to a Linear ticket is the primary use.
# ---------------------------------------------------------------------------


@bp.get("/workflows/<workflow_id>/schema/export")
@require_auth
def schema_export(workflow_id: str) -> Response | tuple[Response, int]:
    """Download the workflow's merged config as ``yaml`` or ``json``."""
    fmt = request.args.get("format", "yaml").lower()
    if fmt not in {"yaml", "json"}:
        return jsonify({"error": "format must be 'yaml' or 'json'"}), 400

    engine = get_engine()
    if not engine.has(workflow_id):
        return jsonify({"error": "unknown workflow", "workflow_id": workflow_id}), 404

    merged = engine.merged_config_for(g.auth.tenant, workflow_id)

    if fmt == "json":
        import json as _json

        body = _json.dumps(merged, indent=2, default=str)
        content_type = "application/json"
        ext = "json"
    else:
        import yaml as _yaml

        body = _yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)
        content_type = "application/yaml"
        ext = "yaml"

    resp = make_response(body)
    resp.headers["Content-Type"] = f"{content_type}; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{workflow_id}-config.{ext}"'
    return resp


# ---------------------------------------------------------------------------
# Semantic Layer Catalog — aggregated multi-workflow export
#
# Companion to the per-workflow schema explorer. The catalog surface lets
# auditors / admins see the institutional schema in one place; this endpoint
# ships the corresponding download. Wraps each workflow's merged config in a
# top-level `catalog: {version, workflows: [...]}` structure so the file
# reads as a single artifact instead of a multi-document pile.
# ---------------------------------------------------------------------------

# Catalog schema version. Bump when the wrapper structure changes (not when
# individual workflow YAMLs change — those carry their own per-workflow
# version field). v1.0 is the frozen v1 schema shape per the spec.
_CATALOG_VERSION = "v1.0"


@bp.get("/catalog/export")
@require_auth
def catalog_export() -> Response | tuple[Response, int]:
    """Download an aggregated catalog of selected workflows as ``yaml``
    or ``json``.

    Query params:
      - ``format`` — ``yaml`` (default) or ``json``
      - ``workflow_ids`` — comma-separated workflow ids to include. Omit
        for all the user's entitled workflows.

    Always restricted to the user's entitled set — passing an unentitled
    or unknown workflow id silently drops it rather than 403'ing the
    whole request, since the spec describes catalog as a discovery
    surface and partial views are expected.
    """
    fmt = request.args.get("format", "yaml").lower()
    if fmt not in {"yaml", "json"}:
        return jsonify({"error": "format must be 'yaml' or 'json'"}), 400

    engine = get_engine()
    requested_ids: list[str] | None = None
    raw = request.args.get("workflow_ids")
    if raw is not None and raw.strip():
        requested_ids = [s.strip() for s in raw.split(",") if s.strip()]

    all_ids = [s["id"] for s in engine.list_summaries()]
    if requested_ids is not None:
        # Preserve the request order so the export matches the on-screen
        # filter selection order — predictable when the file is reviewed.
        included = [wid for wid in requested_ids if wid in all_ids]
    else:
        included = all_ids

    workflows: list[dict[str, object]] = []
    for wid in included:
        if not engine.has(wid):
            continue
        merged = engine.merged_config_for(g.auth.tenant, wid)
        workflows.append({"workflow_id": wid, "config": merged})

    catalog = {
        "catalog": {
            "version": _CATALOG_VERSION,
            "workflows": workflows,
        }
    }

    # Filename pattern per spec: reasonbook-catalog-{slug-or-all}-v{version}.{ext}
    if requested_ids is None or len(included) == len(all_ids):
        slug = "all"
    elif len(included) == 1:
        slug = included[0]
    else:
        slug = "selection"

    if fmt == "json":
        import json as _json

        body = _json.dumps(catalog, indent=2, default=str)
        content_type = "application/json"
        ext = "json"
    else:
        import yaml as _yaml

        body = _yaml.safe_dump(catalog, sort_keys=False, default_flow_style=False)
        content_type = "application/yaml"
        ext = "yaml"

    resp = make_response(body)
    resp.headers["Content-Type"] = f"{content_type}; charset=utf-8"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="reasonbook-catalog-{slug}-{_CATALOG_VERSION}.{ext}"'
    )
    return resp


# ---------------------------------------------------------------------------
# Sprint 3 — manual upload endpoints
# ---------------------------------------------------------------------------


def _resolve_upload_schema(
    workflow_id: str,
) -> tuple[Response, int] | UploadSchema:
    """Authority + entitlement gate, returns the parsed UploadSchema or an
    error tuple. Caller dispatches on the return type."""
    engine = get_engine()
    if not engine.has(workflow_id):
        return jsonify({"error": "unknown workflow", "workflow_id": workflow_id}), 404
    cfg = engine.get_config(workflow_id)
    if cfg.upload is None or not cfg.upload.enabled:
        return (
            jsonify({"error": "manual upload not configured for this workflow"}),
            404,
        )
    return cfg.upload


@bp.get("/workflows/<workflow_id>/upload/sample.csv")
@require_auth
def upload_sample(workflow_id: str) -> Response | tuple[Response, int]:
    """Generate a sample CSV with header + one example row pulled from the
    column ``example`` values. Drives the "Download sample" button."""
    resolved = _resolve_upload_schema(workflow_id)
    if isinstance(resolved, tuple):
        return resolved
    schema = resolved

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.name for c in schema.columns])
    writer.writerow(["" if c.example is None else c.example for c in schema.columns])

    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="{workflow_id}-upload-sample.csv"'
    return resp


@bp.post("/workflows/<workflow_id>/upload")
@require_auth
def upload(workflow_id: str) -> tuple[Response, int]:
    """Multipart upload — file in ``file`` form field. Validates against the
    workflow's UploadSchema, then writes rows directly into the workflow's
    local ``pipe_*`` staging table.

    Returns:
      200 with ``{rows_written, pipe_table}`` on success
      400 with ``{validation: {valid: false, errors: [...]}}`` if validation fails
      502 if the database write fails
    """
    resolved = _resolve_upload_schema(workflow_id)
    if isinstance(resolved, tuple):
        return resolved
    schema = resolved

    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400
    upload_file = request.files["file"]
    if not upload_file.filename:
        return jsonify({"error": "missing filename"}), 400

    filename = upload_file.filename.lower()
    try:
        if filename.endswith(".csv"):
            rows = parse_csv(upload_file.stream)
        elif filename.endswith(".json"):
            rows = parse_json(upload_file.stream)
        else:
            return (
                jsonify({"error": (f"unsupported format: {filename}. Accepted: {schema.formats}")}),
                400,
            )
    except ValueError as exc:
        return jsonify({"error": f"could not parse file: {exc}"}), 400

    result = validate_rows(rows, schema)
    if not result.is_valid:
        return jsonify({"validation": result.to_jsonable()}), 400

    try:
        with session_scope() as session:
            write_result = write_rows(
                session=session,
                rows=result.rows,
                schema=schema,
                tenant_id=g.auth.tenant,
            )
    except WriterError as exc:
        return jsonify({"error": str(exc)}), 502

    log.info(
        "upload tenant=%s workflow=%s rows=%d",
        g.auth.tenant,
        workflow_id,
        write_result.rows_written,
    )
    return (
        jsonify(
            {
                "rows_written": write_result.rows_written,
                "pipe_table": write_result.pipe_table,
            }
        ),
        200,
    )
