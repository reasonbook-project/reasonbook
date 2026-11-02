// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

// ─── Users ────────────────────────────────────────────────────────────────

export type SettingsUser = {
  id: string;
  tenant_id: string;
  username: string;
  email: string;
  name: string;
  title: string | null;
  role: "admin" | "member";
  status: "active" | "inactive" | "locked" | "pending_invite";
  last_login_at: string | null;
  login_count: number;
  created_at: string;
  updated_at: string;
};

export function listSettingsUsers(): Promise<{ items: SettingsUser[] }> {
  return apiFetch<{ items: SettingsUser[] }>("/api/settings/users");
}

export function inviteUser(body: {
  username: string;
  email: string;
  name: string;
  role: "admin" | "member";
  title?: string;
}): Promise<SettingsUser & { temp_password: string }> {
  return apiFetch("/api/settings/users", { method: "POST", body });
}

export function updateUser(
  userId: string,
  body: Partial<Pick<SettingsUser, "name" | "title" | "role" | "status">>,
): Promise<SettingsUser> {
  return apiFetch(`/api/settings/users/${userId}`, { method: "PUT", body });
}

export function deactivateUser(userId: string): Promise<SettingsUser> {
  return apiFetch(`/api/settings/users/${userId}`, { method: "DELETE" });
}

// Entitlements API removed in the DG-substrate cleanup — DP is single-
// tenant (US federal government), and workflow visibility is now
// unconditional. Row-level scope stays via fund-flow tier
// (federal / state / contractor) enforced by `apply_tier_scope`.

// ─── Overrides ────────────────────────────────────────────────────────────

export type OverridableType = "int" | "float" | "str" | "bool" | "list" | "dict";

export type OverridableKeys = Record<string, OverridableType>;

export type WorkflowSettingsConfig = {
  config: Record<string, unknown>;
  overridable_keys: OverridableKeys;
};

export type Override = {
  id: string;
  tenant_id: string;
  workflow_id: string;
  config_key: string;
  config_value: unknown;
  modified_by: string | null;
  modified_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  change_note: string | null;
  superseded_at: string | null;
};

export function getWorkflowSettings(
  workflowId: string,
): Promise<WorkflowSettingsConfig> {
  return apiFetch<WorkflowSettingsConfig>(
    `/api/settings/workflows/${workflowId}/config`,
  );
}

export function setOverride(
  workflowId: string,
  body: { config_key: string; config_value: unknown; change_note?: string },
): Promise<Override> {
  return apiFetch(`/api/settings/workflows/${workflowId}/overrides`, {
    method: "POST",
    body,
  });
}

export function supersedeOverride(
  workflowId: string,
  configKey: string,
): Promise<{ status: string }> {
  return apiFetch(
    `/api/settings/workflows/${workflowId}/overrides/${encodeURIComponent(
      configKey,
    )}`,
    { method: "DELETE" },
  );
}

export function getOverrideHistory(
  workflowId: string,
): Promise<{ items: Override[] }> {
  return apiFetch(
    `/api/settings/workflows/${workflowId}/overrides/history`,
  );
}

// ─── Tenant (Phase 8.5 institution config) ────────────────────────────────

export type OrgType = "CREDIT_UNION" | "COMMUNITY_BANK" | "SAVINGS_INSTITUTION";
export type Regulator = "NCUA" | "FDIC" | "OCC" | "STATE";
export type AssetSizeBand = "small" | "medium" | "large" | "very_large";

export type ExaminerContact = {
  name: string;
  agency?: string;
  email?: string;
  phone?: string;
  role?: string;
};

export type BoardCadenceEntry = {
  body: string; // e.g., "full_board", "audit_committee", "risk_committee"
  cadence: "monthly" | "quarterly" | "semi_annual" | "annual" | "ad_hoc";
  meeting_day?: string; // optional human-readable hint, e.g., "third Tuesday"
  notes?: string;
};

export type TenantProfile = {
  peer_group?: string;
  fiscal_year_start_month?: number;
  board_cadence?: BoardCadenceEntry[];
  examiner_contacts?: ExaminerContact[];
  risk_appetite_statement?: string;
};

export type TenantGovernance = {
  dual_control_enabled: boolean;
  require_approval_roles: string[];
  updated_at: string | null;
  updated_by: string | null;
};

export type DgiPrimaryRespondent = {
  id: string;
  name: string;
  email: string;
  title: string | null;
  status: "active" | "inactive" | "locked" | "pending_invite";
};

export type TenantSettings = {
  tenant_id: string;
  name: string;
  org_type: OrgType;
  regulator: Regulator | null;
  asset_size_band: AssetSizeBand | null;
  oversight_started_at: string | null;
  dgi_publication_opt_out: boolean;
  /** Designated respondent's user_id, or null if none designated yet. */
  dgi_primary_respondent_user_id: string | null;
  /** Resolved respondent — name, email, status. Null if no respondent
   * designated or if the user row was deleted (FK ON DELETE SET NULL). */
  dgi_primary_respondent: DgiPrimaryRespondent | null;
  tenant_profile: TenantProfile;
  governance: TenantGovernance;
  created_at: string;
  updated_at: string;
};

export type TenantPatch = {
  name?: string;
  org_type?: OrgType;
  regulator?: Regulator | null;
  asset_size_band?: AssetSizeBand | null;
  dgi_publication_opt_out?: boolean;
  tenant_profile?: Partial<TenantProfile>;
  governance?: Partial<Pick<TenantGovernance, "dual_control_enabled" | "require_approval_roles">>;
};

export function getTenantSettings(): Promise<TenantSettings> {
  return apiFetch<TenantSettings>("/api/settings/tenant");
}

export function patchTenantSettings(body: TenantPatch): Promise<TenantSettings> {
  return apiFetch("/api/settings/tenant", { method: "PATCH", body });
}
