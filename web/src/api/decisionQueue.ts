// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Decision queue API client (P17).
 *
 * Talks to ``GET /api/decisions/queue`` — the slim sibling of
 * ``GET /api/decisions`` purpose-built for the dashboard drawer. Returns
 * one row per at-risk-or-open decision in the institution, scoped to the
 * caller's entitled workflows (apex excluded). Sorted SLA-deadline
 * ascending so the most urgent decision is row 1.
 *
 * Empty-state contract: when ``status=at_risk`` and ``filtered_count`` is
 * zero, the response includes ``posture_context`` — three stats that power
 * the drawer's "All clear" body. Otherwise that key is absent.
 */

import { apiFetch } from "./client";

export type QueueStatus = "at_risk" | "open";
export type QueueCategory = "credit" | "compliance" | "ops";

export type QueueFilter = {
  status: QueueStatus;
  category?: QueueCategory;
};

export type QueueAssignee = {
  id: string;
  name: string;
  initials: string;
};

export type QueueDecision = {
  id: string;
  decision_number: string;
  workflow_id: string;
  /** Mapped via the shared ``AT_RISK_CATEGORY_BY_WORKFLOW`` table; null for
   *  workflows outside the credit/compliance/ops grouping (no such workflow
   *  ships at the moment, but the field is nullable for future-proofing). */
  category: QueueCategory | null;
  title: string;
  /** Full description, rendered in the row's hover popover so a CRO can
   *  read the context without clicking through to the detail page. Null
   *  on bare-bones decisions; the popover degrades to title-only. */
  description: string | null;
  sla_deadline: string | null;
  sla_status: string | null;
  status: string;
  assignee: QueueAssignee | null;
};

export type PostureContext = {
  open_count: number;
  /** Mean (decided_at - created_at) in days over the trailing 30 days.
   *  Null when no decisions have been resolved in the window. */
  avg_cycle_days: number | null;
  /** Open decisions with SLA in the (now+24h, now+48h] window — i.e. the
   *  next batch to watch after the current at-risk set clears. */
  upcoming_count_48h: number;
};

export type QueueResponse = {
  decisions: QueueDecision[];
  /** Total matching ``status`` without applying the optional category
   *  filter. Lets the UI render "10 of 65" framing. */
  total_count: number;
  /** Total matching ``status`` AND ``category``. ``filtered_count <= total_count``. */
  filtered_count: number;
  next_cursor: string | null;
  status: QueueStatus;
  category: QueueCategory | null;
  /** Present only when ``status=at_risk`` and ``filtered_count=0``. */
  posture_context?: PostureContext;
};

export async function getDecisionQueue(
  filter: QueueFilter,
  options: { limit?: number; offset?: number } = {},
): Promise<QueueResponse> {
  const params = new URLSearchParams({ status: filter.status });
  if (filter.category) params.set("category", filter.category);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  return apiFetch<QueueResponse>(`/api/decisions/queue?${params.toString()}`);
}
