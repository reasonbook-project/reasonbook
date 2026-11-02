// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Governance Roadmap API client — Prompt 1 endpoints.
 *
 * Naming follows the rebrand migration spec: new user-facing surfaces use
 * the "Governance" brand.
 *
 * Backend: dgp/api/governance.py.
 */

import { apiFetch } from "./client";

// ─── Composite (floor / strengths / anchoring) ────────────────────────────

export type GovernanceStrength = {
  facet_id: string;
  level: number;
};

export type GovernanceComposite = {
  floor: number;
  ceiling: number;
  anchoring: string[];
  strengths: GovernanceStrength[];
  next_floor_target: number;
};

// ─── Initiative templates (YAML-backed) ───────────────────────────────────

export type SmartFields = {
  origin: "template" | "user_authored";
  specific: string;
  measurable: string;
  achievable: string;
  relevant: string;
  timebound: string;
};

export type InitiativeTemplateMilestone = {
  id: string;
  title: string;
  produces: string | null;
  offset_quarter: number;
  decision_seed_title: string | null;
  methodology_anchor?: string | null;
  smart: SmartFields;
  risk_factors: string[];
  at_risk_propagation: boolean;
};

export type InitiativeTemplate = {
  facet_id: string;
  from_level: number;
  to_level: number;
  default_duration_quarters: number;
  milestones: InitiativeTemplateMilestone[];
};

export function getInitiativeTemplate(
  facetId: string,
  fromLevel: number,
  toLevel: number,
): Promise<InitiativeTemplate> {
  const params = new URLSearchParams({
    from_level: String(fromLevel),
    to_level: String(toLevel),
  });
  return apiFetch<InitiativeTemplate>(
    `/api/governance/templates/${encodeURIComponent(facetId)}?${params}`,
  );
}

// ─── Initiative shape (read + write) ──────────────────────────────────────

export type GovernanceMilestone = {
  id: string;
  title: string;
  produces: string | null;
  target_quarter: string;
  methodology_anchor: string | null;
  status: "planned" | "in_progress" | "achieved" | "slipped" | "at_risk";
  achieved_quarter: string | null;
  linked_decision_ids: string[];
  smart: SmartFields;
  risk_factors: string[];
  at_risk_propagation: boolean;
  decision_seed_title: string | null;
};

export type GovernanceInitiativeStatus =
  | "planned"
  | "in_progress"
  | "achieved"
  | "missed"
  | "paused"
  | "cancelled";

export type GovernanceInitiative = {
  id: string;
  initiative_number: string;
  tenant_id: string;
  facet_id: string;
  current_level: number;
  target_level: number;
  methodology_version: string;
  source_assessment_id: string | null;
  trigger_reason: "manual" | "below_target" | "stuck_2q" | "regression";
  started_quarter: string;
  target_completion_quarter: string;
  actual_completion_quarter: string | null;
  status: GovernanceInitiativeStatus;
  created_by: string;
  owner_user_id: string | null;
  milestones: GovernanceMilestone[];
  outcome: Record<string, unknown> | null;
  retarget_proposals: Array<Record<string, unknown>>;
  created_at: string;
  updated_at: string;
};

export type CreateInitiativeBody = {
  facet_id: string;
  current_level: number;
  target_level: number;
  started_quarter: string;
  target_completion_quarter: string;
  status: "planned" | "in_progress";
  milestones: Array<{
    id: string;
    title: string;
    produces?: string | null;
    target_quarter: string;
    decision_seed_title?: string | null;
    smart: SmartFields;
    risk_factors?: string[];
    at_risk_propagation?: boolean;
  }>;
  owner_user_id?: string | null;
  source_assessment_id?: string | null;
  trigger_reason?: "manual" | "below_target" | "stuck_2q" | "regression";
};

export function createInitiative(
  body: CreateInitiativeBody,
): Promise<GovernanceInitiative> {
  return apiFetch<GovernanceInitiative>("/api/governance/initiatives", {
    method: "POST",
    body,
  });
}

export type ListInitiativesOptions = {
  /**
   * One or more initiative statuses to keep. Comma-serialized to the
   * server. Omit to receive all statuses.
   */
  status?: ReadonlyArray<GovernanceInitiativeStatus>;
  facetId?: string;
};

export function listInitiatives(
  options: ListInitiativesOptions = {},
): Promise<{
  items: GovernanceInitiative[];
  workflow_id: string;
}> {
  const params = new URLSearchParams();
  if (options.status && options.status.length > 0) {
    params.set("status", options.status.join(","));
  }
  if (options.facetId) params.set("facet_id", options.facetId);
  const query = params.toString();
  const path = query ? `/api/governance/initiatives?${query}` : "/api/governance/initiatives";
  return apiFetch(path);
}

export function getInitiative(id: string): Promise<GovernanceInitiative> {
  return apiFetch<GovernanceInitiative>(
    `/api/governance/initiatives/${encodeURIComponent(id)}`,
  );
}

/**
 * Linked decisions for an initiative, grouped by milestone id. Used by
 * the InitiativeDetailDrawer to render decision cards inside the
 * expanded milestone state.
 */
export type LinkedDecisionSummary = {
  id: string;
  decision_number: string;
  title: string;
  tag: string | null;
  owner_id: string | null;
  status: string;
  decision_class: string;
  /** Slip-note history (Roadmap Prompt 3). Empty unless the decision's
   *  linked milestone has slipped at least once. */
  slip_notes: SlipNote[];
};

export type InitiativeDecisionsResponse = {
  by_milestone: Record<string, LinkedDecisionSummary[]>;
};

export function getInitiativeDecisions(
  id: string,
): Promise<InitiativeDecisionsResponse> {
  return apiFetch<InitiativeDecisionsResponse>(
    `/api/governance/initiatives/${encodeURIComponent(id)}/decisions`,
  );
}

// ─── Composite preview (optional helper) ──────────────────────────────────

export function previewComposite(
  facetPlacements: Record<string, number>,
): Promise<{ composite: GovernanceComposite }> {
  return apiFetch("/api/governance/composite/preview", {
    method: "POST",
    body: { facet_placements: facetPlacements },
  });
}

// ─── Slip / retarget / board-review (Roadmap Prompt 3) ────────────────────

/**
 * Slip note appended to a governance decision when the linked milestone
 * slips past its target quarter. Lives inside the decision's
 * ``slip_notes`` JSONB array — no separate slip-review row.
 *
 * ``body`` is empty until the owner fills it in via the decision detail
 * surface. ``author_user_id`` is the decision owner when the slip is
 * detected (the system actor that triggered the note).
 */
export type SlipNote = {
  milestone_id: string;
  quarter: string;
  author_user_id: string | null;
  created_at: string;
  body: string;
};

/**
 * Retarget proposal lifecycle: ``awaiting_confirm → confirmed | declined``.
 * Generated by the daily slip-detection job; resolved via
 * ``postRetarget``. A new proposal is generated by the next slip-
 * detection cycle if the situation changes after resolution.
 */
export type RetargetProposalStatus =
  | "awaiting_confirm"
  | "confirmed"
  | "declined";

export type RetargetProposedShift = {
  milestone_id: string;
  from: string;
  to: string;
};

export type RetargetProposal = {
  id: string;
  triggered_by_milestone: string;
  proposed_at_quarter: string;
  slip_duration_quarters: number;
  proposed_shifts: RetargetProposedShift[];
  status: RetargetProposalStatus;
  resolved_at: string | null;
  resolved_by_user_id: string | null;
};

export type RetargetAction = "confirm" | "decline";

export function postRetarget(
  initiativeId: string,
  proposalId: string,
  action: RetargetAction,
): Promise<GovernanceInitiative> {
  return apiFetch<GovernanceInitiative>(
    `/api/governance/initiatives/${encodeURIComponent(initiativeId)}/retarget`,
    {
      method: "POST",
      body: { proposal_id: proposalId, action },
    },
  );
}

/**
 * Board-review queue surface — currently used by the Prompt 3 drawer's
 * audit footer and (eventually) by Prompt 4's cycle dossier composer.
 */
export type BoardReviewTrigger =
  | "slip_detected"
  | "initiative_achieved"
  | "floor_advanced";

export type BoardReviewQueueStatus = "pending" | "queued" | "reviewed";

export type BoardReviewQueueItem = {
  id: string;
  tenant_id: string;
  initiative_id: string;
  initiative_number: string;
  facet_id: string;
  current_level: number;
  target_level: number;
  trigger: BoardReviewTrigger;
  queued_at: string;
  status: BoardReviewQueueStatus;
  cycle_id: string | null;
};

export function listBoardReviewQueue(
  status: BoardReviewQueueStatus | "all" = "pending",
): Promise<{ items: BoardReviewQueueItem[] }> {
  const params = new URLSearchParams({ status });
  return apiFetch<{ items: BoardReviewQueueItem[] }>(
    `/api/governance/board-review-queue?${params}`,
  );
}

// ─── Trend matrix (Roadmap Prompt 4) ──────────────────────────────────────

/**
 * One cell in a facet row or the composite row. ``level`` is null for
 * quarters with no assessment in the visible window — the renderer
 * shows an empty cell. ``is_floor_advance`` is only meaningful on the
 * composite row's cells; facet rows leave it false.
 */
export type TrendMatrixCellData = {
  quarter: string;
  level: number | null;
  is_floor_advance?: boolean;
};

export type TrendMatrixFacetRow = {
  facet_id: string;
  label: string;
  placements: TrendMatrixCellData[];
};

export type TrendMatrixCompositeRow = {
  label: string;
  placements: TrendMatrixCellData[];
};

export type TrendMatrixInitiativePin = {
  initiative_id: string;
  initiative_number: string;
  facet_id: string;
  started_quarter: string;
  current_status: GovernanceInitiativeStatus;
  current_level: number;
  target_level: number;
};

export type TrendMatrixPayload = {
  quarters: string[];
  facet_rows: TrendMatrixFacetRow[];
  composite_row: TrendMatrixCompositeRow;
  initiative_pins: TrendMatrixInitiativePin[];
};

export function fetchTrendMatrix(
  quarters: number = 8,
): Promise<TrendMatrixPayload> {
  return apiFetch<TrendMatrixPayload>(
    `/api/governance/trend-matrix?quarters=${quarters}`,
  );
}

// ─── Governance settings (Prompt 5) ────────────────────────────────────────

/**
 * Per-facet target tuple. The settings API returns the level the
 * institution aims to reach for the facet and the calendar quarter by
 * which it expects to get there. Both are admin-editable on
 * /settings/governance; both are consumed by the daily auto-suggest
 * job to decide which facets fire which triggers.
 */
export type GovernanceFacetTarget = {
  level: number;
  target_quarter: string;
};

export type GovernanceSettingsPayload = {
  tenant_id: string;
  /**
   * Master toggle for the daily Suggestion Engine. When ``false`` (the
   * default for new and backfilled tenants), the engine creates no
   * drafts for this tenant regardless of the per-trigger rules below.
   * Per migration 0031 / Roadmap Prompt 5.
   */
  ai_suggestions_enabled: boolean;
  trigger_below_target: boolean;
  trigger_stuck: boolean;
  facet_targets: Record<string, GovernanceFacetTarget>;
};

/**
 * Partial-update body. Any field can be omitted; only what's sent is
 * applied server-side. facet_targets is merged into the stored map —
 * sending only one facet leaves the others unchanged.
 */
export type GovernanceSettingsUpdate = Partial<{
  ai_suggestions_enabled: boolean;
  trigger_below_target: boolean;
  trigger_stuck: boolean;
  facet_targets: Record<string, GovernanceFacetTarget>;
}>;

export function fetchGovernanceSettings(): Promise<GovernanceSettingsPayload> {
  return apiFetch<GovernanceSettingsPayload>("/api/governance/settings");
}

export function updateGovernanceSettings(
  payload: GovernanceSettingsUpdate,
): Promise<GovernanceSettingsPayload> {
  return apiFetch<GovernanceSettingsPayload>("/api/governance/settings", {
    method: "PATCH",
    body: payload,
  });
}
