// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { listArchetypes } from "@/api/archetypes";

/**
 * Read the archetype catalog (the 7 rows the Caseload rail renders).
 * Stale time is high — the catalog is config, not data, and won't
 * change inside a session.
 */
export function useArchetypes() {
  return useQuery({
    queryKey: ["archetypes"] as const,
    queryFn: listArchetypes,
    staleTime: 5 * 60 * 1000,
  });
}
