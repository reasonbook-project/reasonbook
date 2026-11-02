// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, redirect } from "@tanstack/react-router";

import { rootRoute } from "./__root";

/**
 * /workflows/$workflowId/upload → /settings/connectors
 *
 * The manual upload surface is retired. DP ingest is via federal-
 * system connectors (USASpending, eRA Commons, SAM exclusions, etc.),
 * which live as shared infrastructure under /settings/connectors,
 * NOT as per-workflow config.
 *
 * Memory notes: project_no_upload_surface.md,
 * project_usaspending_connector_reference.md.
 */
export const workflowUploadRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workflows/$workflowId/upload",
  beforeLoad: () => {
    throw redirect({
      to: "/settings/connectors",
      replace: true,
    });
  },
  component: () => null,
});
