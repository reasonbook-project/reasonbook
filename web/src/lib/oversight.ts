// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Apex-decision presentation helpers. Pure functions so they're trivial to
 * test and to reuse outside the Decision Detail route (control room, dashboard
 * apex section, future cycle dossier preview).
 */

import type { Decision } from "@/api/decisions";
import type { BoardCycle } from "@/api/oversight";

export const OVERSIGHT_WORKFLOW_ID = "10-oversight" as const;

export function isOversightDecision(d: Pick<Decision, "workflow_id"> | undefined): boolean {
  return d?.workflow_id === OVERSIGHT_WORKFLOW_ID;
}

function fmtDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

/**
 * Editorial tagline shown below the apex decision title.
 *
 * Per design system §5.5 the tagline is the editorial flourish — one line,
 * italic, present-tense for in-flight decisions, past-tense once decided.
 * Returns null when the decision has no useful tagline (e.g. operational).
 */
export function oversightTagline(
  decision: Pick<
    Decision,
    | "outcome_recorded_at"
    | "decided_at"
    | "status"
    | "oversight_cycle_id"
  >,
  cycle: Pick<BoardCycle, "name" | "cycle_end" | "status"> | null,
): string | null {
  if (decision.outcome_recorded_at) {
    return `Outcome recorded ${fmtDate(decision.outcome_recorded_at)}.`;
  }
  if (decision.decided_at) {
    return `Decided ${fmtDate(decision.decided_at)}.`;
  }
  if (decision.status === "deferred") {
    return cycle ? `Deferred — ${cycle.name}.` : "Deferred to next cycle.";
  }
  if (cycle) {
    const cycleEnd = fmtDate(cycle.cycle_end);
    if (cycle.status === "concluded") {
      return `${cycle.name} concluded.`;
    }
    return cycleEnd ? `${cycle.name} closes ${cycleEnd}.` : `${cycle.name} in flight.`;
  }
  return null;
}
