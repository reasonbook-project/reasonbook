// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { DecisionStatus } from "@/api/decisions";

/**
 * Mirrors the backend's EDITABLE_STAGES table in
 * dgp/decisions/manager.py. Stage N is editable when the decision has
 * reached stage N (or beyond) — earlier stages remain editable for
 * post-hoc corrections.
 *
 * Authority is enforced server-side; the UI surfaces edit affordances
 * based on stage-status alone and lets a 403 propagate as an inline
 * error if the user lacks workflow authority.
 */

const EDITABLE_BY_STAGE: Record<
  "signal" | "decision" | "action" | "outcome",
  Set<DecisionStatus>
> = {
  signal: new Set([
    "open",
    "assigned",
    "in_progress",
    "decided",
    "closed",
    "deferred",
    "escalated",
  ]),
  decision: new Set(["in_progress", "decided", "closed"]),
  action: new Set(["decided", "closed"]),
  outcome: new Set(["closed"]),
};

export type EditableStage = keyof typeof EDITABLE_BY_STAGE;

export function canEditStage(stage: EditableStage, status: DecisionStatus): boolean {
  return EDITABLE_BY_STAGE[stage].has(status);
}
