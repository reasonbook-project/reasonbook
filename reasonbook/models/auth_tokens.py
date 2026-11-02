# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Short-lived single-use auth tokens (DB-backed).

Email-verification, password-reset, and account-unlock magic links are
one-time tokens. In v1.0 they live in the database (no external cache) —
one small table with a TTL column. Only the SHA-256 hash of the token is
stored, so a database read never exposes a usable link.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    # SHA-256 hex digest of the random token — the raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    # 'verify' | 'reset' | 'unlock'
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(GUID, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


__all__ = ["AuthToken"]
