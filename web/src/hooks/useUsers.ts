// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { listUsers } from "@/api/users";

/**
 * useUsers — tenant user list for picker UIs.
 *
 * Used by the Governance Roadmap promote-modal owner picker (Prompt 1)
 * and will be reused by the deferred bulk-Reassign action. Keep the query
 * shape generic — do not narrow it to one caller.
 */
export function useUsers(options: { status?: string } = {}) {
  return useQuery({
    queryKey: ["users", options.status ?? "all"],
    queryFn: () => listUsers(options),
    staleTime: 60_000,
  });
}
