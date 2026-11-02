# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy engine and session setup (dialect-portable).

Reasonbook runs on SQLite by default and on PostgreSQL when
``REASONBOOK_DATABASE_URL`` points at one. The two differences handled
here:

- **Schema.** On PostgreSQL the tables live in a named ``platform``
  schema; SQLite has no schemas, so tables are flat. ``Base.metadata``
  carries ``schema=settings.db_schema`` ("platform" or ``None``), which
  makes every model's unqualified ForeignKey (``ForeignKey("users.id")``)
  resolve under the right schema on each dialect. Raw SQL uses
  :func:`schema_prefix` for the same reason.
- **Connection setup.** SQLite needs WAL + a busy timeout so overlapping
  writers queue instead of raising "database is locked"; PostgreSQL wants
  pool pre-ping / recycle. Both are wired on the engine below.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import MetaData, Uuid, create_engine, event
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

from reasonbook.config import get_settings

_settings = get_settings()


class GUID(TypeDecorator):
    """UUID column that accepts both ``uuid.UUID`` and string values.

    Wraps SQLAlchemy's generic ``Uuid`` (native UUID on PostgreSQL,
    CHAR(32) hex on SQLite) but coerces string inputs to ``uuid.UUID``
    first. Many call sites query by a string id (e.g. a JWT ``sub``
    claim); the native-UUID path on PostgreSQL tolerates that, but the
    character-storage path on SQLite requires a real UUID object. This
    keeps both dialects working from one column type.
    """

    impl = Uuid
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is not None and not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        return value

# SQLite cannot bind a uuid.UUID object in raw text() SQL (unlike psycopg).
# SQLAlchemy's Uuid type stores UUIDs as 32-char hex on SQLite; register the
# same adaptation globally so raw SQL that binds a UUID (e.g. the per-matter
# integrity endpoint, alert promotion) produces values matching ORM storage.
sqlite3.register_adapter(uuid.UUID, lambda u: u.hex)


# The ORM metadata always lives in a logical ``platform`` schema. On
# PostgreSQL that is a real named schema; on SQLite (which has no schemas)
# the engine's schema_translate_map rewrites ``platform`` -> None so the
# same models and the same migration render flat tables. See _make_engine.
SCHEMA_NAME = "platform"


class Base(DeclarativeBase):
    """Declarative base for all ORM models.

    Metadata is pinned to the logical ``platform`` schema for both
    dialects; the engine translates it away on SQLite (see
    :func:`_make_engine`). Models therefore use unqualified ForeignKey
    strings (``ForeignKey("users.id")``) which resolve under this schema.
    """

    metadata = MetaData(schema=SCHEMA_NAME)


def schema_prefix() -> str:
    """``"platform."`` on PostgreSQL, ``""`` on SQLite — for raw SQL only.

    SQLAlchemy's schema_translate_map covers ORM/Core constructs but NOT
    ``text()`` strings, so raw SQL interpolates this prefix instead.
    """
    return f"{SCHEMA_NAME}." if get_settings().is_postgres else ""


def _make_engine() -> Engine:
    settings = get_settings()
    if settings.is_postgres:
        # pool_pre_ping catches connections invalidated since checkout;
        # pool_recycle retires them after 5 minutes so managed-DB idle kills
        # don't surface as mid-request errors.
        return create_engine(
            settings.database_url,
            future=True,
            pool_pre_ping=True,
            pool_recycle=300,
        )
    # SQLite. schema_translate_map rewrites the logical ``platform`` schema
    # to None (flat tables). check_same_thread=False lets the APScheduler
    # thread share the engine; WAL + busy_timeout are applied per-connection.
    return create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False},
        execution_options={"schema_translate_map": {SCHEMA_NAME: None}},
    )


engine = _make_engine()


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_connection: object, _record: object) -> None:
    """Apply WAL + busy_timeout on every new SQLite connection.

    WAL lets readers run while a single writer holds the write lock;
    busy_timeout makes a blocked writer wait (and retry internally) for up
    to 5s instead of immediately raising "database is locked". Together
    they make SQLite safe for a small team plus the 5-minute ingestion
    batch (see DEPLOY.md, single-writer limit).
    """
    if engine.dialect.name != "sqlite":
        return
    # Compatibility shim: PostgreSQL's gen_random_uuid() used by some raw SQL.
    # Return 32-char hex to match how the Uuid type stores UUIDs on SQLite.
    dbapi_connection.create_function(  # type: ignore[attr-defined]
        "gen_random_uuid", 0, lambda: uuid.uuid4().hex
    )
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
