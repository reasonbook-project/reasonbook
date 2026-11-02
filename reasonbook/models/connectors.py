# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ORM models for the connector registry.

See migration 0045_connectors.py for column-level documentation.

Connectors are shared federal-system data sources (USASpending,
eRA Commons, SAM exclusions, etc.). One connector typically feeds
multiple workflows — it's configured once at /settings/connectors
and run on a schedule.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class Connector(Base):
    __tablename__ = "connectors"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    source_description: Mapped[str] = mapped_column(Text(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="connected", server_default=text("'connected'"))

    # Config
    filter_label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schedule_label: Mapped[str | None] = mapped_column(Text(), nullable=True)

    # Denormalized last-run snapshot
    last_sync_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_sync_record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_window_start: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    last_window_end: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    next_sync_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Integrity snapshot
    integrity_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    integrity_verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Workflows fed by this connector
    feeds_workflow_ids: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )

    # Audit
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )


class ConnectorRun(Base):
    __tablename__ = "connector_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_type: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress", server_default=text("'in_progress'"))
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    completed_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    filters_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    window_start: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    window_end: Mapped[datetime.date | None] = mapped_column(Date, nullable=True)
    record_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_chain_head: Mapped[str | None] = mapped_column(String(64), nullable=True)
