# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Identity-resolution dispute model.

Sits alongside Matter (Matters) and the promoted-alert Decisions
(Reviews) as the third first-class Register entity. A Dispute captures
a "who is this?" disagreement between two candidate identities that
have to be reconciled before an award moves forward.

See migration ``0047_disputes.py`` for the column-level documentation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class Dispute(Base):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'resolved_same', 'resolved_different', "
            "'manual_override', 'withdrawn')",
            name="chk_disputes_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )

    # The name at the heart of the disagreement. Both candidates
    # supposedly refer to something spelled roughly like this.
    subject_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Free-shape provenance for each side (SAM.gov row, LEIE row,
    # USASpending recipient, etc.). Analyst UI renders whatever's
    # present.
    candidate_a: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    candidate_b: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text("'open'")
    )
    resolution: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resolution_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    opened_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional links back to related matter / alert. Set when the
    # dispute originated from an inline check on a specific matter
    # or a specific alert investigation.
    related_matter_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("matters.id", ondelete="SET NULL"),
        nullable=True,
    )
    related_alert_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("alerts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Set when the dispute is answered — points at the Decision the
    # resolve endpoint minted. Analyst navigates from the dispute
    # detail to the decision via this link.
    linked_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="SET NULL"),
        nullable=True,
    )


__all__ = ["Dispute"]
