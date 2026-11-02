// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * useDecisionQueue — fetches the slim queue rows for the P17 drawer.
 *
 * Stub for Phase 1. Wired to consumers in Phase 2 (DecisionQueueDrawer
 * + filter toolbar). 30s staleTime matches the dashboard hook so the
 * drawer's "Refresh" feel mirrors the rest of the executive view.
 *
 * Refetch on filter change is automatic via the queryKey including the
 * filter object — TanStack Query treats a new key as a new query.
 *
 * The drawer is expected to gate this hook with ``enabled`` so the
 * network request only fires when the drawer is actually open; the hook
 * does not assume any UI state on its own.
 */

import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

import {
  getDecisionQueue,
  type QueueFilter,
  type QueueResponse,
} from "@/api/decisionQueue";

export type UseDecisionQueueOptions = {
  /** When false, the query is shelved (no fetch, no refetch). Defaults to
   *  true so the hook is opt-out for callers that want immediate fetch. */
  enabled?: boolean;
  limit?: number;
  offset?: number;
};

export function useDecisionQueue(
  filter: QueueFilter,
  options: UseDecisionQueueOptions = {},
) {
  const { enabled = true, limit, offset } = options;
  const queryOptions: UseQueryOptions<QueueResponse> = {
    queryKey: ["decisionQueue", filter, limit, offset],
    queryFn: () => getDecisionQueue(filter, { limit, offset }),
    staleTime: 30_000,
    enabled,
  };
  return useQuery(queryOptions);
}
