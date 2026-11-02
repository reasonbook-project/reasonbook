// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Workflow extension registry — the slot pattern from frontend doc §7.
 *
 * The shared Decision Detail spine ships with generic fallback views for
 * every slot. A workflow can override one or more slots by adding its own
 * components and registering them here. When the registry has no entry for
 * a workflow, the generic fallbacks render.
 *
 * Scope: DP-native workflows only. CFI-legacy workflows (03-credit-lending
 * through 09-digital-transformation) were removed in the DG-substrate
 * cleanup — see docs/architecture/backlog/ for the follow-ups on the
 * schema/entitlements side of that scrub.
 */

import type { ComponentType } from "react";

import type { Decision } from "@/api/decisions";

export type EvidenceViewProps = {
  decision: Decision;
};

export type PayloadViewProps = {
  decision: Decision;
};

export type WorkflowExtensions = {
  EvidenceView?: ComponentType<EvidenceViewProps>;
  PayloadView?: ComponentType<PayloadViewProps>;
};

import * as reg from "./01-regulatory-compliance";
import * as oversight from "./10-oversight";

const REGISTRY: Record<string, WorkflowExtensions> = {
  "01-regulatory-compliance": reg.extensions,
  "10-oversight": oversight.extensions,
};

export function workflowExtensions(workflowId: string): WorkflowExtensions {
  return REGISTRY[workflowId] ?? {};
}
