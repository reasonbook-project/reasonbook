// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

/**
 * Register tree — the non-matter matter types (Cases, Decisions awaiting
 * review). Matters live in api/matters; this client surfaces the rest of
 * what the Register lists per SURFACE-USER-STORIES.md.
 */

export type RegistryAlertSummary = {
  id: string;
  severity: "critical" | "high" | "medium" | "low";
  source: "fraud_risk_screening" | "flow_graph" | "identity";
  title: string;
  matter_id: string | null;
};

export type RegistryDecisionSummary = {
  id: string;
  decision_number: string;
  title: string;
  status: string;
  priority: string | null;
  workflow_id: string;
  decision_type: string | null;
  created_at: string | null;
  decided_at: string | null;
  owner_id: string | null;
  /** Set on Cases (decisions promoted from an alert); null otherwise. */
  alert: RegistryAlertSummary | null;
};

export type RegistryListResponse = {
  items: RegistryDecisionSummary[];
  total: number;
};

export function listCases(): Promise<RegistryListResponse> {
  return apiFetch<RegistryListResponse>("/api/registry/cases");
}

export function listOrphanDecisions(): Promise<RegistryListResponse> {
  return apiFetch<RegistryListResponse>("/api/registry/decisions");
}

// ─── Disputes ─────────────────────────────────────────────────────────

/**
 * Identity-resolution dispute. Each dispute pairs two candidate
 * identities (SAM.gov entity, USASpending recipient, LEIE row, etc.)
 * that look similar enough to warrant analyst review before an award
 * moves.
 */
export type Dispute = {
  id: string;
  subject_name: string;
  status:
    | "open"
    | "resolved_same"
    | "resolved_different"
    | "manual_override"
    | "withdrawn";
  resolution: string | null;
  resolution_rationale: string | null;
  candidate_a: Record<string, unknown>;
  candidate_b: Record<string, unknown>;
  notes: string | null;
  opened_at: string | null;
  resolved_at: string | null;
  related_matter_id: string | null;
  related_alert_id: string | null;
};

export type DisputeListResponse = {
  items: Dispute[];
  total: number;
};

export function listDisputes(): Promise<DisputeListResponse> {
  return apiFetch<DisputeListResponse>("/api/registry/disputes");
}

export function getDispute(disputeId: string): Promise<Dispute> {
  return apiFetch<Dispute>(`/api/registry/disputes/${disputeId}`);
}

export type DisputeResolution =
  | "same_entity"
  | "different_entities"
  | "manual_override";

export type ResolveDisputeResponse = {
  dispute: Dispute;
  decision_id: string;
  decision_workflow_id: string;
  decision_matter_id: string | null;
};

export function resolveDispute(
  disputeId: string,
  body: { resolution: DisputeResolution; rationale?: string },
): Promise<ResolveDisputeResponse> {
  return apiFetch<ResolveDisputeResponse>(
    `/api/registry/disputes/${disputeId}/resolve`,
    { method: "POST", body },
  );
}
