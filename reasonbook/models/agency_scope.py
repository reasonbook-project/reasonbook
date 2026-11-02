# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Agency-scope model — hierarchical agency tree + cross-agency grants.

Distinct from ``AgencyCatalog`` (``dp/models/agencies.py``), which
catalogs awarding-agency **display labels** pulled from USAspending.
This module defines the **scope-carrier** agencies that DP users and
decisions belong to.

See migration ``0046_agencies.py`` for the full column-level
documentation and the DG-substrate cleanup narrative.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from reasonbook.db import GUID, Base


class Agency(Base):
    """A federal agency in the scope hierarchy.

    ``parent_agency_id`` is nullable — top-level cabinet departments
    have no parent. ``depth`` denormalises the level (0 = cabinet,
    1 = bureau / operating division, 2 = program office). Applications
    typically read ``depth`` for display filtering; the true parent
    walk uses ``parent_agency_id``.
    """

    __tablename__ = "agencies"
    __table_args__ = (
        CheckConstraint("depth >= 0 AND depth <= 5", name="chk_agencies_depth"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agency_slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    short_name: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Self-referential relationships. `children` walks down; `parent`
    # walks up. Both are lazy — most callers use the queries below
    # via the helper in `dp/decisions/scope.py`.
    parent: Mapped[Agency | None] = relationship(
        "Agency",
        remote_side=[id],
        back_populates="children",
        lazy="select",
    )
    children: Mapped[list[Agency]] = relationship(
        "Agency",
        back_populates="parent",
        lazy="select",
    )


class UserAgencyScope(Base):
    """Explicit cross-agency grant.

    A user's *primary* agency lives on ``users.agency_id``. This table
    captures any additional agencies the user is granted read on beyond
    their primary — e.g., an OIG examiner working across HHS, HUD, and
    DoD.

    ``includes_descendants`` opts a grant into the sub-agency cascade:
    a HHS grant with the flag covers NIH and NIH-OER too. Grants
    without the flag cover only the named agency (useful when an
    examiner has read on a single program office within a bureau
    without seeing the whole department).

    Append-only — revocations set ``revoked_at`` rather than delete
    the row so the audit chain preserves who saw what and when.
    """

    __tablename__ = "user_agency_scopes"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    agency_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    includes_descendants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    granted_by: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["Agency", "UserAgencyScope"]
