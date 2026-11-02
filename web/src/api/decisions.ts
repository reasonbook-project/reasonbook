// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { ApiError, apiFetch } from "./client";

// ─── Types ────────────────────────────────────────────────────────────────

export type DecisionStatus =
  | "open"
  | "assigned"
  | "in_progress"
  | "decided"
  | "closed"
  | "deferred"
  | "escalated";

export type DecisionPriority = "critical" | "urgent" | "high" | "medium" | "low";
export type DecisionSeverity = "low" | "medium" | "high" | "critical";

export type DecisionScope = "mine" | "team" | "all_entitled";
export type DecisionDensity = "active" | "all";
export type DecisionStage =
  | "signals"
  | "decisions"
  | "actions"
  | "awaiting_committee"
  | "outcomes"
  | "closed";
export type DecisionSort = "newest" | "oldest" | "sla_deadline" | "priority";

export type EscalationStep = {
  user_id: string;
  name: string;
  level: number | null;
};

export type Decision = {
  id: string;
  decision_number: string;
  tenant_id: string;
  workflow_id: string;
  decision_type: string;
  title: string;
  description: string | null;
  priority: DecisionPriority;
  severity: DecisionSeverity;
  status: DecisionStatus;
  sla_hours: number | null;
  sla_deadline: string | null;
  sla_status: string | null;

  signal_captured_at: string | null;
  signal_source: string | null;
  signal_summary: string | null;
  trigger_data: Record<string, unknown> | null;

  owner_id: string | null;
  created_by: string | null;
  assigned_at: string | null;
  acknowledged_at: string | null;
  owner_authority_level: number | null;
  escalation_path: EscalationStep[] | null;

  decided_at: string | null;
  selected_option: string | null;
  alternatives: unknown[] | null;
  evidence_refs: unknown[] | null;
  rationale: string | null;

  action_started_at: string | null;
  action_completed_at: string | null;
  action_artifacts: unknown[] | null;

  outcome_recorded_at: string | null;
  outcome_text: string | null;
  outcome_impact: "positive" | "neutral" | "negative" | null;
  outcome_metrics: Record<string, unknown> | null;
  closed_at: string | null;

  defer_reason: string | null;
  defer_reopen_at: string | null;
  escalated_to: string | null;
  escalation_reason: string | null;

  decision_payload: Record<string, unknown> | null;
  tags: string[] | null;
  created_at: string;
  updated_at: string;

  // Commitment fields (spec §6) — populated when this Decision was
  // written as an external-party response. NULL / false on internally-
  // authored decisions.
  is_commitment?: boolean;
  originating_party_name?: string | null;
  response_shape?: {
    prompt_type?: string;
    accepted?: string;
    exceptions?: string | null;
    signatory_name?: string;
    signatory_title?: string;
    attestations?: string[];
    attachments?: unknown[];
    [k: string]: unknown;
  } | null;
  /** Text stand-in for the RFR FK until the requests_for_response
   *  table lands. Phase A0: freeform string. */
  in_response_to?: string | null;

  // Tenancy / matter membership per TENANCY-MODEL §11. NULL on
  // legacy / pre-matter decisions; populated when the matter service
  // mints the Decision through create_matter.
  matter_id: string | null;
  matter_node_id: string | null;
  fund_flow_path: string[];

  // Apex extensions per dgp-apex-workflow-spec-v1_0.md §10.3. Null on
  // operational decisions; populated for workflow_id === "10-oversight".
  oversight_cycle_id: string | null;
  target_outcome: string | null;
  actual_outcome: string | null;
  outcome_captured_by: string | null;
  // True only for apex decisions in `decided` that haven't yet been
  // ratified by the board. Drives Inbox grouping ("Awaiting board
  // ratification" section) + the new stage-strip tile. P51 Phase 2.
  awaiting_committee_endorsement: boolean;
};

export type DecisionEvent = {
  id: string;
  decision_id: string;
  tenant_id: string;
  workflow_id: string;
  user_id: string | null;
  user_name: string | null;
  user_username: string | null;
  action: string;
  old_status: string | null;
  new_status: string | null;
  comment: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type DecisionAttachment = {
  id: string;
  decision_id: string;
  stage: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  storage_backend: string;
  uploaded_by: string;
  uploaded_at: string | null;
  description: string | null;
  superseded_at: string | null;
};

export type AttachmentStage = "signal" | "decision" | "action" | "outcome" | "evidence";
export type StageContext = "signal" | "decision" | "action" | "outcome" | "general";
export type EventInclude = "audit" | "comments" | "all";

export type DecisionListParams = {
  scope?: DecisionScope;
  density?: DecisionDensity;
  stage?: DecisionStage;
  workflow_id?: string;
  archetype?: string;
  sort?: DecisionSort;
  limit?: number;
  offset?: number;
};

export type DecisionListResponse = {
  items: Decision[];
  total: number;
  limit: number;
  offset: number;
  scope: string;
  density: string;
  stage: string | null;
  workflow_id: string | null;
  archetype: string | null;
  sort: string;
};

// ─── Calls ────────────────────────────────────────────────────────────────

function toQuery(params: DecisionListParams): string {
  const sp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      sp.set(key, String(value));
    }
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export function listDecisions(
  params: DecisionListParams = {},
): Promise<DecisionListResponse> {
  return apiFetch<DecisionListResponse>(`/api/decisions${toQuery(params)}`);
}

export function getDecision(decisionId: string): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}`);
}

export function getDecisionEvents(
  decisionId: string,
  include: EventInclude = "audit",
): Promise<{ items: DecisionEvent[] }> {
  const q = include !== "audit" ? `?include=${include}` : "";
  return apiFetch<{ items: DecisionEvent[] }>(
    `/api/decisions/${decisionId}/events${q}`,
  );
}

export function claimDecision(decisionId: string): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/claim`, {
    method: "POST",
  });
}

export type FinalizeBody = {
  selected_option: string;
  rationale: string;
  evidence_refs?: unknown[];
  alternatives?: unknown[];
};

export function finalizeDecision(
  decisionId: string,
  body: FinalizeBody,
): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/finalize`, {
    method: "POST",
    body,
  });
}

export function deferDecision(
  decisionId: string,
  body: { reason: string; reopen_at?: string },
): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/defer`, {
    method: "POST",
    body,
  });
}

export function escalateDecision(
  decisionId: string,
  body: { reason: string; escalated_to?: string },
): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/escalate`, {
    method: "POST",
    body,
  });
}

// ─── Phase 7.5 Gate 4 — manual creation ───────────────────────────────────

export type CreateDecisionBody = {
  workflow_id: string;
  decision_type: string;
  title: string;
  description?: string;
  priority?: DecisionPriority;
  sla_hours?: number;
  owner_id?: string;
  trigger_data?: Record<string, unknown>;
  signal_summary?: string;
  decision_payload?: Record<string, unknown>;
  tags?: string[];
};

export function createDecision(body: CreateDecisionBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions`, { method: "POST", body });
}

// ─── Phase 7.5 Gate 5 — PATCH stage edits ─────────────────────────────────
//
// Each PATCH writes a stage_edit event; the manager validates stage-readiness
// and authority. signal_source is immutable post-creation and rejected.

export type PatchSignalBody = {
  signal_summary?: string;
  trigger_data?: Record<string, unknown>;
};

export function patchSignal(decisionId: string, body: PatchSignalBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/signal`, {
    method: "PATCH",
    body,
  });
}

export type PatchDecisionBody = {
  selected_option?: string;
  alternatives?: unknown[];
  evidence_refs?: unknown[];
  rationale?: string;
};

export function patchDecisionStage(
  decisionId: string,
  body: PatchDecisionBody,
): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/decision`, {
    method: "PATCH",
    body,
  });
}

export type PatchActionBody = {
  action_started_at?: string;
  action_completed_at?: string;
  action_artifacts?: unknown[];
};

export function patchAction(decisionId: string, body: PatchActionBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/action`, {
    method: "PATCH",
    body,
  });
}

export type PatchOutcomeBody = {
  outcome_text?: string;
  outcome_impact?: "positive" | "neutral" | "negative";
  outcome_metrics?: Record<string, unknown>;
};

export function patchOutcome(decisionId: string, body: PatchOutcomeBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/outcome`, {
    method: "PATCH",
    body,
  });
}

// ─── POST stage transitions (record action / outcome) ─────────────────────

export type RecordActionBody = {
  started_at?: string;
  completed_at?: string;
  artifacts?: unknown[];
};

export function recordAction(decisionId: string, body: RecordActionBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/action`, {
    method: "POST",
    body,
  });
}

export type RecordOutcomeBody = {
  outcome_text: string;
  outcome_impact?: "positive" | "neutral" | "negative";
  outcome_metrics?: Record<string, unknown>;
};

export function recordOutcome(decisionId: string, body: RecordOutcomeBody): Promise<Decision> {
  return apiFetch<Decision>(`/api/decisions/${decisionId}/outcome`, {
    method: "POST",
    body,
  });
}

// ─── Phase 7.5 Gate 7 — attachments ───────────────────────────────────────

export function listAttachments(
  decisionId: string,
): Promise<{ items: DecisionAttachment[] }> {
  return apiFetch<{ items: DecisionAttachment[] }>(
    `/api/decisions/${decisionId}/attachments`,
  );
}

export async function uploadAttachment(
  decisionId: string,
  file: File,
  stage: AttachmentStage = "evidence",
  description?: string,
): Promise<DecisionAttachment> {
  // Multipart upload bypasses the JSON apiFetch wrapper — let the browser set
  // its own Content-Type with the correct boundary.
  const fd = new FormData();
  fd.append("file", file);
  fd.append("stage", stage);
  if (description) fd.append("description", description);

  const resp = await fetch(`/api/decisions/${decisionId}/attachments`, {
    method: "POST",
    credentials: "include",
    body: fd,
  });
  const text = await resp.text();
  let parsed: unknown = null;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }
  if (!resp.ok) {
    throw new ApiError(resp.status, parsed);
  }
  return parsed as DecisionAttachment;
}

export function deleteAttachment(
  decisionId: string,
  attachmentId: string,
): Promise<{ superseded: true; attachment_id: string }> {
  return apiFetch(`/api/decisions/${decisionId}/attachments/${attachmentId}`, {
    method: "DELETE",
  });
}

// The /download endpoint either streams the bytes directly (local backend)
// or returns a 302 redirect to a presigned URL (do_spaces backend). In both
// cases <a href={attachmentDownloadUrl(...)} target="_blank"> Just Works —
// the browser follows the redirect and renders the PDF.
export function attachmentDownloadUrl(decisionId: string, attachmentId: string): string {
  return `/api/decisions/${decisionId}/attachments/${attachmentId}/download`;
}

// ─── Phase 7.5 Gate 7 — comments ──────────────────────────────────────────

export type CreateCommentBody = {
  body: string;
  stage_context?: StageContext;
  mentions?: string[];
};

export function createComment(
  decisionId: string,
  body: CreateCommentBody,
): Promise<DecisionEvent> {
  return apiFetch<DecisionEvent>(`/api/decisions/${decisionId}/comments`, {
    method: "POST",
    body,
  });
}

// ─── Phase 8.5 — bulk decision operations ────────────────────────────────

export type BulkResult = {
  decision_id: string;
  ok: boolean;
  error?: string;
};

export type BulkResponse = {
  bulk_operation_id: string;
  results: BulkResult[];
  succeeded: number;
  failed: number;
};

export function bulkClaim(decisionIds: string[]): Promise<BulkResponse> {
  return apiFetch<BulkResponse>(`/api/decisions/bulk/claim`, {
    method: "POST",
    body: { decision_ids: decisionIds },
  });
}

export function bulkComment(
  decisionIds: string[],
  body: string,
): Promise<BulkResponse> {
  return apiFetch<BulkResponse>(`/api/decisions/bulk/comment`, {
    method: "POST",
    body: { decision_ids: decisionIds, body },
  });
}
