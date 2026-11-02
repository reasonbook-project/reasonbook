// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, redirect } from "@tanstack/react-router";

import { rootRoute } from "./__root";

/**
 * /register → /matters
 *
 * The Register surface was unified into /matters as part of the
 * unified-surface UI work. This file is retained only to keep the
 * deep link working — the route itself is a thin beforeLoad redirect.
 *
 * The original AwardsPage implementation and its agency / archetype
 * tree helpers are gone — /matters owns the discovery surface now
 * (LeftTree with Agency → Program → Matter).
 */
export const awardsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/register",
  beforeLoad: () => {
    throw redirect({ to: "/matters", replace: true });
  },
  component: () => null,
});
