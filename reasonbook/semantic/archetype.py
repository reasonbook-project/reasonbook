# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the archetype × program-profile workflow contract.

Per docs/architecture/MODEL-DESIGN-SPEC.md and archetype.schema.yaml.
Coexists with the legacy WorkflowConfig in reasonbook.semantic.schema, which
still backs the apex and user-configuration workflows.

Three things this file defines:

  * Archetype  — Tier-2 base contract (one of ~7). Defines stages,
    gates, roles, evidence, outcomes, events. Loaded from
    dp/config/archetypes/<id>.yaml.
  * Program    — Tier-3 override layer that binds one archetype and
    fills its profile_required slots. Loaded from
    dp/config/programs/<id>.yaml.
  * Enums      — Literal types for gate, flow, decision_basis,
    promotes, promotion triggers, edge types.

The override allowlist (archetype.profile_extensible) is enforced by
the loader, not by Pydantic field constraints — the loader runs a
post-validation pass that checks the program's set fields against the
archetype's profile_extensible / profile_required dot-path lists.

Promotion logic (every_case vs on_trigger; resolution of
``gate: conditional``) lives in :mod:`reasonbook.promotion`, not here. This
file is structural only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

FamilyLiteral = Literal["grant", "entitlement", "procurement"]
FlowLiteral = Literal["forward", "reverse"]
DecisionBasisLiteral = Literal[
    "review",
    "eligibility_rules",
    "formula",
    "authorization",
]
PromotesLiteral = Literal["every_case", "on_trigger"]
PromotionTriggerLiteral = Literal[
    "override",
    "adverse_action",
    "appeal",
    "sample",
    "fraud_flag",
]
StageMapsToLiteral = Literal[
    "signal",
    "owner",
    "decision",
    "action",
    "outcome",
]
# Stage gate enum. ``conditional`` is dormant until a promotion trigger
# fires — resolved upstream in :mod:`reasonbook.promotion` so :mod:`reasonbook.decisions`
# only ever sees ``none`` or ``authority``.
GateLiteral = Literal["none", "authority", "conditional"]

# Per TENANCY-MODEL §5 — gate vs notify for upstream-review behavior on
# archetypes. notify writes a decision_events row only; gate writes the
# event AND creates an upstream Decision in 'assigned' status.
ReviewModeLiteral = Literal["gate", "notify"]

# Per TENANCY-MODEL §14.4 — honest about program clarity. lacks_definition
# disables the pickup heartbeat; ambiguous softens alert framing and
# unlocks the request_clarification disposition action.
DefinitionQualityLiteral = Literal["clear", "ambiguous", "lacks_definition"]

# Mirrors alerts.severity. Used by heartbeat config to label the
# ownership_gap alert that fires when a watch breaches.
SeverityLiteral = Literal["critical", "high", "medium", "low"]

# Three tiers of the dollar chain per TENANCY-MODEL §1.
TierLiteral = Literal["federal", "state", "recipient"]


# ---------------------------------------------------------------------------
# Permissive base — allow forward-compatible extra keys without losing
# validation on the known shape.
# ---------------------------------------------------------------------------


class _Permissive(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# ---------------------------------------------------------------------------
# Archetype sub-models
# ---------------------------------------------------------------------------


class ArchetypeMeta(_Permissive):
    id: str
    name: str
    description: str | None = None
    # ``family`` is multi-valued because some archetypes genuinely span
    # families. ``payment_authorization`` and ``adverse_action`` apply to
    # grant, entitlement, AND procurement programs; single-family
    # archetypes wrap their one value in a list (``[grant]``).
    family: list[FamilyLiteral]
    flow: FlowLiteral
    decision_basis: DecisionBasisLiteral
    # Volume switch (the "entitlement caveat" in MODEL-DESIGN-SPEC §57):
    #   every_case — full Decision per case (grants, contracts, adverse actions)
    #   on_trigger — Decision only on a promotion_triggers event (SNAP, Medicaid)
    promotes: PromotesLiteral


class Ledger(_Permissive):
    """Always-on ledger: every atomic determination is recorded.

    Distinct from the Decision lifecycle. Per the model spec, the
    ledger is the system of record for reconstruction; the Decision
    wrapper only attaches when ``promotes == every_case`` or when a
    promotion trigger fires for an ``on_trigger`` archetype.
    """

    records: Literal["all_determinations"] = "all_determinations"
    fields: list[str] = Field(default_factory=list)
    reconstructable: bool = True


class FlowTemplate(_Permissive):
    """Funding-flow topology — parse-but-dormant.

    Consumed later by the graph projection (deferred to GRAPH-MODEL.md
    follow-up). Validated structurally here so archetypes can declare
    expected tier chains and edge types without the runtime acting on
    them yet.
    """

    tiers: list[str] = Field(default_factory=list)
    required_edges: list[str] = Field(default_factory=list)
    optional_edges: list[str] = Field(default_factory=list)
    edge_types: list[str] = Field(default_factory=list)


class Stage(_Permissive):
    """One stage in the archetype's flow.

    ``maps_to`` pins each archetype stage to one of the five lifecycle
    stages in :mod:`reasonbook.decisions` (Signal/Owner/Decision/Action/Outcome).
    ``gate: conditional`` is the new dormant-until-promoted gate; the
    promotion wrapper resolves it to ``authority`` when materializing
    a Decision, so the lifecycle code stays unchanged.
    """

    id: str
    maps_to: StageMapsToLiteral
    label: str
    gate: GateLiteral
    decision_basis_step: bool = False
    required_evidence: list[str] = Field(default_factory=list)
    sla_hint_hours: int | None = None


class Role(_Permissive):
    id: str
    label: str
    authority: bool = False


class AuthorityRef(_Permissive):
    delegation_ref: str
    gated_transitions: list[str] = Field(default_factory=list)


class EvidenceSpec(_Permissive):
    kinds: list[str] = Field(default_factory=list)
    attachments: bool = True


class OverrideSpec(_Permissive):
    allowed: bool = True
    rationale_required: bool = True
    outcome_alignment_check: bool = True


class ReconstructabilityRef(_Permissive):
    standard_ref: str
    retention_months: int = 24


class Outcome(_Permissive):
    id: str
    label: str
    terminal: bool = False


class UpstreamReview(_Permissive):
    """Per-archetype gate-vs-notify policy for upstream-review events.

    Per TENANCY-MODEL §5. Defaults are deliberately permissive (notify
    everywhere). A missing block reads as "all notify"; declaring `gate`
    on a specific action is an intentional opt-in to upstream review.

    ``review_sla_hours`` is the SLA on a gating upstream Decision once
    created (the upstream tier has this long to ratify or send back).
    Defaults to 120 (5 business days).
    """

    on_promote: ReviewModeLiteral = "notify"
    on_outcome: ReviewModeLiteral = "notify"
    on_modification: ReviewModeLiteral = "notify"
    on_adverse_action: ReviewModeLiteral = "notify"
    on_closeout: ReviewModeLiteral = "notify"
    review_sla_hours: int = 120


# ---------------------------------------------------------------------------
# Archetype — Tier 2 top-level
# ---------------------------------------------------------------------------


class Archetype(_Permissive):
    schema_version: str = "1.0"
    archetype: ArchetypeMeta
    ledger: Ledger
    promotion_triggers: list[PromotionTriggerLiteral] = Field(default_factory=list)
    flow_template: FlowTemplate
    stages: list[Stage]
    roles: list[Role]
    authority: AuthorityRef
    evidence: EvidenceSpec
    overrides: OverrideSpec
    reconstructability: ReconstructabilityRef
    outcomes: list[Outcome]
    events: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    profile_extensible: list[str] = Field(default_factory=list)
    profile_required: list[str] = Field(default_factory=list)
    # Per TENANCY-MODEL §5. Default factory produces an all-notify shape;
    # gates are declared explicitly in the YAML on a per-archetype basis.
    upstream_review: UpstreamReview = Field(default_factory=UpstreamReview)

    @field_validator("stages")
    @classmethod
    def _unique_stage_ids(cls, v: list[Stage]) -> list[Stage]:
        ids = [s.id for s in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate stage ids: {sorted(dupes)}")
        return v

    @field_validator("outcomes")
    @classmethod
    def _unique_outcome_ids(cls, v: list[Outcome]) -> list[Outcome]:
        ids = [o.id for o in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate outcome ids: {sorted(dupes)}")
        return v

    @field_validator("roles")
    @classmethod
    def _unique_role_ids(cls, v: list[Role]) -> list[Role]:
        ids = [r.id for r in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate role ids: {sorted(dupes)}")
        return v


# ---------------------------------------------------------------------------
# Program (profile) — Tier 3 override
# ---------------------------------------------------------------------------


class ProfileMeta(_Permissive):
    id: str
    name: str
    # Matter UI consumes this in the page header and the Caseload rail.
    # Falls back to ``name`` when not provided.
    display_name: str | None = None
    binds_archetype: str
    # Legacy single field — programs may continue to populate this; new
    # callers should read ``awarding_agency`` for the explicit semantics
    # (which agency obligates funds vs. which one administers).
    agency: str | None = None
    awarding_agency: str | None = None
    # Convenience copy of binds_archetype for federal-originating
    # programs. Lets matter code read "what archetype do federal users
    # finalize on?" without re-resolving binding.
    federal_archetype: str | None = None
    # Program-level retention override. When set, must extend the
    # archetype default (loader's extend-only validation reuses the
    # same predicate).
    retention_months: int | None = None


class TierDefaults(_Permissive):
    """Per-tier defaults pre-filling the matter create form (TENANCY §11.2).

    ``active_archetypes`` is the set of archetype ids a stakeholder at
    this tier can run under this program. ``authority_role`` is the
    label that holds the gate (closed enum in v1: 'awarding_official',
    'state_program_director', 'certifying_officer').
    """

    active_archetypes: list[str] = Field(default_factory=list)
    authority_role: str | None = None


class ProgramDefaults(_Permissive):
    """Per-matter delegation defaults per TENANCY §11.2.

    Matter create reads these to pre-fill the decision-rights table.
    The persisted values on matter_nodes are the source of truth
    from t0 forward; defaults are starting points only.
    """

    federal: TierDefaults = Field(default_factory=TierDefaults)
    state: TierDefaults = Field(default_factory=TierDefaults)
    recipient: TierDefaults = Field(default_factory=TierDefaults)


class HeartbeatConfig(_Permissive):
    """Per-program heartbeat thresholds per TENANCY §14.3/§14.4.

    Each *_days field opens a watch when its corresponding tier
    transition occurs (federal->state, state->recipient, recipient->state
    for rollup). When the watch breaches, an ownership_gap alert fires
    with the matching severity.

    ``alert_cascade_hours`` is an optional per-severity override of the
    ALERTS-SPEC §10.3 defaults (72h for critical/high, 7d otherwise).
    Rarely needed; declared per-program when a program's audit-clock
    rules differ from the cross-platform defaults.
    """

    state_pickup_days: int | None = None
    state_pickup_severity: SeverityLiteral = "high"
    recipient_draw_days: int | None = None
    recipient_draw_severity: SeverityLiteral = "medium"
    outcome_rollup_days: int | None = None
    outcome_rollup_severity: SeverityLiteral = "medium"
    alert_cascade_hours: dict[str, int] | None = None


class Program(_Permissive):
    """A program profile — binds one archetype and fills its slots.

    ``decision_logic`` shape varies by the bound archetype's
    ``decision_basis`` (review criteria for ``review``; rule sets for
    ``eligibility_rules``; formula for ``formula``; auth-check spec for
    ``authorization``). Pydantic keeps it open here; the loader's
    archetype-aware validation pass enforces the right shape.
    """

    schema_version: str = "1.0"
    profile: ProfileMeta
    decision_logic: dict[str, Any]
    authority: dict[str, Any]
    role_assignments: dict[str, str]
    vocabulary: dict[str, str]
    stage_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)
    data_sources: list[str] = Field(default_factory=list)
    reconstructability: dict[str, Any] = Field(default_factory=dict)
    # Per TENANCY-MODEL §14.4. Default 'clear' so legacy programs that
    # don't yet declare the flag continue to validate; in practice every
    # program YAML should set this explicitly because the choice is
    # auditable evidence in its own right.
    definition_quality: DefinitionQualityLiteral = "clear"
    defaults: ProgramDefaults = Field(default_factory=ProgramDefaults)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)


__all__ = [
    "Archetype",
    "ArchetypeMeta",
    "AuthorityRef",
    "EvidenceSpec",
    "FlowTemplate",
    "HeartbeatConfig",
    "Ledger",
    "Outcome",
    "OverrideSpec",
    "Program",
    "ProgramDefaults",
    "ProfileMeta",
    "ReconstructabilityRef",
    "Role",
    "Stage",
    "TierDefaults",
    "UpstreamReview",
    "DecisionBasisLiteral",
    "DefinitionQualityLiteral",
    "FamilyLiteral",
    "FlowLiteral",
    "GateLiteral",
    "PromotesLiteral",
    "PromotionTriggerLiteral",
    "ReviewModeLiteral",
    "SeverityLiteral",
    "StageMapsToLiteral",
    "TierLiteral",
]
