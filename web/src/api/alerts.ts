// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type AlertSource = "fraud_risk_screening" | "flow_graph" | "identity";
export type AlertSeverity = "critical" | "high" | "medium" | "low";
export type AlertStatus =
  | "new"
  | "triaged"
  | "promoted"
  | "dismissed"
  | "reopened";

export type DispositionAction = "promote" | "dismiss" | "hold" | "reopen";
export type DismissReason =
  | "false_positive"
  | "not_actionable"
  | "duplicate"
  | "resolved_elsewhere";

export type Alert = {
  id: string;
  tenant_id: string;
  source: AlertSource;
  signal_ref: Record<string, unknown>;
  severity: AlertSeverity;
  subject_entity: { kind?: string; id?: string; display_name?: string } & Record<string, unknown>;
  matter_id: string | null;
  fund_flow_ref: string[];
  title: string;
  body: string | null;
  target_program_id: string;
  detected_at: string;
  current_status: AlertStatus;
};

export type AlertDisposition = {
  id: string;
  alert_id: string;
  action: DispositionAction;
  reason_code: DismissReason | null;
  rationale: string;
  actor_user_id: string;
  actor_tier: string;
  resulting_decision_id: string | null;
  resulting_status: AlertStatus;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type AlertCounts = {
  new: number;
  triaged: number;
  promoted: number;
  dismissed: number;
  reopened: number;
  actionable: number;
  /** Actionable alerts with no matter_id — powers the top-bar Alerts
   *  pill and the /signals matcher default view. */
  unattached: number;
};

export type MatterLinkFilter = "attached" | "unattached";

export type AlertListResponse = {
  items: Alert[];
  counts: AlertCounts;
};

export type AlertLifecycleResponse = {
  alert: Alert;
  dispositions: AlertDisposition[];
};

export type DispositionBody = {
  action: DispositionAction;
  rationale: string;
  reason_code?: DismissReason;
  metadata?: Record<string, unknown>;
};

export type DispositionResponse = {
  alert: Alert;
  disposition: AlertDisposition;
  resulting_decision?: {
    id: string;
    decision_number: string | null;
  };
};

export function listAlerts(params?: {
  status?: AlertStatus[];
  source?: AlertSource[];
  matter_link?: MatterLinkFilter;
}): Promise<AlertListResponse> {
  const sp = new URLSearchParams();
  if (params?.status?.length) sp.set("status", params.status.join(","));
  if (params?.source?.length) sp.set("source", params.source.join(","));
  if (params?.matter_link) sp.set("matter_link", params.matter_link);
  const q = sp.toString();
  return apiFetch<AlertListResponse>(`/api/alerts${q ? `?${q}` : ""}`);
}

export function postDisposition(
  alertId: string,
  body: DispositionBody,
): Promise<DispositionResponse> {
  return apiFetch<DispositionResponse>(`/api/alerts/${alertId}/dispositions`, {
    method: "POST",
    body,
  });
}

export function attachAlertToMatter(
  alertId: string,
  matterId: string,
): Promise<{ alert: Alert }> {
  return apiFetch<{ alert: Alert }>(`/api/alerts/${alertId}`, {
    method: "PATCH",
    body: { matter_id: matterId },
  });
}

export function getAlertLifecycle(alertId: string): Promise<AlertLifecycleResponse> {
  return apiFetch<AlertLifecycleResponse>(`/api/alerts/${alertId}/lifecycle`);
}
