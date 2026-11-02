# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Pydantic models for the unified workflow `config.yaml`.

Mirrors the structure documented in `reasonbook-workflow-yaml-schema-v1_0.md` §3.
The schema is intentionally permissive: legacy pipe YAMLs include sections
(``interface_calibration``, etc.) that don't drive runtime behaviour and are
not yet specified here, so models allow extra fields.

Boot-time validation in `reasonbook.semantic.loader` runs *post*-Pydantic referential
checks (every authority_required references a known authority_level, etc.) so
this file focuses on field-level shapes.
"""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

DirectionLiteral = Literal["higher_is_better", "lower_is_better", "neutral"]
SeverityLiteral = Literal["positive", "warning", "critical", "informational"]
PriorityLiteral = Literal["critical", "urgent", "high", "medium", "low"]
ImpactLiteral = Literal["critical", "high", "medium", "low"]

# ── Catalog facet enums (DESIGN-SPEC-semantic-catalog.md §"Data the catalog reads") ──
# Closed enums by design — the faceted catalog needs stable values to
# group / count / filter on. The default view groups by ``who_watches``;
# ``tier`` mirrors the federal/state/recipient model in TENANCY-MODEL;
# ``domain`` replaces the legacy ``category`` field (one slot, federal
# vocabulary).
WhoWatchesLiteral = Literal[
    "agency_head",
    "oig",
    "program_officer",
    "caseworker",
    "certifying_officer",
    "program_monitor",
    "state_administrator",
    "engineer",
]
CatalogTierLiteral = Literal["federal", "state", "recipient", "cross_tier"]
DomainLiteral = Literal[
    "governance",
    "payment_integrity",
    "eligibility",
    "oversight_response",
    "appropriations",
    "integrity",
    "subrecipient_oversight",
    "program_design",
]
TimeHorizonLiteral = Literal[
    "immediate",
    "short_term",
    "long_term",
    "strategic",
    "weekly",
    "monthly",
    "quarterly",
    "annual",
]
TypeLiteral = Literal["int", "float", "str", "bool", "list", "dict"]
WorkflowKindLiteral = Literal["user_configuration"]


class _Permissive(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class Workflow(_Permissive):
    id: str
    name: str
    full_name: str | None = None
    description: str = ""
    version: str = "1.0"
    vertical: str = "financial_institution"
    icon: str | None = None
    color: str | None = None
    apex_contributing: bool = True
    # Apex discriminators per reasonbook-apex-workflow-spec-v1_0.md §3.1.
    # Exactly one workflow may have is_apex=True; that's the strategic-tier
    # workflow. enterprise_only gates entitlement availability behind the
    # tenant's Enterprise tier (currently equivalent to has_apex=True).
    is_apex: bool = False
    enterprise_only: bool = False
    # Per decision-governance-self-assessment-platform-variant-v1_0.md §8.5.3:
    # `kind` is optional, absent by default. The 10 standard governance
    # workflows tenants buy do not set it. Setting `kind: user_configuration`
    # marks the workflow as hosting tenant-level user-configuration decisions
    # (designated respondent for the self-assessment, future configuration
    # commits, etc.) — these workflows are always entitled to every tenant,
    # don't appear in the rail's main entitled-workflows section, and don't
    # have their own control room. Current occupant: ``user-configuration``.
    kind: WorkflowKindLiteral | None = None


class DecisionDomain(_Permissive):
    """Apex-only — strategic decision domains per apex spec §3.3."""

    id: str
    name: str
    primary_owner_role: str | None = None
    secondary_owner_roles: list[str] = Field(default_factory=list)
    typical_evidence_workflows: list[str] = Field(default_factory=list)
    description: str | None = None


class EvidenceRole(_Permissive):
    """Apex-only — evidence roles per apex spec §4.2."""

    id: str
    name: str
    description: str | None = None
    typical_count_per_apex_decision: str | None = None
    constraint: str | None = None


class EntityAttribute(_Permissive):
    name: str
    type: str
    values: list[str] | None = None
    description: str | None = None


class Entity(_Permissive):
    display_name: str
    description: str | None = None
    attributes: list[EntityAttribute] = Field(default_factory=list)


class AlertCategory(_Permissive):
    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    # Catalog facets — see DESIGN-SPEC-semantic-catalog.md.
    meaning: str | None = None
    why_it_matters: str | None = None
    owner: str | None = None
    who_watches: WhoWatchesLiteral | None = None
    tier: CatalogTierLiteral | None = None
    domain: DomainLiteral | None = None
    severity: SeverityLiteral | None = None
    plain_thresholds: str | None = None


class MetricThresholds(_Permissive):
    critical_low: float | None = None
    warning_low: float | None = None
    target: float | None = None
    stretch: float | None = None
    warning_high: float | None = None
    critical_high: float | None = None


class Metric(_Permissive):
    id: str
    name: str
    description: str | None = None
    unit: str | None = None
    format: str | None = None
    direction: DirectionLiteral = "neutral"
    grain: list[str] | None = None
    calculation: str | None = None
    thresholds: MetricThresholds = Field(default_factory=MetricThresholds)
    # Catalog facets — see DESIGN-SPEC-semantic-catalog.md.
    # ``domain`` replaces the legacy ``category`` field; meaning /
    # why_it_matters / owner / plain_thresholds are the plain-language
    # surface the de-IT-ified catalog leads with.
    meaning: str | None = None
    why_it_matters: str | None = None
    owner: str | None = None
    who_watches: WhoWatchesLiteral | None = None
    tier: CatalogTierLiteral | None = None
    domain: DomainLiteral | None = None
    plain_thresholds: str | None = None


class MetricGroup(_Permissive):
    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    metrics: list[str] = Field(default_factory=list)


class SegmentItem(_Permissive):
    id: str
    name: str
    filter: str | None = None
    decision_types: list[str] = Field(default_factory=list)


class Chart(_Permissive):
    id: str
    name: str
    type: str
    description: str | None = None
    metrics: list[str] = Field(default_factory=list)
    reference_lines: list[dict[str, Any]] = Field(default_factory=list)


class InsightTemplate(_Permissive):
    id: str
    trigger: str
    headline: str
    detail: str = ""
    severity: SeverityLiteral = "informational"


class Trigger(_Permissive):
    metric: str | None = None
    condition: str | None = None
    description: str | None = None


class Action(_Permissive):
    id: str
    name: str
    description: str | None = None
    authority_required: str
    deadline: str | None = None
    impact: ImpactLiteral = "medium"


class DecisionType(_Permissive):
    id: str
    name: str
    description: str | None = None
    time_horizon: TimeHorizonLiteral = "short_term"
    icon: str | None = None
    priority: PriorityLiteral = "medium"
    sla_hours: int | None = None
    default_owner_role: str | None = None
    triggers: list[Trigger] = Field(default_factory=list)
    available_actions: list[Action] = Field(default_factory=list)
    outcome_metrics: list[str] = Field(default_factory=list)
    payload_schema: dict[str, Any] | None = None
    oversight_evidence_eligible: bool = True
    # Phase 7.5 Gate 6 (per reasonbook-authoring-and-config-amendment-v1_2.md §4 task 9
    # and reasonbook-workflow-yaml-schema-v1_0.md §3.9):
    #
    # `manually_creatable` opts a decision type in to human-originated creation
    # via the Phase 7.5 manual-creation drawer. Default is False; a decision
    # type stays auto-only unless we explicitly mark it human-originatable.
    #
    # `authoring_authority_level` is required when manually_creatable is True
    # and must reference an authority_level id declared on the workflow
    # (named by role, not ordinal — per-workflow level scales differ). The
    # cross-section reference check runs in reasonbook.semantic.loader.
    manually_creatable: bool = False
    authoring_authority_level: str | None = None
    # Catalog facets — see DESIGN-SPEC-semantic-catalog.md.
    meaning: str | None = None
    why_it_matters: str | None = None
    owner: str | None = None
    who_watches: WhoWatchesLiteral | None = None
    tier: CatalogTierLiteral | None = None
    domain: DomainLiteral | None = None


class AuthorityLevel(_Permissive):
    id: str
    name: str
    level: int
    can_approve: list[str] = Field(default_factory=list)
    limits: dict[str, Any] | None = None


class Persona(_Permissive):
    id: str
    name: str
    description: str | None = None
    icon: str | None = None
    default_authority_level: str | None = None
    cognitive_budget: str | None = None
    # Catalog facets — see DESIGN-SPEC-semantic-catalog.md.
    meaning: str | None = None
    why_it_matters: str | None = None
    owner: str | None = None
    who_watches: WhoWatchesLiteral | None = None
    tier: CatalogTierLiteral | None = None
    domain: DomainLiteral | None = None


class SlaSection(_Permissive):
    default_response_hours: int = 72
    business_hours_start: str = "08:00"
    business_hours_end: str = "17:00"
    timezone: str = "America/New_York"
    holidays: list[str] = Field(default_factory=list)


class OwnershipSection(_Permissive):
    primary_role: str
    backup_role: str | None = None
    escalation_role: str | None = None


UploadFieldType = Literal["string", "integer", "float", "boolean", "date"]
UploadFormat = Literal["csv", "json", "xlsx"]


class UploadColumn(_Permissive):
    """One CSV/JSON column in the upload contract.

    Mirrors the per-field schema vocabulary (type/required/min/max)
    flattened so YAML reads naturally — no nested ``constraints:`` block.
    The ``example`` value powers the sample-CSV download.
    """

    name: str
    type: UploadFieldType
    required: bool = False
    description: str | None = None
    example: Any = None
    # Constraints — applied during validation in reasonbook.uploads.validator.
    min: float | None = None
    max: float | None = None
    max_length: int | None = None
    pattern: str | None = None  # regex for string columns
    enum: list[Any] | None = None
    # Period column marker — exactly one per UploadSchema gets primary_key=True
    # and its value becomes the pipe row's period_date.
    primary_key: bool = False


class UploadSchema(_Permissive):
    """Per-workflow manual upload contract.

    Optional — workflows without manual upload (e.g., apex) omit the
    ``upload:`` section entirely. The direct writer in
    ``reasonbook.uploads.writer`` inserts validated rows into ``pipe_table``.
    """

    enabled: bool = True
    description: str | None = None
    # The pipe_* staging table the validated rows land in. Must match the
    # PIPE_TABLE_NAMES entry in reasonbook.ingestion.pipe_reader so ingestion
    # can find the row after upload.
    pipe_table: str
    formats: list[UploadFormat] = Field(default_factory=lambda: cast(list[UploadFormat], ["csv"]))
    period_type: Literal["monthly", "quarterly", "annual"] = "monthly"
    period_format_hint: str = "YYYY-MM"
    columns: list[UploadColumn] = Field(default_factory=list)

    @field_validator("columns")
    @classmethod
    def _exactly_one_period_pk(cls, v: list[UploadColumn]) -> list[UploadColumn]:
        pks = [c for c in v if c.primary_key]
        if len(pks) != 1:
            raise ValueError(
                "upload schema requires exactly one column with primary_key: true "
                f"(the period column); found {len(pks)}"
            )
        return v

    @field_validator("columns")
    @classmethod
    def _unique_column_names(cls, v: list[UploadColumn]) -> list[UploadColumn]:
        names = [c.name for c in v]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate upload column names: {sorted(dupes)}")
        return v


class WorkflowConfig(_Permissive):
    """Top-level container — the parsed `config.yaml`."""

    workflow: Workflow
    entities: dict[str, Entity] = Field(default_factory=dict)
    alert_categories: list[AlertCategory] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    metric_groups: list[MetricGroup] = Field(default_factory=list)
    segments: dict[str, list[SegmentItem]] = Field(default_factory=dict)
    charts: dict[str, Chart] = Field(default_factory=dict)
    insight_templates: list[InsightTemplate] = Field(default_factory=list)
    decision_types: list[DecisionType] = Field(default_factory=list)
    authority_levels: list[AuthorityLevel] = Field(default_factory=list)
    personas: list[Persona] = Field(default_factory=list)
    overridable_keys: dict[str, TypeLiteral] = Field(default_factory=dict)
    sla: SlaSection
    ownership: OwnershipSection
    # Sprint 3 — manual upload contract. None for workflows that don't
    # accept manual uploads (apex, future workflows where there is no
    # corresponding schema).
    upload: UploadSchema | None = None

    # Apex-only sections — empty for operational workflows.
    decision_domains: list[DecisionDomain] = Field(default_factory=list)
    evidence_roles: list[EvidenceRole] = Field(default_factory=list)

    @field_validator("metrics")
    @classmethod
    def _unique_metric_ids(cls, v: list[Metric]) -> list[Metric]:
        ids = [m.id for m in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate metric ids: {sorted(dupes)}")
        return v

    @field_validator("decision_types")
    @classmethod
    def _unique_decision_type_ids(cls, v: list[DecisionType]) -> list[DecisionType]:
        ids = [d.id for d in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate decision_type ids: {sorted(dupes)}")
        return v

    @field_validator("authority_levels")
    @classmethod
    def _unique_authority_ids(cls, v: list[AuthorityLevel]) -> list[AuthorityLevel]:
        ids = [a.id for a in v]
        dupes = {x for x in ids if ids.count(x) > 1}
        if dupes:
            raise ValueError(f"duplicate authority_level ids: {sorted(dupes)}")
        return v
