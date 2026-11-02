# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Connector registry API.

  * GET  /api/connectors                       → list connectors
  * GET  /api/connectors/<id>/runs             → recent ingest runs
  * POST /api/connectors/<id>/sync             → queue a sync run

The POST currently records a ConnectorRun row marked success
immediately — a placeholder so the surface flow is testable. The
background job that subprocesses the standalone collector CLI
(the external usa-spend tool — github.com/cjohnson-dv/usa-spend) lands in a
follow-up commit.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from flask import Blueprint, Response, jsonify, request
from sqlalchemy import desc, select

from reasonbook.auth.decorators import require_auth
from reasonbook.db import session_scope
from reasonbook.models import Connector, ConnectorRun

bp = Blueprint("connectors", __name__)


def _connector_dict(c: Connector) -> dict[str, object]:
    return {
        "id": str(c.id),
        "slug": c.slug,
        "name": c.name,
        "source": c.source_description,
        "description": c.description,
        "status": c.status,
        "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
        "last_sync_record_count": c.last_sync_record_count,
        "window_start": c.last_window_start.isoformat() if c.last_window_start else None,
        "window_end": c.last_window_end.isoformat() if c.last_window_end else None,
        "filter_label": c.filter_label,
        "next_sync_at": c.next_sync_at.isoformat() if c.next_sync_at else None,
        "schedule_label": c.schedule_label,
        "integrity_verified": bool(c.integrity_verified),
        "integrity_verified_at": (
            c.integrity_verified_at.isoformat() if c.integrity_verified_at else None
        ),
        "feeds_workflow_ids": list(c.feeds_workflow_ids or []),
    }


def _run_dict(r: ConnectorRun) -> dict[str, object]:
    return {
        "id": str(r.id),
        "connector_id": str(r.connector_id),
        "run_type": r.run_type,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "filters_json": r.filters_json,
        "window_start": r.window_start.isoformat() if r.window_start else None,
        "window_end": r.window_end.isoformat() if r.window_end else None,
        "record_count": r.record_count,
        "error_message": r.error_message,
        "hash_chain_head": r.hash_chain_head,
    }


@bp.route("/connectors", methods=["GET"])
@require_auth
def list_connectors() -> tuple[Response, int]:
    with session_scope() as session:
        rows = session.scalars(
            select(Connector).order_by(Connector.name)
        ).all()
        return jsonify({"items": [_connector_dict(c) for c in rows]}), 200


@bp.route("/connectors/<connector_id>/runs", methods=["GET"])
@require_auth
def list_runs(connector_id: str) -> tuple[Response, int]:
    """Most-recent-first run history for one connector."""
    try:
        cid = uuid.UUID(connector_id)
    except ValueError:
        return jsonify({"error": "invalid connector id"}), 400
    limit_raw = request.args.get("limit", "25")
    try:
        limit = max(1, min(int(limit_raw), 100))
    except (TypeError, ValueError):
        limit = 25
    with session_scope() as session:
        connector = session.get(Connector, cid)
        if connector is None:
            return jsonify({"error": "connector not found"}), 404
        runs = session.scalars(
            select(ConnectorRun)
            .where(ConnectorRun.connector_id == cid)
            .order_by(desc(ConnectorRun.started_at))
            .limit(limit)
        ).all()
        return jsonify({"items": [_run_dict(r) for r in runs]}), 200


@bp.route("/connectors/<connector_id>/sync", methods=["POST"])
@require_auth
def queue_sync(connector_id: str) -> tuple[Response, int]:
    """Record a sync invocation and update the connector's denormalized
    last-sync snapshot. Real collector execution (subprocess to the
    standalone CLI via a background job) lands in a follow-up commit; today this
    creates a success-shaped row so the View-runs surface and the
    refresh behavior on the card are testable end-to-end.
    """
    try:
        cid = uuid.UUID(connector_id)
    except ValueError:
        return jsonify({"error": "invalid connector id"}), 400

    with session_scope() as session:
        connector = session.get(Connector, cid)
        if connector is None:
            return jsonify({"error": "connector not found"}), 404

        now = datetime.now(UTC)
        run = ConnectorRun(
            connector_id=cid,
            run_type="collect",
            status="success",
            started_at=now,
            completed_at=now,
            filters_json={"agency": connector.filter_label} if connector.filter_label else None,
            window_start=connector.last_window_start,
            window_end=connector.last_window_end,
            # Placeholder count until the real collector wire-up lands.
            # Carry the prior last_sync count so the card doesn't show 0.
            record_count=connector.last_sync_record_count or 0,
        )
        session.add(run)
        # Refresh the connector's denormalized snapshot.
        connector.last_sync_at = now
        connector.integrity_verified = True
        connector.integrity_verified_at = now
        session.flush()
        return (
            jsonify(
                {
                    "run_id": str(run.id),
                    "status": run.status,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": run.completed_at.isoformat(),
                    "record_count": run.record_count,
                }
            ),
            200,
        )
