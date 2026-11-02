// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type WeeklyOpenedPoint = {
  /** ISO date (YYYY-MM-DD) of the Monday anchoring the week. */
  week_starting: string;
  opened_count: number;
};

export type DashboardWorkflowSummary = {
  workflow_id: string;
  workflow_name: string;
  color: string | null;
  open_count: number;
  decided_count: number;
  at_risk_count: number;
  /** 4 entries oldest→newest. Powers an inline SVG sparkline. */
  trend: WeeklyOpenedPoint[];
};

export type DailyOpenPoint = {
  /** ISO date (YYYY-MM-DD). */
  day: string;
  open_count: number;
};

export type AtRiskBreakdownEntry = {
  /** Strategic-domain category: "credit" | "compliance" | "ops". */
  label: string;
  count: number;
};

export type DashboardTotals = {
  open: number;
  decided: number;
  at_risk: number;
  /** New decisions created in trailing 24h, still in an open status. */
  open_delta_24h: number;
  /** Signed change: decided in trailing 24h MINUS decided in 24–48h prior. */
  decided_delta_24h: number;
  /** Currently at-risk decisions (sla_deadline ∈ now..now+24h, not closed/deferred). */
  at_risk_delta_24h: number;
  /** Mean cycle days for decisions decided in trailing 30 days, or null when empty. */
  decided_avg_cycle_days: number | null;
  /** At-risk category breakdown sorted desc by count, empty buckets dropped. */
  at_risk_breakdown: AtRiskBreakdownEntry[];
};

export type DashboardOperational = {
  by_workflow: DashboardWorkflowSummary[];
  totals: DashboardTotals;
  /** 7 daily open-count snapshots oldest→newest. Powers the OPEN tile sparkline. */
  open_trend: DailyOpenPoint[];
};

export type DashboardApexOpenDecision = {
  decision_id: string;
  decision_number: string;
  title: string;
  decision_type: string;
  owner_name: string | null;
};

export type DashboardApexCycle = {
  id: string;
  name: string;
  cycle_end: string | null;
  open_count: number;
  /**
   * First N in-flight decisions in this cycle, ordered SLA-deadline
   * ascending. Capped server-side (_CYCLE_OPEN_DECISIONS_LIMIT = 5);
   * anything past the cap surfaces via `open_decisions_more`.
   */
  open_decisions: DashboardApexOpenDecision[];
  /** Count of in-flight decisions not inlined above. 0 when all fit. */
  open_decisions_more: number;
};

export type DashboardApexDomain = {
  domain_id: string;
  name: string;
  primary_owner_role: string | null;
  open_count: number;
};

export type DashboardApex = {
  open_decisions_count: number;
  open_by_domain: DashboardApexDomain[];
  current_cycle: DashboardApexCycle | null;
};

export type DashboardRecentOutcome = {
  decision_id: string;
  decision_number: string;
  title: string;
  workflow_id: string;
  workflow_name: string;
  workflow_color: string | null;
  outcome_recorded_at: string | null;
};

export type DashboardResponse = {
  tenant: { id: string; name: string };
  operational: DashboardOperational;
  apex: DashboardApex;
  recent_outcomes: DashboardRecentOutcome[];
};

export function getDashboard(): Promise<DashboardResponse> {
  return apiFetch<DashboardResponse>("/api/dashboard");
}
