# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Alembic environment.

Reads the database URL from Reasonbook settings and uses
``reasonbook.db.Base`` metadata for autogeneration. The metadata lives in
the logical ``platform`` schema; on SQLite a schema_translate_map rewrites
it to None so the same migration runs flat. CREATE SCHEMA / the named
version-table schema apply only on PostgreSQL.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from reasonbook import models  # noqa: F401  -- register all ORM models on Base.metadata
from reasonbook.config import get_settings
from reasonbook.db import SCHEMA_NAME, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

_IS_PG = settings.is_postgres
# On PostgreSQL the tables live in a real ``platform`` schema; on SQLite we
# translate that logical schema to None (flat tables).
_SCHEMA_TRANSLATE = None if _IS_PG else {SCHEMA_NAME: None}
_VERSION_TABLE_SCHEMA = SCHEMA_NAME if _IS_PG else None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_VERSION_TABLE_SCHEMA,
        include_schemas=_IS_PG,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        if _SCHEMA_TRANSLATE is not None:
            connection = connection.execution_options(schema_translate_map=_SCHEMA_TRANSLATE)
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=_VERSION_TABLE_SCHEMA,
            include_schemas=_IS_PG,
        )
        with context.begin_transaction():
            if _IS_PG:
                context.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
