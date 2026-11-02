# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ORM model for the federal agency catalog.

See migration ``0041_agency_catalog.py`` for column-level documentation
and ``scripts/import_usaspending.py`` for the loader. The eventual real
connector (P25 per ADR-10) writes here too.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class AgencyCatalog(Base):
    __tablename__ = "agency_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="usaspending", server_default=text("'usaspending'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["AgencyCatalog"]
