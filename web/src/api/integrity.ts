// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

/**
 * SEC-1 hash-chain verification (P09).
 *
 * Walks the append-only ``decision_events`` table from genesis and
 * confirms each event's stored hash matches the recomputed hash. On
 * any tamper, ``ok=false`` with ``broken_at_*`` pointing at the first
 * divergent row.
 */
export type VerifyChainResult = {
  ok: boolean;
  total_events: number;
  head_hash: string;
  broken_at_id: string | null;
  broken_at_index: number | null;
  expected_hash: string | null;
  actual_hash: string | null;
};

export function verifyChain(): Promise<VerifyChainResult> {
  return apiFetch<VerifyChainResult>("/api/integrity/verify-chain");
}
