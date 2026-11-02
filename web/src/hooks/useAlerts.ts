// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type AlertSource,
  type AlertStatus,
  type DispositionBody,
  type MatterLinkFilter,
  attachAlertToMatter,
  getAlertLifecycle,
  listAlerts,
  postDisposition,
} from "@/api/alerts";
import type { ApiError } from "@/api/client";

const ALERTS_KEY = "alerts" as const;

export function useAlerts(params?: {
  status?: AlertStatus[];
  source?: AlertSource[];
  matter_link?: MatterLinkFilter;
}) {
  return useQuery({
    queryKey: [ALERTS_KEY, "list", params],
    queryFn: () => listAlerts(params),
    staleTime: 5_000,
    refetchInterval: (q) => (q.state.error ? false : 10_000),
    refetchIntervalInBackground: false,
  });
}

export function useAlertLifecycle(alertId: string | undefined) {
  return useQuery({
    queryKey: [ALERTS_KEY, "lifecycle", alertId],
    queryFn: () => getAlertLifecycle(alertId as string),
    enabled: Boolean(alertId),
    staleTime: 5_000,
  });
}

export function usePostDisposition() {
  const qc = useQueryClient();
  return useMutation<
    Awaited<ReturnType<typeof postDisposition>>,
    ApiError,
    { alertId: string; body: DispositionBody }
  >({
    mutationFn: ({ alertId, body }) => postDisposition(alertId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [ALERTS_KEY, "list"] });
      void qc.invalidateQueries({ queryKey: [ALERTS_KEY, "lifecycle"] });
    },
  });
}

export function useAttachAlertToMatter() {
  const qc = useQueryClient();
  return useMutation<
    Awaited<ReturnType<typeof attachAlertToMatter>>,
    ApiError,
    { alertId: string; matterId: string }
  >({
    mutationFn: ({ alertId, matterId }) => attachAlertToMatter(alertId, matterId),
    onSuccess: () => {
      // Alerts list changes shape (unattached count drops); matter data
      // gains a fresh signal on the case-file surface.
      void qc.invalidateQueries({ queryKey: [ALERTS_KEY, "list"] });
      void qc.invalidateQueries({ queryKey: ["matters"] });
      void qc.invalidateQueries({ queryKey: ["matter"] });
    },
  });
}
