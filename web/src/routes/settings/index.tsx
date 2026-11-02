// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, redirect } from "@tanstack/react-router";

import { rootRoute } from "../__root";

/**
 * /settings → /settings/profile
 * The settings landing always lands on the profile pane.
 */
export const settingsIndexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings",
  beforeLoad: () => {
    throw redirect({ to: "/settings/profile" });
  },
});
