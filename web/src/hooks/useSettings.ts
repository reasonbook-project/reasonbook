// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  type SettingsUser,
  type TenantPatch,
  type TenantSettings,
  deactivateUser,
  getOverrideHistory,
  getTenantSettings,
  getWorkflowSettings,
  inviteUser,
  listSettingsUsers,
  patchTenantSettings,
  setOverride,
  supersedeOverride,
  updateUser,
} from "@/api/settings";

const USERS_KEY = ["settings", "users"] as const;
const TENANT_KEY = ["settings", "tenant"] as const;

// ─── Users ────────────────────────────────────────────────────────────────

export function useSettingsUsers() {
  return useQuery({ queryKey: USERS_KEY, queryFn: listSettingsUsers });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: inviteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation<
    SettingsUser,
    Error,
    { userId: string; body: Parameters<typeof updateUser>[1] }
  >({
    mutationFn: ({ userId, body }) => updateUser(userId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: deactivateUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: USERS_KEY }),
  });
}

// ─── Overrides ────────────────────────────────────────────────────────────

export function useWorkflowSettings(workflowId: string | undefined) {
  return useQuery({
    queryKey: ["settings", "workflow", workflowId],
    queryFn: () => getWorkflowSettings(workflowId as string),
    enabled: Boolean(workflowId),
  });
}

export function useOverrideHistory(workflowId: string | undefined) {
  return useQuery({
    queryKey: ["settings", "workflow", workflowId, "history"],
    queryFn: () => getOverrideHistory(workflowId as string),
    enabled: Boolean(workflowId),
  });
}

export function useSetOverride() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { workflowId: string; body: Parameters<typeof setOverride>[1] }
  >({
    mutationFn: ({ workflowId, body }) => setOverride(workflowId, body),
    onSuccess: (_data, { workflowId }) => {
      void qc.invalidateQueries({
        queryKey: ["settings", "workflow", workflowId],
      });
    },
  });
}

export function useSupersedeOverride() {
  const qc = useQueryClient();
  return useMutation<
    unknown,
    Error,
    { workflowId: string; configKey: string }
  >({
    mutationFn: ({ workflowId, configKey }) =>
      supersedeOverride(workflowId, configKey),
    onSuccess: (_data, { workflowId }) => {
      void qc.invalidateQueries({
        queryKey: ["settings", "workflow", workflowId],
      });
    },
  });
}

// ─── Tenant settings ──────────────────────────────────────────────────────

export function useTenantSettings() {
  return useQuery({ queryKey: TENANT_KEY, queryFn: getTenantSettings });
}

export function usePatchTenantSettings() {
  const qc = useQueryClient();
  return useMutation<TenantSettings, Error, TenantPatch>({
    mutationFn: patchTenantSettings,
    onSuccess: (data) => {
      qc.setQueryData(TENANT_KEY, data);
      // Topbar / dashboard surfaces read tenant name; refresh.
      void qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}
