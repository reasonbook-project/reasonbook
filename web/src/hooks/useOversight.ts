// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type ApexEvidenceLink,
  type BoardAction,
  type CreateEvidenceBody,
  type RecordBoardActionBody,
  type SupersedeEvidenceBody,
  createApexEvidence,
  listApexEvidence,
  listBoardCycles,
  listCycleFindings,
  recordBoardAction,
  supersedeApexEvidence,
} from "@/api/oversight";
import { ApiError } from "@/api/client";

const APEX_KEY = "apex" as const;

export function useOversightCycles(
  status?: "planned" | "active" | "concluded",
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: [APEX_KEY, "cycles", status ?? "all"],
    queryFn: () => listBoardCycles(status),
    // Cycle status flips on calendar boundaries (a daily auto-transition
    // job moves planned→active and active→concluded). 60s stale window is
    // fine for inspection; cycles don't churn the way decisions do.
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
}

export function useOversightCycleFindings(cycleId: string | undefined) {
  return useQuery({
    queryKey: [APEX_KEY, "cycle-findings", cycleId],
    queryFn: () => listCycleFindings(cycleId as string),
    enabled: Boolean(cycleId),
    staleTime: 30_000,
  });
}

export function useOversightEvidence(oversightDecisionId: string | undefined) {
  return useQuery({
    queryKey: [APEX_KEY, "evidence", oversightDecisionId],
    queryFn: () => listApexEvidence(oversightDecisionId as string),
    enabled: Boolean(oversightDecisionId),
    staleTime: 5_000,
  });
}

export function useCreateApexEvidence() {
  const qc = useQueryClient();
  return useMutation<
    ApexEvidenceLink,
    ApiError,
    { oversightDecisionId: string; body: CreateEvidenceBody }
  >({
    mutationFn: ({ oversightDecisionId, body }) =>
      createApexEvidence(oversightDecisionId, body),
    onSuccess: (_d, { oversightDecisionId }) => {
      void qc.invalidateQueries({ queryKey: [APEX_KEY, "evidence", oversightDecisionId] });
    },
  });
}

export function useSupersedeApexEvidence(oversightDecisionId: string) {
  const qc = useQueryClient();
  return useMutation<
    { superseded: ApexEvidenceLink; replacement: ApexEvidenceLink | null },
    ApiError,
    { linkId: string; body?: SupersedeEvidenceBody }
  >({
    mutationFn: ({ linkId, body }) => supersedeApexEvidence(linkId, body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [APEX_KEY, "evidence", oversightDecisionId] });
    },
  });
}

/** Record a board action against an apex decision. Writes a `decision_events`
 *  row server-side; the action label drives the CommitteeStage rendering. The
 *  hook invalidates the events query so the new row surfaces immediately. */
export function useRecordBoardAction(oversightDecisionId: string) {
  const qc = useQueryClient();
  return useMutation<
    { ok: boolean; action: BoardAction },
    ApiError,
    RecordBoardActionBody
  >({
    mutationFn: (body) => recordBoardAction(oversightDecisionId, body),
    onSuccess: () => {
      void qc.invalidateQueries({
        queryKey: ["decisions", "events", oversightDecisionId],
      });
      void qc.invalidateQueries({
        queryKey: ["decisions", "detail", oversightDecisionId],
      });
    },
  });
}
