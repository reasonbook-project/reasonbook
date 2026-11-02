# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tenant administration endpoints — users, overrides, tenant config.

Entitlements endpoints retired in the DG-substrate cleanup: DP is
single-tenant (US federal government) with no per-workflow gating.
"""

from flask import Blueprint

from reasonbook.api.settings import overrides, tenant, users

bp = Blueprint("settings", __name__)
bp.register_blueprint(users.bp, url_prefix="")
bp.register_blueprint(overrides.bp, url_prefix="")
bp.register_blueprint(tenant.bp, url_prefix="")
