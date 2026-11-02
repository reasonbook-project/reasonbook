// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

/**
 * Archetype summary returned by `/api/archetypes`.
 *
 * The list comes back in fixed Caseload display order; the `position`
 * field carries 1..7 so the rail can render the `01..07` mono-eyebrow
 * numbers the same way the legacy entitled-workflow rail did.
 *
 * `family` is multi-valued because `payment_authorization` and
 * `adverse_action` span grant / entitlement / procurement.
 */
export type Archetype = {
  id: string;
  name: string;
  description: string | null;
  family: ("grant" | "entitlement" | "procurement")[];
  flow: "forward" | "reverse";
  decision_basis: "review" | "eligibility_rules" | "formula" | "authorization";
  promotes: "every_case" | "on_trigger";
  position: number;
};

export type ArchetypeListResponse = { archetypes: Archetype[] };

export function listArchetypes(): Promise<ArchetypeListResponse> {
  return apiFetch<ArchetypeListResponse>("/api/archetypes");
}
