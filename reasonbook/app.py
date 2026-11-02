# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Flask application factory."""

from __future__ import annotations

import logging
import secrets
from pathlib import Path

from flask import Flask, Response, send_from_directory
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from reasonbook.config import Settings, get_settings
from reasonbook.logging import configure_logging

log = logging.getLogger(__name__)

# Built SPA assets are copied here by the Docker image build
# (web/dist -> reasonbook/static/web). Absent during `flask run` dev,
# where Vite serves the frontend on its own port.
_STATIC_WEB = Path(__file__).resolve().parent / "static" / "web"


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, format_=settings.log_format)

    _ensure_secret(settings)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["SETTINGS"] = settings

    # Trust one proxy layer (X-Forwarded-For/Proto/Host) so request.remote_addr
    # is the real client IP behind a single reverse proxy. Depth 1 only.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[method-assign]

    CORS(
        app,
        resources={r"/api/*": {"origins": settings.cors_origin_list}},
        supports_credentials=True,
    )

    _init_semantic_layer(settings)
    _register_blueprints(app)
    _register_spa(app)

    if settings.run_scheduler and not settings.testing:
        from reasonbook.scheduler import start_scheduler

        start_scheduler()

    return app


def _ensure_secret(settings: Settings) -> None:
    """Fail fast in production when the signing secret is unset.

    In development/testing a random ephemeral secret is generated (never a
    committed default) so `flask run` works; sessions won't survive a
    restart in that mode, which is fine for local use.
    """
    if settings.secret_key:
        return
    if settings.flask_env == "production":
        raise RuntimeError(
            "REASONBOOK_SECRET_KEY is not set. Reasonbook refuses to start in "
            "production without a signing secret. Generate one with "
            "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
        )
    ephemeral = secrets.token_urlsafe(48)
    object.__setattr__(settings, "secret_key", ephemeral)
    log.warning(
        "REASONBOOK_SECRET_KEY unset — generated an ephemeral dev secret "
        "(sessions will not survive a restart; never use this in production)."
    )


def _register_blueprints(app: Flask) -> None:
    from reasonbook.api.admin import bp as admin_bp
    from reasonbook.api.alerts import bp as alerts_bp
    from reasonbook.api.archetypes import bp as archetypes_bp
    from reasonbook.api.auth import bp as auth_bp
    from reasonbook.api.catalog import bp as catalog_bp
    from reasonbook.api.connectors import bp as connectors_bp
    from reasonbook.api.control_points import bp as control_points_bp
    from reasonbook.api.dashboard import bp as dashboard_bp
    from reasonbook.api.decisions import bp as decisions_bp
    from reasonbook.api.health import bp as health_bp
    from reasonbook.api.integrity import bp as integrity_bp
    from reasonbook.api.matters import bp as matters_bp
    from reasonbook.api.oversight import bp as oversight_bp
    from reasonbook.api.programs import bp as programs_bp
    from reasonbook.api.registry import bp as registry_bp
    from reasonbook.api.settings import bp as settings_bp
    from reasonbook.api.users import bp as users_bp
    from reasonbook.api.workflows import bp as workflows_bp

    for bp in (
        health_bp,
        auth_bp,
        admin_bp,
        workflows_bp,
        archetypes_bp,
        programs_bp,
        catalog_bp,
        connectors_bp,
        alerts_bp,
        decisions_bp,
        matters_bp,
        control_points_bp,
        settings_bp,
        users_bp,
        oversight_bp,
        dashboard_bp,
        integrity_bp,
        registry_bp,
    ):
        app.register_blueprint(bp, url_prefix="/api")


def _register_spa(app: Flask) -> None:
    """Serve the built React SPA for all non-API routes.

    Real asset paths are served from disk; everything else falls back to
    index.html so client-side routing works on deep links. A no-op when
    the built bundle is absent (dev: Vite serves the frontend separately).
    """

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str) -> Response | tuple[str, int]:
        if path.startswith("api/"):
            return "Not found", 404
        if not _STATIC_WEB.is_dir():
            return (
                "Reasonbook API is running. The web UI bundle is not present in "
                "this process (run the frontend with `pnpm dev`, or build the "
                "Docker image which bundles it).",
                200,
            )
        candidate = _STATIC_WEB / path
        if path and candidate.is_file():
            return send_from_directory(_STATIC_WEB, path)
        return send_from_directory(_STATIC_WEB, "index.html")


def _init_semantic_layer(settings: Settings) -> None:
    """Load workflow YAMLs and sync the decision_types registry.

    Skipped when REASONBOOK_SKIP_SEMANTIC_BOOT=true (used by tests that
    don't need workflows loaded, e.g. the health-endpoint test).
    """
    if settings.skip_semantic_boot:
        return

    from reasonbook.semantic.engine import init_engine
    from reasonbook.semantic.registry import sync_decision_types

    engine = init_engine()

    # Registry sync is best-effort during boot — if the DB isn't reachable
    # we still want the app to come up so /api/health can respond.
    try:
        sync_decision_types(engine)
    except Exception as exc:  # noqa: BLE001
        log.warning("decision_types sync skipped: %s", exc)
