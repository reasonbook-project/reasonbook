// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation } from "@tanstack/react-query";

import { verifyChain } from "@/api/integrity";

/**
 * Manual-trigger hash-chain verify. Use as a mutation (button-driven)
 * rather than a query so the "we just verified" moment is explicit and
 * the head hash in the response is fresh.
 */
export function useVerifyChain() {
  return useMutation({
    mutationFn: verifyChain,
  });
}
