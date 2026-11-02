// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, redirect } from "@tanstack/react-router";

import { rootRoute } from "../__root";

/**
 * /settings/tenant → /settings/profile
 *
 * The DGP-era Institution settings page was a multi-tenant concern
 * (peer group, board cadence, examiner contacts, risk appetite) that
 * doesn't apply to DP. DP is single-agency: exactly one federal
 * agency runs the app. There is no per-institution config to author.
 *
 * The route survives only as a redirect so any deep links land
 * somewhere coherent. The original TenantForm + sections (~700
 * lines) are gone.
 *
 * Memory: project_single_tenant_federal.md.
 */
export const settingsTenantRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/tenant",
  beforeLoad: () => {
    throw redirect({ to: "/settings/profile", replace: true });
  },
  component: () => null,
});
