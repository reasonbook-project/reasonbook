# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""ORM model for the determination ledger.

One row per atomic archetype determination. Append-only — the promotion
service writes; nothing updates. The ``promoted`` /
``promoted_decision_id`` / ``promotion_trigger`` columns are set at
write time (every_case) or later by the promotion service when a
trigger fires (on_trigger). They are not mutated after that point —
"upgrading" a ledger row to a Decision means writing a new ledger row
that points at the new Decision, never mutating the original.

Role vs. ``decision_events`` (P06 resolution):
  * ``decision_events`` is the canonical lifecycle ledger. Every
    Decision's create/claim/finalize/outcome trail lives there. UI
    "Decision Detail" renders from this table.
  * ``determination_ledger`` (this table) is the complementary
    archetype-evaluation log: rule_version, basis_result, flow_refs,
    parent_ledger_id for appeals. It links to a promoted Decision via
    ``promoted_decision_id``; the lifecycle of that Decision is owned
    by ``decision_events``, not duplicated here.

  Promoted federal Decisions are routed through ``reasonbook.decisions.manager``
  (see ``scripts.seed_dev.make_federal_decision_factory``) so the trail
  is consistent regardless of write origin. See
  ``docs/architecture/_archive/reconcile/v3_0.md`` §3 for the original P1
  violation that this split addresses.

See migration 0033_determination_ledger.py for the full column-level
documentation; this file is the ORM mapping.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class DeterminationLedger(Base):
    __tablename__ = "determination_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    program_id: Mapped[str] = mapped_column(String(100), nullable=False)
    archetype_id: Mapped[str] = mapped_column(String(100), nullable=False)
    promotes: Mapped[str] = mapped_column(String(20), nullable=False)

    inputs: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    rule_version: Mapped[str | None] = mapped_column(String(50))
    basis_result: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    outcome: Mapped[str | None] = mapped_column(String(100))
    actor: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'")
    )
    flow_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, server_default=text("'[]'")
    )

    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    promoted_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", ondelete="SET NULL"),
    )
    promotion_trigger: Mapped[str | None] = mapped_column(String(50))

    # Self-reference: appeals + re-decisions point at the originating
    # determination's ledger row. The originating Decision stays closed;
    # the appeal becomes a fresh archetype run that links back through
    # this column. Keeps dp/decisions/ unaware of re-entry semantics —
    # the lifecycle continues to see only forward state transitions.
    parent_ledger_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("determination_ledger.id", ondelete="SET NULL"),
    )

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )


__all__ = ["DeterminationLedger"]
