// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { listCatalog } from "@/api/catalog";

/** Read the full unified semantic-catalog entry stream. Stale time is
 *  high — the catalog is config, not data, and won't change inside a
 *  session unless the YAMLs reload. */
export function useCatalog() {
  return useQuery({
    queryKey: ["catalog", "entries"] as const,
    queryFn: listCatalog,
    staleTime: 5 * 60 * 1000,
  });
}
