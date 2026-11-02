// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

/**
 * Matter aggregate per TENANCY-MODEL.md §11 / ADR-11. The matter IS the
 * Register matter — there's no separate matter table.
 */
export type MatterNode = {
  id: string;
  tier: "federal" | "state" | "recipient";
  parent_node_id: string | null;
  participant_org_id: string | null;
  participant_org_name: string | null;
  participant_org_code: string | null;
  active_archetypes: string[];
  authority_role: string;
  added_at: string | null;
  removed_at: string | null;
  /** Dollar amount that arrived AT this node. NULL when not known
   *  (synthetic matters; sub-edges in the v1 matters loader). */
  amount: string | null;
};

export type PathPreviewNode = {
  tier: "federal" | "state" | "recipient";
  label: string;
  amount: string | null;
};

/** Highest-severity open alert linked to a matter. Null when the
 *  matter has no open alerts. `kind` is the signal_ref.kind from the
 *  alert (e.g. "tier_skip"); `skipped_tier` / `expected_parent` are
 *  set when kind === "tier_skip". */
export type MatterSignal = {
  alert_id: string;
  /** Broad category from the alert.source column — e.g. "tier_skip",
   *  "identity", "flow_graph", "fraud_risk_screening". Used to pick
   *  the attribution rule in fund-flow visual-rules.md. */
  source: string | null;
  /** Specific catalog id from signal_ref.kind — e.g. "tier_skip",
   *  "ssn_multiple_claimants", "phantom_subrecipient". */
  kind: string | null;
  severity: "critical" | "high" | "medium" | "low" | string;
  title: string;
  body: string | null;
  skipped_tier: string | null;
  expected_parent: string | null;
  /** Participant node this signal attributes to (identity + per-node
   *  signals). Matches `MatterNode.participant_org_id`. Null when the
   *  signal doesn't name a specific participant. */
  subject_participant_org_id: string | null;
};

export type MatterSummary = {
  id: string;
  program_id: string;
  federal_archetype: string;
  awarding_agency: string;
  amount_obligated: string | null;
  period_label: string | null;
  terms: string | null;
  retention_months: number | null;
  planned_disbursement_at: string | null;
  originating_decision_id: string | null;
  created_at: string | null;
  node_count: number | null;
  /** Denormalised federal → state → recipient walk for the Register's
   *  compact path render. 1–3 nodes in flow order. */
  path_preview: PathPreviewNode[];
  /** Every recipient display_name on the matter (prime + all subs) —
   *  search hay so a sub name finds the matter even when the chip
   *  shows the prime. */
  search_labels: string[];
  /** Additional search-only strings (e.g. decision numbers on the
   *  matter) — extends the client-side hay but is NOT used to render
   *  the tree label. */
  search_terms?: string[];
  /** Highest-severity open alert, or null when clean. Equal to
   *  `signals[0] ?? null`. */
  signal: MatterSignal | null;
  /** All open signals on the matter, highest-severity first. Powers
   *  per-element fund-flow attribution per
   *  docs/architecture/fund-flow-visual-rules.md. Empty when clean. */
  signals: MatterSignal[];
  /** Batch-derived stage — priority order:
   *   `awaiting_response` → `in_progress` → `awaiting_owner` → `cleared`.
   *   Powers the Matters-rail Stage facet + the leaf's stage dot.
   *   Nullable when the endpoint didn't compute it (e.g. POST create). */
  stage?: "awaiting_owner" | "in_progress" | "awaiting_response" | "cleared" | null;
  /** Owner of the current in-progress/assigned decision (or earliest
   *  owned decision, if none active). Falls back to null when the
   *  matter has no owned decisions yet. */
  owner_id?: string | null;
  owner_name?: string | null;
  /** Number of Decisions on this matter with is_commitment=true.
   *  Powers the recipient watchlist's Awaiting/Recently-submitted
   *  partition without a second round-trip. Defaults to 0 for older
   *  API versions that don't yet return this field. */
  commitment_count?: number;
};

export type MatterOriginatingDecision = {
  id: string;
  decision_number: string;
  status: string;
  title: string;
};

/** One decision record on a matter. Matters hold a collection of these
 *  (see SURFACE-USER-STORIES.md — "a matter is the collection of
 *  decision records and supporting metadata for the fund-flow of a
 *  matter"). The `is_originating` flag marks the federal-tier
 *  originating decision; the rest are amendments, investigations,
 *  per-node decisions, etc. */
export type MatterDecision = {
  id: string;
  decision_number: string;
  decision_type: string;
  status: string;
  title: string;
  priority: string;
  created_at: string | null;
  decided_at: string | null;
  selected_option: string | null;
  outcome_text: string | null;
  is_originating: boolean;
  matter_node_id: string | null;
  /** Classifies the decision for the UI panel:
   *  - "tier_accept" → tier-acceptance (state / recipient / sub accept)
   *  - "federal_seed_dev" / null on originating → federal-tier originating
   *  - "alert.flow_graph.*" → investigation triggered by a signal
   *  - "manual" → authority action / amendment
   */
  signal_source: string | null;
  /** JSON evidence entries — typically {kind, ref} objects. Drives the
   *  composite card's Evidence chip + drawer. Nullable on legacy rows. */
  evidence_refs: Array<{ kind: string; ref: string }> | null;
  /** True when this Decision was written via the recipient/state
   *  response endpoint — a legally-binding commitment (spec §6). */
  is_commitment?: boolean;
  /** Party (recipient / state) that submitted the commitment. Only
   *  meaningful when is_commitment=true. Phase-A becomes a real FK
   *  into the parties table. */
  originating_party_name?: string | null;
  /** Structured response payload — attestations, signatory info,
   *  prompt type. Powers the Commitment integrity card. */
  response_shape?: {
    prompt_type?: string;
    accepted?: string;
    exceptions?: string | null;
    signatory_name?: string;
    signatory_title?: string;
    attestations?: string[];
    attachments?: unknown[];
    [k: string]: unknown;
  } | null;
  /** RFR reference (Phase A0 text stand-in for the FK that lands with
   *  the requests_for_response table). */
  in_response_to?: string | null;
};

export type Matter = MatterSummary & {
  nodes: MatterNode[];
  historical_nodes: MatterNode[];
  originating_decision: MatterOriginatingDecision | null;
  /** Every decision linked to this matter, in chronological order. */
  decisions: MatterDecision[];
};

export type MatterListResponse = { items: MatterSummary[] };

export function listMatters(): Promise<MatterListResponse> {
  return apiFetch<MatterListResponse>("/api/matters");
}

export type MatterMeta = {
  matters: number;
  /** Sum of amount_obligated as a string (Decimal-safe). */
  exposure: string;
  signals: number;
};

export function getMatterMeta(): Promise<MatterMeta> {
  return apiFetch<MatterMeta>("/api/matters/meta");
}

/* ─── Matters-first Inbox ────────────────────────────────────────────── */

export type MatterInboxBand = "incoming" | "inflight" | "at_risk";
export type MatterInboxHorizon = "30d" | "90d" | "fy";
export type MatterInboxScope = "mine" | "team" | "all_agency";

export type MatterReadiness = {
  state: "ready" | "pending";
  pending_count: number;
};

export type MatterRiskReason = {
  kind: string | null;
  text: string;
};

export type MatterInboxRow = MatterSummary & {
  band: MatterInboxBand;
  /** Incoming-only: Ready / N pending pill. */
  readiness?: MatterReadiness;
  /** Inflight-only: which stage pill to render. */
  stage?: "decision" | "action" | "outcome";
  owner_id?: string | null;
  owner_name?: string | null;
  oldest_open_age_days?: number;
  lead_decision_title?: string;
  /** At-risk-only: structured reason line + age. */
  risk_reason?: MatterRiskReason;
  risk_age_days?: number;
};

export type MatterInboxResponse = {
  horizon: MatterInboxHorizon;
  horizon_end: string;
  band_counts: Record<MatterInboxBand, number>;
  program_counts: Record<string, number>;
  bands: Record<MatterInboxBand, MatterInboxRow[]>;
};

export type MatterInboxParams = {
  scope?: MatterInboxScope;
  horizon?: MatterInboxHorizon;
  program?: string;
};

export function getMattersInbox(
  params: MatterInboxParams = {},
): Promise<MatterInboxResponse> {
  const qs = new URLSearchParams();
  if (params.scope) qs.set("scope", params.scope);
  if (params.horizon) qs.set("horizon", params.horizon);
  if (params.program) qs.set("program", params.program);
  const suffix = qs.toString();
  return apiFetch<MatterInboxResponse>(
    `/api/matters/inbox${suffix ? `?${suffix}` : ""}`,
  );
}

/* ─── Recipient response (external-party commitment) ────────────────── */

export type RecipientResponseShape = {
  prompt_type: "accept_scope";
  accepted: "as_issued" | "with_exceptions" | "declined";
  exceptions: string | null;
  signatory_name: string;
  signatory_title: string;
  attestations: string[];
  attachments: unknown[];
};

export type RecipientResponseInput = {
  originating_party_name: string;
  in_response_to?: string | null;
  response_shape: RecipientResponseShape;
};

export type RecipientResponseResult = {
  id: string;
  decision_number: string;
  matter_id: string;
  is_commitment: true;
  originating_party_name: string;
  in_response_to: string | null;
  response_shape: RecipientResponseShape;
  decided_at: string | null;
  title: string;
  status: string;
};

/* ─── Matter claim (take over the whole case file) ───────────────── */

export type ClaimMatterResult = {
  matter_id: string;
  bulk_operation_id: string;
  claimed: string[];
  transferred: string[];
  skipped_already_mine: string[];
  total_touched: number;
};

export function claimMatter(matterId: string): Promise<ClaimMatterResult> {
  return apiFetch<ClaimMatterResult>(`/api/matters/${matterId}/claim`, {
    method: "POST",
  });
}

export function submitRecipientResponse(
  matterId: string,
  input: RecipientResponseInput,
): Promise<RecipientResponseResult> {
  return apiFetch<RecipientResponseResult>(
    `/api/matters/${matterId}/recipient-response`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
}

export function getMatter(matterId: string): Promise<Matter> {
  return apiFetch<Matter>(`/api/matters/${matterId}`);
}

export type StakeholderSpecInput = {
  participant_org_id: string;
  active_archetypes?: string[];
  authority_role?: string;
};

export type RecipientSpecInput = {
  parent_state_org_id: string;
  participant_org_id: string;
  active_archetypes?: string[];
  authority_role?: string;
};

export type CreateMatterInput = {
  program_id: string;
  awarding_agency: string;
  amount_obligated: string;
  period_label: string;
  terms: string;
  federal_application_ref: string;
  states: StakeholderSpecInput[];
  recipients: RecipientSpecInput[];
};

export function createMatter(input: CreateMatterInput): Promise<MatterSummary> {
  return apiFetch<MatterSummary>("/api/matters", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
}

export type ParticipantOrg = {
  id: string;
  kind: "state" | "recipient";
  display_name: string;
  code: string | null;
};

export type ParticipantOrgListResponse = { items: ParticipantOrg[] };

export function listParticipantOrgs(
  kind?: "state" | "recipient",
): Promise<ParticipantOrgListResponse> {
  const qs = kind ? `?kind=${kind}` : "";
  return apiFetch<ParticipantOrgListResponse>(`/api/participant_orgs${qs}`);
}

export type Agency = {
  id: string;
  slug: string;
  display_name: string;
  source: string;
};

export type AgencyListResponse = { agencies: Agency[]; count: number };

export function listAgencies(q?: string): Promise<AgencyListResponse> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : "";
  return apiFetch<AgencyListResponse>(`/api/catalog/agencies${qs}`);
}

/* ─── Requests-For-Response (RFR) ────────────────────────────────────── */

export type RfrStatus = "open" | "resolved" | "superseded";

export type RfrRow = {
  id: string;
  rfr_number: string;
  matter_id: string;
  matter_node_id: string | null;
  originating_decision_id: string | null;
  target_party_name: string;
  prompt_type: string;
  prompt_body: string;
  due_at: string | null;
  status: RfrStatus;
  resolved_by_decision_id: string | null;
  resolved_at: string | null;
  issued_by_user_id: string | null;
  created_at: string | null;
  /** Present on cross-matter list responses only — matter metadata
   *  the watchlist needs to render party context without a per-row
   *  round-trip. */
  matter?: {
    id: string;
    awarding_agency: string;
    program_id: string;
    period_label: string | null;
  };
};

export type RfrListResponse = { items: RfrRow[] };

export function listMatterRfrs(
  matterId: string,
  status: RfrStatus | "all" = "open",
): Promise<RfrListResponse> {
  const qs = status === "all" ? "?status=all" : `?status=${status}`;
  return apiFetch<RfrListResponse>(`/api/matters/${matterId}/rfrs${qs}`);
}

export type ChainEvent = {
  event_id: string;
  ts: string | null;
  action: string;
  summary: string;
  decision_number: string | null;
  actor_name: string | null;
  hash: string;
  prev_hash: string;
};

export type MatterChainResponse = {
  matter_id: string;
  head_hash: string | null;
  prev_hash: string | null;
  genesis_hash: string;
  event_count: number;
  verified: boolean;
  events: ChainEvent[];
};

export function getMatterChain(
  matterId: string,
): Promise<MatterChainResponse> {
  return apiFetch<MatterChainResponse>(
    `/api/integrity/matters/${matterId}/chain`,
  );
}

export function listRfrs(
  params: { status?: RfrStatus | "all"; party?: string } = {},
): Promise<RfrListResponse> {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.party) q.set("party", params.party);
  const suffix = q.toString();
  return apiFetch<RfrListResponse>(`/api/rfrs${suffix ? `?${suffix}` : ""}`);
}
