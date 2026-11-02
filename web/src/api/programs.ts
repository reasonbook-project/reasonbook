// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

/**
 * Program profile returned by `/api/programs` — the Tier-3 layer that
 * binds an archetype and fills its profile_required slots.
 */
export type ProgramTierDefaults = {
  active_archetypes: string[];
  authority_role: string | null;
};

export type ProgramHeartbeat = {
  state_pickup_days: number | null;
  state_pickup_severity: "critical" | "high" | "medium" | "low";
  recipient_draw_days: number | null;
  recipient_draw_severity: "critical" | "high" | "medium" | "low";
  outcome_rollup_days: number | null;
  outcome_rollup_severity: "critical" | "high" | "medium" | "low";
  alert_cascade_hours: Record<string, number> | null;
};

export type Program = {
  id: string;
  name: string;
  display_name: string | null;
  awarding_agency: string | null;
  federal_archetype: string | null;
  binds_archetype: string;
  binds_archetype_name: string;
  definition_quality: "clear" | "ambiguous" | "lacks_definition";
  defaults: {
    federal: ProgramTierDefaults;
    state: ProgramTierDefaults;
    recipient: ProgramTierDefaults;
  };
  heartbeat: ProgramHeartbeat;
  retention_months: number | null;
};

export type ProgramListResponse = { programs: Program[] };

export function listPrograms(): Promise<ProgramListResponse> {
  return apiFetch<ProgramListResponse>("/api/programs");
}
