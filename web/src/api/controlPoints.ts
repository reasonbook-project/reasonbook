// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type ControlPointStatus = "pending" | "cleared" | "skipped" | "missed";
export type ControlPointTier = "federal" | "state" | "recipient";
export type ControlPointGateType = "gate" | "notify";

export type ControlPoint = {
  id: string;
  tenant_id: string;
  matter_id: string;
  node_id: string;
  tier: ControlPointTier;
  archetype_id: string;
  trigger_event: string;
  gate_type: ControlPointGateType;
  required_authority_role: string | null;
  status: ControlPointStatus;
  cleared_by_decision_id: string | null;
  cleared_by_user_id: string | null;
  cleared_at: string | null;
  named_gap_reason: string | null;
  created_at: string;
  updated_at: string;
};

export type ControlPointCounts = {
  pending: number;
  cleared: number;
  skipped: number;
  missed: number;
  total: number;
};

export type ControlPointListResponse = {
  items: ControlPoint[];
  counts: ControlPointCounts;
};

export type MarkGapBody = {
  reason: string;
  decision_id: string;
};

export type MarkGapResponse = {
  control_point: ControlPoint;
};

export function listControlPoints(matterId: string): Promise<ControlPointListResponse> {
  return apiFetch<ControlPointListResponse>(`/api/matters/${matterId}/control-points`);
}

export function postMarkGap(
  controlPointId: string,
  body: MarkGapBody,
): Promise<MarkGapResponse> {
  return apiFetch<MarkGapResponse>(`/api/control-points/${controlPointId}/mark-gap`, {
    method: "POST",
    body,
  });
}
