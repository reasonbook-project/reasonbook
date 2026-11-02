// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { getDashboard } from "@/api/dashboard";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    staleTime: 30_000,
    refetchInterval: (query) => (query.state.error ? false : 60_000),
    refetchIntervalInBackground: false,
  });
}
