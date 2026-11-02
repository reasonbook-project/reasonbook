# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Pytest fixtures.

The suite runs on SQLite by default (a temp file), and on PostgreSQL when
``REASONBOOK_DATABASE_URL`` points at one (CI runs both). Test-only
environment defaults are set here BEFORE any ``reasonbook`` module is
imported, so the cached settings and the module-level engine pick them up.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from typing import Any

# --- Test environment defaults (must be set before importing reasonbook) ---
os.environ.setdefault("REASONBOOK_FLASK_ENV", "testing")
os.environ.setdefault("REASONBOOK_SECRET_KEY", "test-secret-not-for-production")
os.environ.setdefault("REASONBOOK_JWT_ISSUER", "reasonbook")
os.environ.setdefault("REASONBOOK_RUN_SCHEDULER", "false")
# Fixed, test-only seed password (no shipped default lives in code).
os.environ.setdefault("REASONBOOK_SEED_PASSWORD", "test-seed-pw-1234")
if "REASONBOOK_DATABASE_URL" not in os.environ and "DATABASE_URL" not in os.environ:
    _TMP_DB = os.path.join(tempfile.gettempdir(), "reasonbook-test.db")
    os.environ["REASONBOOK_DATABASE_URL"] = f"sqlite:///{_TMP_DB}"

import pytest  # noqa: E402
from flask import Flask  # noqa: E402
from flask.testing import FlaskClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.engine import Connection, Engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from reasonbook.app import create_app  # noqa: E402
from reasonbook.config import get_settings  # noqa: E402
from reasonbook.db import engine as app_engine  # noqa: E402

# Shared, fixed test-only seed password (demo accounts are non-production).
DEMO_PASSWORD = os.environ["REASONBOOK_SEED_PASSWORD"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Run ``clean_db``-using tests LAST — they reset the schema and would
    nuke the session-scoped seed the other tests depend on."""
    items.sort(key=lambda item: 1 if "clean_db" in getattr(item, "fixturenames", ()) else 0)


@pytest.fixture()
def app() -> Iterator[Flask]:
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture()
def demo_password() -> str:
    return DEMO_PASSWORD


@pytest.fixture()
def captured_login_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture ``send_email`` calls from the auth endpoints."""
    sent: list[dict[str, Any]] = []

    def fake_send_email(
        *, to_addr: str, subject: str, body: str, reply_to: str | None = None
    ) -> bool:
        sent.append({"to": to_addr, "subject": subject, "body": body})
        return True

    monkeypatch.setattr("reasonbook.api.auth.send_email", fake_send_email)
    return sent


def _alembic_upgrade_head() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    command.upgrade(cfg, "head")


def _reset_database() -> None:
    """Reset to a virgin schema, then re-run migrations (portable)."""
    settings = get_settings()
    if settings.is_postgres:
        with app_engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS platform CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    else:
        # SQLite: foreign_keys=ON (plus the decisions<->matters cycle) makes
        # ordered DROP TABLE fail, so just delete the temp DB file instead.
        app_engine.dispose()
        path = settings.database_url.replace("sqlite:///", "")
        if path and path != ":memory:":
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(path + suffix)
                except FileNotFoundError:
                    pass
    _alembic_upgrade_head()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    """Migrate the schema once per session so every test starts current."""
    _reset_database()
    yield app_engine
    app_engine.dispose()


@pytest.fixture()
def clean_db(db_engine: Engine) -> Iterator[Engine]:
    """Virgin schema (migrations applied, no seed) for DDL/seed tests."""
    _reset_database()
    yield db_engine


@pytest.fixture(scope="session")
def db_seeded(db_engine: Engine) -> Iterator[Engine]:
    """Session-scoped: seed once (schema already migrated) + init semantics."""
    from reasonbook.semantic.engine import init_engine, reset_engine
    from scripts.seed_dev import seed as _seed

    _seed()
    reset_engine()
    init_engine()
    yield db_engine


@pytest.fixture()
def seeded(db_seeded: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    """Function-scoped seeded engine with per-test transactional rollback.

    Binds ``reasonbook.db.SessionLocal`` to a connection running an outer
    transaction; each test's writes become SAVEPOINTs that roll back at
    teardown, leaving the seeded baseline intact.
    """
    connection: Connection = db_seeded.connect()
    outer_tx = connection.begin()

    test_sessionmaker = sessionmaker(
        bind=connection,
        autoflush=False,
        autocommit=False,
        future=True,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr("reasonbook.db.SessionLocal", test_sessionmaker)

    try:
        yield db_seeded
    finally:
        outer_tx.rollback()
        connection.close()
