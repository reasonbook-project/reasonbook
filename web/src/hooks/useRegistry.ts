// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getDispute,
  listCases,
  listDisputes,
  listOrphanDecisions,
  resolveDispute,
  type DisputeResolution,
  type ResolveDisputeResponse,
} from "@/api/registry";
import { ApiError } from "@/api/client";

export function useRegistryCases() {
  return useQuery({
    queryKey: ["registry", "cases"] as const,
    queryFn: listCases,
    staleTime: 30 * 1000,
  });
}

export function useRegistryOrphanDecisions() {
  return useQuery({
    queryKey: ["registry", "decisions"] as const,
    queryFn: listOrphanDecisions,
    staleTime: 30 * 1000,
  });
}

export function useRegistryDisputes() {
  return useQuery({
    queryKey: ["registry", "disputes"] as const,
    queryFn: listDisputes,
    staleTime: 30 * 1000,
  });
}

export function useDispute(disputeId: string | undefined) {
  return useQuery({
    queryKey: ["registry", "dispute", disputeId] as const,
    queryFn: () => getDispute(disputeId as string),
    enabled: Boolean(disputeId),
    staleTime: 30 * 1000,
  });
}

export function useResolveDispute() {
  const qc = useQueryClient();
  return useMutation<
    ResolveDisputeResponse,
    ApiError,
    { disputeId: string; resolution: DisputeResolution; rationale?: string }
  >({
    mutationFn: ({ disputeId, resolution, rationale }) =>
      resolveDispute(disputeId, { resolution, rationale }),
    onSuccess: (_data, { disputeId }) => {
      void qc.invalidateQueries({
        queryKey: ["registry", "dispute", disputeId],
      });
      void qc.invalidateQueries({ queryKey: ["registry", "disputes"] });
      void qc.invalidateQueries({ queryKey: ["registry", "cases"] });
    },
  });
}
