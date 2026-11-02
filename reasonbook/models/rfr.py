# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Request-For-Response (RFR) ORM model.

The record of "federal PM asked party X for a response on matter Y."
Sits alongside Matter, Alert, and Dispute as a first-class register
entity — see EXTERNAL-PARTY-ACCESS-SPEC §4, §6 and
backlog/awaiting-recipient-stage-band.md.

Column-level docs live on migration ``0055_requests_for_response.py``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class RequestForResponse(Base):
    __tablename__ = "requests_for_response"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved', 'superseded')",
            name="chk_rfr_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    # Public-facing id used in narration + surfaces + commitment refs
    # (e.g. "RFR-2026-07-08-4291"). Unique.
    rfr_number: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    matter_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("matters.id", ondelete="CASCADE"),
        nullable=False,
    )
    matter_node_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("matter_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    originating_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="SET NULL"),
        nullable=True,
    )

    target_party_name: Mapped[str] = mapped_column(Text, nullable=False)

    prompt_type: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_body: Mapped[str] = mapped_column(Text, nullable=False)

    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'open'")
    )
    resolved_by_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["RequestForResponse"]
