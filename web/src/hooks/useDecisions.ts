// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type CreateCommentBody,
  type CreateDecisionBody,
  type Decision,
  type DecisionListParams,
  type EventInclude,
  type PatchActionBody,
  type PatchDecisionBody,
  type PatchOutcomeBody,
  type PatchSignalBody,
  type RecordActionBody,
  type RecordOutcomeBody,
  type BulkResponse,
  bulkClaim,
  bulkComment,
  claimDecision,
  createComment,
  createDecision,
  deferDecision,
  deleteAttachment,
  escalateDecision,
  finalizeDecision,
  type FinalizeBody,
  getDecision,
  getDecisionEvents,
  listAttachments,
  listDecisions,
  patchAction,
  patchDecisionStage,
  patchOutcome,
  patchSignal,
  recordAction,
  recordOutcome,
  uploadAttachment,
  type AttachmentStage,
} from "@/api/decisions";
import { ApiError } from "@/api/client";

const DECISIONS_KEY = "decisions" as const;

export function useDecisions(params: DecisionListParams) {
  return useQuery({
    queryKey: [DECISIONS_KEY, "list", params],
    queryFn: () => listDecisions(params),
    staleTime: 5_000,
    refetchInterval: (query) => (query.state.error ? false : 10_000),
    refetchIntervalInBackground: false,
  });
}

export function useDecision(decisionId: string | undefined) {
  return useQuery({
    queryKey: [DECISIONS_KEY, "detail", decisionId],
    queryFn: () => getDecision(decisionId as string),
    enabled: Boolean(decisionId),
    staleTime: 5_000,
  });
}

export function useDecisionEvents(
  decisionId: string | undefined,
  include: EventInclude = "audit",
) {
  return useQuery({
    queryKey: [DECISIONS_KEY, "events", decisionId, include],
    queryFn: () => getDecisionEvents(decisionId as string, include),
    enabled: Boolean(decisionId),
    staleTime: 5_000,
  });
}

export function useDecisionAttachments(decisionId: string | undefined) {
  return useQuery({
    queryKey: [DECISIONS_KEY, "attachments", decisionId],
    queryFn: () => listAttachments(decisionId as string),
    enabled: Boolean(decisionId),
    staleTime: 5_000,
  });
}

function invalidateDecision(qc: ReturnType<typeof useQueryClient>, id: string) {
  void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "list"] });
  void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "detail", id] });
  void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "events", id] });
  void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "attachments", id] });
  // Matter queries embed decision rows (status, selected_option, etc.)
  // via the composite decision-record card, so a decision mutation
  // needs to reflow both the single-matter detail and any list view.
  void qc.invalidateQueries({ queryKey: ["matter"] });
  void qc.invalidateQueries({ queryKey: ["matters"] });
}

export function useClaimDecision() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, string>({
    mutationFn: (decisionId: string) => claimDecision(decisionId),
    onSuccess: (_data, decisionId) => invalidateDecision(qc, decisionId),
  });
}

export function useFinalizeDecision() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    ApiError,
    { decisionId: string; body: FinalizeBody }
  >({
    mutationFn: ({ decisionId, body }) => finalizeDecision(decisionId, body),
    onSuccess: (_data, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function useDeferDecision() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    ApiError,
    { decisionId: string; reason: string; reopen_at?: string }
  >({
    mutationFn: ({ decisionId, reason, reopen_at }) =>
      deferDecision(decisionId, { reason, reopen_at }),
    onSuccess: (_data, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function useEscalateDecision() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    ApiError,
    { decisionId: string; reason: string; escalated_to?: string }
  >({
    mutationFn: ({ decisionId, reason, escalated_to }) =>
      escalateDecision(decisionId, { reason, escalated_to }),
    onSuccess: (_data, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

// ─── Phase 7.5 Gate 4 ─────────────────────────────────────────────────────

export function useCreateDecision() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, CreateDecisionBody>({
    mutationFn: (body) => createDecision(body),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "list"] });
    },
  });
}

// ─── Phase 7.5 Gate 5 — PATCH stage edits ─────────────────────────────────

export function usePatchSignal() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: PatchSignalBody }>({
    mutationFn: ({ decisionId, body }) => patchSignal(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function usePatchDecisionStage() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: PatchDecisionBody }>({
    mutationFn: ({ decisionId, body }) => patchDecisionStage(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function usePatchAction() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: PatchActionBody }>({
    mutationFn: ({ decisionId, body }) => patchAction(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function usePatchOutcome() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: PatchOutcomeBody }>({
    mutationFn: ({ decisionId, body }) => patchOutcome(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

// ─── Stage transitions (record action / outcome) ──────────────────────────

export function useRecordAction() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: RecordActionBody }>({
    mutationFn: ({ decisionId, body }) => recordAction(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function useRecordOutcome() {
  const qc = useQueryClient();
  return useMutation<Decision, ApiError, { decisionId: string; body: RecordOutcomeBody }>({
    mutationFn: ({ decisionId, body }) => recordOutcome(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

// ─── Phase 7.5 Gate 7 — attachments ───────────────────────────────────────

export function useUploadAttachment() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    ApiError,
    { decisionId: string; file: File; stage?: AttachmentStage; description?: string }
  >({
    mutationFn: ({ decisionId, file, stage, description }) =>
      uploadAttachment(decisionId, file, stage, description),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

export function useDeleteAttachment() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, { decisionId: string; attachmentId: string }>({
    mutationFn: ({ decisionId, attachmentId }) =>
      deleteAttachment(decisionId, attachmentId),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

// ─── Phase 7.5 Gate 7 — comments ──────────────────────────────────────────

export function useCreateComment() {
  const qc = useQueryClient();
  return useMutation<unknown, ApiError, { decisionId: string; body: CreateCommentBody }>({
    mutationFn: ({ decisionId, body }) => createComment(decisionId, body),
    onSuccess: (_d, { decisionId }) => invalidateDecision(qc, decisionId),
  });
}

// ─── Phase 8.5 — bulk operations ──────────────────────────────────────────

function invalidateAfterBulk(qc: ReturnType<typeof useQueryClient>, ids: string[]) {
  void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "list"] });
  for (const id of ids) {
    void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "detail", id] });
    void qc.invalidateQueries({ queryKey: [DECISIONS_KEY, "events", id] });
  }
}

export function useBulkClaim() {
  const qc = useQueryClient();
  return useMutation<BulkResponse, ApiError, string[]>({
    mutationFn: (ids) => bulkClaim(ids),
    onSuccess: (_d, ids) => invalidateAfterBulk(qc, ids),
  });
}

export function useBulkComment() {
  const qc = useQueryClient();
  return useMutation<BulkResponse, ApiError, { ids: string[]; body: string }>({
    mutationFn: ({ ids, body }) => bulkComment(ids, body),
    onSuccess: (_d, { ids }) => invalidateAfterBulk(qc, ids),
  });
}
