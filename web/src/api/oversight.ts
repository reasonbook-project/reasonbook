// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

// ─── Types ────────────────────────────────────────────────────────────────

export type EvidenceRole =
  | "primary_evidence"
  | "supporting_evidence"
  | "risk_concentration_evidence"
  | "regulatory_alignment_evidence"
  | "outcome_evidence"
  | "counter_evidence";

export type ApexEvidenceOperational = {
  id: string;
  decision_number: string;
  title: string;
  workflow_id: string;
  status: string;
  decided_at: string | null;
};

export type ApexEvidenceLink = {
  id: string;
  oversight_decision_id: string;
  operational_decision_id: string;
  evidence_role: EvidenceRole;
  link_rationale: string | null;
  linked_at: string | null;
  linked_by: string;
  superseded_at: string | null;
  superseded_by_link_id: string | null;
  /** Present on list responses; absent on the create response. */
  operational?: ApexEvidenceOperational;
};

export type BoardCycle = {
  id: string;
  tenant_id: string;
  name: string;
  cycle_type: string;
  committee: string | null;
  cycle_start: string;
  cycle_end: string;
  status: "planned" | "active" | "concluded";
  meeting_date: string | null;
  notes: string | null;
  created_at: string;
  created_by: string;
  /** Present on list responses; counts apex decisions tied to the cycle. */
  decision_count?: number;
};

/** Returns the URL for the cycle dossier PDF endpoint.
 *
 * The dossier is served as a binary download by the Flask handler
 * (Content-Disposition: attachment), so the simplest UX is an `<a>`
 * pointing here — no extra fetch needed. The session cookie travels
 * with the link request so auth Just Works.
 */
export function cycleDossierUrl(cycleId: string): string {
  return `/api/oversight/cycles/${cycleId}/dossier`;
}

// ─── Calls ────────────────────────────────────────────────────────────────

export function listBoardCycles(
  status?: "planned" | "active" | "concluded",
): Promise<{ items: BoardCycle[] }> {
  const q = status ? `?status=${status}` : "";
  return apiFetch<{ items: BoardCycle[] }>(`/api/oversight/cycles${q}`);
}

/** Oversight-cycle finding. Populated from platform.oversight_findings
 *  (migration 0052). Append-only; transitions to closed / under_appeal
 *  stamp the disposition but preserve the row. */
export type OversightFinding = {
  id: string;
  cycle_id: string;
  finding_number: string;
  title: string;
  observation: string;
  source: "oig" | "gao" | "single_audit" | "internal_audit";
  severity: "critical" | "high" | "medium" | "low";
  status: "open" | "closed" | "under_appeal";
  cited_matter_ids: string[];
  citations: string[];
  disposition: string | null;
  opened_at: string;
  opened_by: string;
  closed_at: string | null;
  closed_by: string | null;
};

export type OversightFindingCounts = {
  total: number;
  open: number;
  closed: number;
  under_appeal: number;
};

export function listCycleFindings(
  cycleId: string,
): Promise<{ items: OversightFinding[]; counts: OversightFindingCounts }> {
  return apiFetch<{
    items: OversightFinding[];
    counts: OversightFindingCounts;
  }>(`/api/oversight/cycles/${cycleId}/findings`);
}

export function listApexEvidence(
  oversightDecisionId: string,
): Promise<{ items: ApexEvidenceLink[] }> {
  return apiFetch<{ items: ApexEvidenceLink[] }>(
    `/api/oversight/decisions/${oversightDecisionId}/evidence`,
  );
}

export type CreateEvidenceBody = {
  operational_decision_id: string;
  evidence_role?: EvidenceRole;
  rationale?: string;
};

export function createApexEvidence(
  oversightDecisionId: string,
  body: CreateEvidenceBody,
): Promise<ApexEvidenceLink> {
  return apiFetch<ApexEvidenceLink>(
    `/api/oversight/decisions/${oversightDecisionId}/evidence`,
    { method: "POST", body },
  );
}

export type SupersedeEvidenceBody = {
  replacement_operational_decision_id?: string;
  replacement_evidence_role?: EvidenceRole;
  rationale?: string;
};

export function supersedeApexEvidence(
  linkId: string,
  body: SupersedeEvidenceBody = {},
): Promise<{ superseded: ApexEvidenceLink; replacement: ApexEvidenceLink | null }> {
  return apiFetch(`/api/oversight/evidence/${linkId}/supersede`, {
    method: "POST",
    body,
  });
}

// ─── Board actions (apex spec §6.2, TODO P51) ─────────────────────────────

export type BoardAction =
  | "ratified_by_board"
  | "noted_by_board"
  | "ratified_by_committee"
  | "deferred_to_next_cycle";

export type RecordBoardActionBody = {
  action: BoardAction;
  /** Only relevant for `ratified_by_committee`. */
  committee?: string;
  /** Optional free-text rationale recorded with the event. */
  note?: string;
};

export function recordBoardAction(
  oversightDecisionId: string,
  body: RecordBoardActionBody,
): Promise<{ ok: boolean; action: BoardAction }> {
  return apiFetch(`/api/oversight/decisions/${oversightDecisionId}/board-action`, {
    method: "POST",
    body,
  });
}
