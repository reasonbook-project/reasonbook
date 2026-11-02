// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { listPrograms } from "@/api/programs";

/** Read the program catalog (the 7 program-profile rows). Stale time
 *  is high — programs are config, not data, and won't change inside a
 *  session. */
export function usePrograms() {
  return useQuery({
    queryKey: ["programs"] as const,
    queryFn: listPrograms,
    staleTime: 5 * 60 * 1000,
  });
}
