// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Shared tenant-user list endpoint client.
 *
 * Distinct from web/src/api/settings.ts (admin-only, heavier payload). This
 * client is used by picker UIs — owner / assignee selection — where the
 * caller doesn't need admin scope to read the list.
 *
 * Backend: dgp/api/users.py (auth: @require_auth, tenant-scoped).
 */

import { apiFetch } from "./client";

export type TenantUser = {
  id: string;
  name: string;
  title: string | null;
  role: string;
  status: string;
};

export function listUsers(
  options: { status?: string } = {},
): Promise<{ items: TenantUser[] }> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  const query = params.toString();
  const path = query ? `/api/users?${query}` : "/api/users";
  return apiFetch<{ items: TenantUser[] }>(path);
}
