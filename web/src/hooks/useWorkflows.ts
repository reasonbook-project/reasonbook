// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useQuery } from "@tanstack/react-query";

import { getWorkflowConfig, listWorkflows } from "@/api/workflows";

export function useWorkflows() {
  return useQuery({
    queryKey: ["workflows", "list"],
    queryFn: listWorkflows,
    staleTime: 60_000,
  });
}

export function useWorkflowConfig(workflowId: string | undefined) {
  return useQuery({
    queryKey: ["workflows", "config", workflowId],
    queryFn: () => getWorkflowConfig(workflowId as string),
    enabled: Boolean(workflowId),
    staleTime: 60_000,
  });
}
