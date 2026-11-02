// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { ApiError, apiFetch } from "./client";

export type WorkflowSummary = {
  id: string;
  name: string;
  description: string;
  icon: string | null;
  color: string | null;
  version: string;
  oversight_contributing: boolean;
  /**
   * Per decision-governance-self-assessment-platform-variant-v1_0.md §8.5.3:
   * absent (or null) on the 10 standard governance workflows tenants buy.
   * Set to 'user_configuration' on workflows that host tenant-level
   * user-configuration decisions (designated respondent for the governance
   * maturity Self-Assessment, future configuration commits) — these workflows are
   * always entitled to every tenant, don't appear in the rail's main
   * entitled-workflows section, and don't have their own control room.
   * Decisions surface in the Inbox via the workflow chip on each row.
   */
  kind?: "user_configuration" | null;
};

export type WorkflowAction = {
  id: string;
  name: string;
  description?: string | null;
  authority_required: string;
  deadline?: string | null;
  impact: "critical" | "high" | "medium" | "low";
};

export type WorkflowDecisionType = {
  id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  priority?: string;
  sla_hours?: number | null;
  default_owner_role?: string | null;
  available_actions: WorkflowAction[];
  outcome_metrics: string[];
  payload_schema?: Record<string, unknown> | null;
  oversight_evidence_eligible: boolean;
  // Phase 7.5 Gate 6 — opt-in to human-originated creation. Default false;
  // ingestion-only types stay unset. authoring_authority_level names a role
  // declared on the workflow's authority_levels (not an ordinal).
  manually_creatable: boolean;
  authoring_authority_level: string | null;
};

export type WorkflowAuthorityLevel = {
  id: string;
  name: string;
  level: number;
  can_approve: string[];
  limits?: Record<string, unknown> | null;
};

export type UploadFieldType =
  | "string"
  | "integer"
  | "float"
  | "boolean"
  | "date";

export type UploadColumn = {
  name: string;
  type: UploadFieldType;
  required: boolean;
  primary_key: boolean;
  description?: string | null;
  example?: unknown;
  min?: number | null;
  max?: number | null;
  max_length?: number | null;
  pattern?: string | null;
  enum?: unknown[] | null;
};

export type UploadSchema = {
  enabled: boolean;
  description?: string | null;
  pipe_table: string;
  dp_engine_path: string;
  formats: ("csv" | "json" | "xlsx")[];
  period_type: "monthly" | "quarterly" | "annual";
  period_format_hint: string;
  columns: UploadColumn[];
};

export type WorkflowConfig = {
  workflow: WorkflowSummary;
  metrics: { id: string; name: string; description?: string | null }[];
  decision_types: WorkflowDecisionType[];
  authority_levels: WorkflowAuthorityLevel[];
  upload?: UploadSchema | null;
  // Other YAML sections — we type the ones the frontend reads.
  [key: string]: unknown;
};

export type UploadValidationError = {
  row: number;
  column: string | null;
  message: string;
};

export type UploadResponse = {
  rows_written: number;
  mode: "direct" | "proxy";
  pipe_table?: string | null;
  dp_engine_status?: number | null;
};

export function listWorkflows(): Promise<{ workflows: WorkflowSummary[] }> {
  return apiFetch<{ workflows: WorkflowSummary[] }>("/api/workflows");
}

export function getWorkflowConfig(workflowId: string): Promise<WorkflowConfig> {
  return apiFetch<WorkflowConfig>(`/api/workflows/${workflowId}/config`);
}

// ─── Sprint 3 — manual upload ─────────────────────────────────────────────

export function uploadSampleUrl(workflowId: string): string {
  return `/api/workflows/${workflowId}/upload/sample.csv`;
}

export function schemaExportUrl(
  workflowId: string,
  format: "yaml" | "json",
): string {
  return `/api/workflows/${workflowId}/schema/export?format=${format}`;
}

/**
 * Aggregated multi-workflow catalog export URL. Pass an empty
 * `workflowIds` to export all the user's entitled workflows; pass a
 * subset to filter. The backend silently drops unentitled or unknown
 * ids per the catalog spec — partial views are expected.
 */
export function catalogExportUrl(
  workflowIds: readonly string[],
  format: "yaml" | "json",
): string {
  const base = `/api/catalog/export?format=${format}`;
  if (workflowIds.length === 0) return base;
  return `${base}&workflow_ids=${workflowIds.join(",")}`;
}

export async function uploadFile(
  workflowId: string,
  file: File,
): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const resp = await fetch(`/api/workflows/${workflowId}/upload`, {
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
  return parsed as UploadResponse;
}
