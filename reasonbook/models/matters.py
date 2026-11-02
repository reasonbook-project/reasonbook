# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Matter aggregate + supporting participant_orgs.

Per TENANCY-MODEL.md §11 and ADR-11. The matter is the aggregate root
that backs each Register-row; the federal originating Decision is one
node inside it, not a synonym for it.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from reasonbook.db import GUID, Base


class ParticipantOrg(Base):
    """A state or recipient org that can hold a matter node.

    Federal is implicit (NULL participant_org_id on the federal-root node)
    and not represented here.
    """

    __tablename__ = "participant_orgs"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    # 'state' | 'recipient'.
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    # USPS state code, UEI / DUNS, etc.
    code: Mapped[str | None] = mapped_column(Text)
    # State parent for sub-recipients; NULL otherwise. Note: a recipient
    # under multiple states gets one node per (state, recipient) pair in
    # matter_nodes — this column is a hint, not the source of truth
    # for the fund-flow tree.
    parent_org_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("participant_orgs.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Matter(Base):
    """Matter-level fields: program, agency, $ obligated, period, terms.

    The matter is what the Register lists. The matter's federal-tier root
    node + downstream tree (state, recipient) lives in `MatterNode`.
    """

    __tablename__ = "matters"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    # Program id from the YAML registry: 'CDBG' | 'SNAP' | 'NIH-R01' | ...
    program_id: Mapped[str] = mapped_column(Text, nullable=False)
    # Set from the program YAML's federal_archetype field.
    federal_archetype: Mapped[str] = mapped_column(Text, nullable=False)
    awarding_agency: Mapped[str] = mapped_column(Text, nullable=False)
    # Owning agency in the DP scope hierarchy. Nullable in this
    # migration for backfill; seed maps the awarding_agency name to
    # the corresponding agencies.id.
    agency_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("agencies.id", ondelete="RESTRICT"),
        nullable=True,
    )
    amount_obligated: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    period_label: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[str | None] = mapped_column(Text)
    retention_months: Mapped[int | None] = mapped_column(Integer)
    # Calendar anchor for the Matters-first Inbox's Incoming band.
    # Migration 0053. NULL for matters that never reach Incoming (fully
    # drawn matters, investigative-only rows, oversight roll-ups).
    planned_disbursement_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Federal award Decision (one of the nodes). Nullable because the
    # matter row is inserted before the originating Decision is minted
    # within the matter-create transaction (§12).
    originating_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("decisions.id", use_alter=True, name="fk_matters_originating_decision"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )


class MatterNode(Base):
    """One node in the matter's fund-flow tree.

    The federal root is the only node with NULL parent_node_id AND NULL
    participant_org_id. All other nodes have both set. Append-only:
    amendments write a new row and stamp the prior row's removed_at;
    the active row per (matter_id, participant_org_id) is the one with
    removed_at IS NULL (enforced by the unique partial index).
    """

    __tablename__ = "matter_nodes"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    matter_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("matters.id", ondelete="CASCADE"),
        nullable=False,
    )
    # NULL only for the federal root.
    parent_node_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("matter_nodes.id")
    )
    # 'federal' | 'state' | 'recipient'.
    tier: Mapped[str] = mapped_column(String(20), nullable=False)
    # NULL only for the federal root.
    participant_org_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("participant_orgs.id")
    )
    # Per-node delegation. Defaults pre-fill from the program YAML's
    # defaults.{tier}.active_archetypes; persisted value is source of
    # truth once written.
    active_archetypes: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("'[]'")
    )
    # Closed enum for v1: 'awarding_official' | 'state_program_director'
    # | 'certifying_officer'.
    authority_role: Mapped[str] = mapped_column(Text, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    added_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Append-only soft-delete marker. NULL = active row.
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Dollar amount that arrived AT this node (migration 0042). Renders
    # the fund-flow path with per-edge labels — HHS → $46.7M → Florida
    # DOH → $415k → Healthy Start. NULL when not known (synthetic seed
    # matters, oversight roll-ups). Forward-compatible with P25's
    # collector sync.
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
