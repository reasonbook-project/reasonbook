# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Health endpoint."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from reasonbook import __version__

bp = Blueprint("health", __name__)


@bp.get("/health")
def health() -> tuple[Response, int]:
    return jsonify({"status": "healthy", "version": __version__}), 200
