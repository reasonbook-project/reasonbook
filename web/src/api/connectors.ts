// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type ConnectorStatus = "connected" | "degraded" | "disconnected";

export type Connector = {
  id: string;
  slug: string;
  name: string;
  source: string;
  description: string | null;
  status: ConnectorStatus;
  last_sync_at: string | null;
  last_sync_record_count: number | null;
  window_start: string | null;
  window_end: string | null;
  filter_label: string | null;
  next_sync_at: string | null;
  schedule_label: string | null;
  integrity_verified: boolean;
  integrity_verified_at: string | null;
  feeds_workflow_ids: string[];
};

export type ConnectorRunStatus = "in_progress" | "success" | "failure";

export type ConnectorRun = {
  id: string;
  connector_id: string;
  run_type: string;
  status: ConnectorRunStatus;
  started_at: string;
  completed_at: string | null;
  filters_json: Record<string, unknown> | null;
  window_start: string | null;
  window_end: string | null;
  record_count: number | null;
  error_message: string | null;
  hash_chain_head: string | null;
};

export type ConnectorListResponse = { items: Connector[] };
export type ConnectorRunListResponse = { items: ConnectorRun[] };

export type SyncResponse = {
  run_id: string;
  status: ConnectorRunStatus;
  started_at: string;
  completed_at: string | null;
  record_count: number | null;
};

export function listConnectors(): Promise<ConnectorListResponse> {
  return apiFetch<ConnectorListResponse>("/api/connectors");
}

export function listConnectorRuns(
  connectorId: string,
): Promise<ConnectorRunListResponse> {
  return apiFetch<ConnectorRunListResponse>(
    `/api/connectors/${connectorId}/runs`,
  );
}

export function syncConnector(connectorId: string): Promise<SyncResponse> {
  return apiFetch<SyncResponse>(`/api/connectors/${connectorId}/sync`, {
    method: "POST",
    body: {},
  });
}
