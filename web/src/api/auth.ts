// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { apiFetch } from "./client";

export type ApexCapabilities = {
  oversight_role: string | null;
  domains_owned: string[];
  can_record_committee_action: boolean;
  is_executive: boolean;
  is_committee: boolean;
  level: number;
};

/** Compact agency descriptor emitted alongside CurrentUser. Not the
 *  full row — just what the frontend needs to render breadcrumbs,
 *  org-scope chips, and cross-agency indicators without a second
 *  round-trip. */
export type AgencySummary = {
  id: string;
  slug: string;
  name: string;
  short_name: string;
  depth: number;
};

export type CurrentUser = {
  id: string;
  username: string;
  name: string;
  email: string;
  title: string | null;
  role: "admin" | "member";
  tenant_id: string;
  tenant_name: string | null;
  // Tenancy tier per TENANCY-MODEL §3. Drives gating of tier-restricted
  // UI affordances ("Create matter" federal-only, amendment surfaces).
  tier: "federal" | "state" | "recipient";
  // Agency scope. DP is single-tenant / multi-agency; every federal-
  // tier user belongs to exactly one primary agency. `agency_chain`
  // walks top-down (department → bureau → program office) for
  // breadcrumb / org-scope display. All three are null for state/
  // recipient tier users (they scope by participant_org_id instead).
  agency_id: string | null;
  agency: AgencySummary | null;
  agency_chain: AgencySummary[];
  participant_org_id: string | null;
  // Apex capabilities — null for users without an apex grant. Drives the
  // Board stage action affordance on apex Decision Detail. Per apex spec
  // §6 + TODO P51.
  oversight_capabilities: ApexCapabilities | null;
};

export function login(username: string, password: string): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

export function logout(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/auth/logout", { method: "POST" });
}

export function getMe(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/api/auth/me");
}

export function verifyEmail(token: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(
    `/api/auth/verify-email?token=${encodeURIComponent(token)}`,
  );
}

export function resendVerification(): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/auth/resend-verification", {
    method: "POST",
  });
}

export function forgotPassword(email: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/auth/forgot-password", {
    method: "POST",
    body: { email },
  });
}

export function resetPassword(
  token: string,
  password: string,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>("/api/auth/reset-password", {
    method: "POST",
    body: { token, password },
  });
}
