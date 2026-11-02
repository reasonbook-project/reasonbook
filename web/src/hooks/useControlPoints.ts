// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  listControlPoints,
  type MarkGapBody,
  postMarkGap,
} from "@/api/controlPoints";
import type { ApiError } from "@/api/client";

const CONTROL_POINTS_KEY = "control_points" as const;

export function useControlPoints(matterId: string | undefined) {
  return useQuery({
    queryKey: [CONTROL_POINTS_KEY, "list", matterId],
    queryFn: () => listControlPoints(matterId as string),
    enabled: Boolean(matterId),
    staleTime: 5_000,
    refetchInterval: (q) => (q.state.error ? false : 10_000),
    refetchIntervalInBackground: false,
  });
}

export function useMarkGap() {
  const qc = useQueryClient();
  return useMutation<
    Awaited<ReturnType<typeof postMarkGap>>,
    ApiError,
    { controlPointId: string; body: MarkGapBody }
  >({
    mutationFn: ({ controlPointId, body }) => postMarkGap(controlPointId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [CONTROL_POINTS_KEY, "list"] });
    },
  });
}
