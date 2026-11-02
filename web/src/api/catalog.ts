// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type CatalogEntryType =
  | "metric"
  | "alert"
  | "persona"
  | "decision_type"
  | "archetype"
  | "program";

export type WhoWatches =
  | "agency_head"
  | "oig"
  | "program_officer"
  | "caseworker"
  | "certifying_officer"
  | "program_monitor"
  | "state_administrator"
  | "engineer";

export type CatalogTier = "federal" | "state" | "recipient" | "cross_tier";

export type CatalogDomain =
  | "governance"
  | "payment_integrity"
  | "eligibility"
  | "oversight_response"
  | "appropriations"
  | "integrity"
  | "subrecipient_oversight"
  | "program_design";

export type Direction = "higher_is_better" | "lower_is_better" | "neutral";

export type CatalogEntry = {
  type: CatalogEntryType;
  id: string;
  name: string;
  meaning: string | null;
  why_it_matters: string | null;
  owner: string | null;
  who_watches: WhoWatches;
  tier: CatalogTier;
  domain: CatalogDomain;
  workflow_id: string | null;
  workflow_name: string | null;
  direction: Direction | null;
  severity: string | null;
  plain_thresholds: string | null;
  technical: Record<string, unknown>;
};

export type CatalogResponse = {
  entries: CatalogEntry[];
  count: number;
};

export function listCatalog(): Promise<CatalogResponse> {
  return apiFetch<CatalogResponse>("/api/catalog/entries");
}

// ── Display labels for the closed-enum facet values ─────────────────────
export const WHO_WATCHES_LABEL: Record<WhoWatches, string> = {
  agency_head: "Agency head",
  oig: "OIG",
  program_officer: "Program officer",
  caseworker: "Caseworker",
  certifying_officer: "Certifying officer",
  program_monitor: "Program monitor",
  state_administrator: "State administrator",
  engineer: "Engineer",
};

export const TIER_LABEL: Record<CatalogTier, string> = {
  federal: "Federal",
  state: "State",
  recipient: "Recipient",
  cross_tier: "Cross-tier",
};

export const DOMAIN_LABEL: Record<CatalogDomain, string> = {
  governance: "Governance",
  payment_integrity: "Payment integrity",
  eligibility: "Eligibility",
  oversight_response: "Oversight response",
  appropriations: "Appropriations",
  integrity: "Program integrity",
  subrecipient_oversight: "Subrecipient oversight",
  program_design: "Program design",
};

export const TYPE_LABEL: Record<CatalogEntryType, string> = {
  metric: "Metric",
  alert: "Alert",
  persona: "Persona",
  decision_type: "Decision type",
  archetype: "Playbook",
  program: "Program",
};

export const DIRECTION_LABEL: Record<Direction, string> = {
  higher_is_better: "higher is better",
  lower_is_better: "lower is better",
  neutral: "neutral",
};
