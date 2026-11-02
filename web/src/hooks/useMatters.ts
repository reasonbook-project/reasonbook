// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  claimMatter,
  type CreateMatterInput,
  createMatter,
  getMatter,
  getMatterChain,
  getMatterMeta,
  getMattersInbox,
  listAgencies,
  listMatters,
  listMatterRfrs,
  listParticipantOrgs,
  listRfrs,
  type MatterInboxParams,
  type RecipientResponseInput,
  type RfrStatus,
  submitRecipientResponse,
} from "@/api/matters";

/** Read the caller's visible matters (federal sees all; state/recipient
 *  see only matters whose tree includes their participant_org). */
export function useMatters() {
  return useQuery({
    queryKey: ["matters"] as const,
    queryFn: listMatters,
    staleTime: 60 * 1000,
  });
}

/** Read RFRs on a single matter. Powers the case-file "Awaiting
 *  response" row. Defaults to open RFRs; pass "all" to include
 *  resolved + superseded for the audit view. */
export function useMatterRfrs(
  matterId: string | undefined,
  status: RfrStatus | "all" = "open",
) {
  return useQuery({
    queryKey: ["matter", matterId, "rfrs", status] as const,
    queryFn: () => {
      if (!matterId) throw new Error("missing matterId");
      return listMatterRfrs(matterId, status);
    },
    enabled: !!matterId,
    staleTime: 30 * 1000,
  });
}

/** Fetch a matter's slice of the integrity chain — head/prev/genesis
 *  hashes + verified flag + per-event hash pointers. Powers both the
 *  Activity and Integrity drawers. */
export function useMatterChain(matterId: string | undefined) {
  return useQuery({
    queryKey: ["matter", matterId, "chain"] as const,
    queryFn: () => {
      if (!matterId) throw new Error("missing matterId");
      return getMatterChain(matterId);
    },
    enabled: !!matterId,
    staleTime: 30 * 1000,
  });
}

/** Cross-matter RFR list — powers the Recipient Portal watchlist.
 *  Defaults to open RFRs across every matter the caller can see. */
export function useRfrs(
  params: { status?: RfrStatus | "all"; party?: string } = {},
) {
  return useQuery({
    queryKey: ["rfrs", params] as const,
    queryFn: () => listRfrs(params),
    staleTime: 30 * 1000,
  });
}

/** Read a single matter by id. Returns 404 when the id is unknown OR
 *  the caller's tier doesn't grant access (the API surfaces 404 vs 403
 *  per its policy). */
export function useMatter(matterId: string | undefined) {
  return useQuery({
    queryKey: ["matter", matterId] as const,
    queryFn: () => {
      if (!matterId) throw new Error("missing matterId");
      return getMatter(matterId);
    },
    enabled: !!matterId,
    staleTime: 60 * 1000,
    retry: false, // 404 / 403 are terminal; don't keep hammering
  });
}

/** List participant_orgs for the create-matter drawer pickers.
 *  ``kind`` filters to 'state' or 'recipient' when supplied. */
export function useParticipantOrgs(kind?: "state" | "recipient") {
  return useQuery({
    queryKey: ["participant_orgs", kind ?? "all"] as const,
    queryFn: () => listParticipantOrgs(kind),
    staleTime: 5 * 60 * 1000,
  });
}

/** Matters-first Inbox — three bands + rail counts, driven by scope +
 *  horizon + optional program filter. Refetches every 15s so the "in
 *  queue" chip and band counts stay live-feeling without SSE. */
export function useMattersInbox(params: MatterInboxParams) {
  return useQuery({
    queryKey: [
      "matters",
      "inbox",
      params.scope ?? "mine",
      params.horizon ?? "90d",
      params.program ?? null,
    ] as const,
    queryFn: () => getMattersInbox(params),
    staleTime: 10 * 1000,
    refetchInterval: 15 * 1000,
  });
}

/** Aggregate counts for the Register meta bar. */
export function useMatterMeta() {
  return useQuery({
    queryKey: ["matters", "meta"] as const,
    queryFn: getMatterMeta,
    staleTime: 30 * 1000,
  });
}

/** Federal agency catalog for the create-matter awarding_agency typeahead.
 *  Backed by the USAspending demo pull (see scripts/import_usaspending.py)
 *  with an optional `q` substring filter. */
export function useAgencies(q?: string) {
  return useQuery({
    queryKey: ["agencies", q ?? ""] as const,
    queryFn: () => listAgencies(q),
    staleTime: 5 * 60 * 1000,
  });
}

/** Take over an entire matter — bulk-claim every workable Decision
 *  in one shot. Invalidates the matter + inbox so the ownership
 *  update lands immediately across surfaces. */
export function useClaimMatter(matterId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => {
      if (!matterId) throw new Error("missing matterId");
      return claimMatter(matterId);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["matter", matterId] });
      void qc.invalidateQueries({ queryKey: ["matters"] });
    },
  });
}

/** Submit an external-party response as a commitment Decision.
 *  Invalidates the matter + its decisions so the receipt lands
 *  immediately on the federal PM side. */
export function useSubmitRecipientResponse(matterId: string | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: RecipientResponseInput) => {
      if (!matterId) throw new Error("missing matterId");
      return submitRecipientResponse(matterId, input);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["matter", matterId] });
      void qc.invalidateQueries({ queryKey: ["matters"] });
    },
  });
}

/** Create a matter. Invalidates the matter list on success so the
 *  Register reflects the new row immediately. */
export function useCreateMatter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateMatterInput) => createMatter(input),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["matters"] });
    },
  });
}
