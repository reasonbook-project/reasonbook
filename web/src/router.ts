// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRouter } from "@tanstack/react-router";

import { NotFoundPage } from "./components/NotFoundPage";

import { alertsRoute } from "./routes/alerts";
import { apexCyclesRoute } from "./routes/apexCycles";
import { rootRoute } from "./routes/__root";
import { awardsRoute } from "./routes/awards";
import { catalogRoute } from "./routes/catalog";
import { dashboardRoute } from "./routes/dashboard";
import { decisionDetailRoute } from "./routes/decisionDetail";
import { disputeDetailRoute } from "./routes/disputeDetail";
import { forgotPasswordRoute } from "./routes/forgotPassword";
import { indexRoute } from "./routes/index";
import { inboxRoute } from "./routes/inbox";
import { inboxDecisionsRoute } from "./routes/inboxDecisions";
import { loginRoute } from "./routes/login";
import { matterDetailRoute } from "./routes/matterDetail";
import { mattersRoute } from "./routes/matters";
import { recipientPortalRoute } from "./routes/recipientPortal";
import { recipientResponseRoute } from "./routes/recipientResponse";
import { oversightRoute } from "./routes/oversight";
import { resetPasswordRoute } from "./routes/resetPassword";
import { settingsConnectorsRoute } from "./routes/settings/connectors";
import { settingsIndexRoute } from "./routes/settings/index";
import { settingsProfileRoute } from "./routes/settings/profile";
import { settingsTenantRoute } from "./routes/settings/tenant";
import { settingsUsersRoute } from "./routes/settings/users";
import { settingsWorkflowsRoute } from "./routes/settings/workflows";
import { verifyEmailRoute } from "./routes/verifyEmail";
import { workflowSchemaRoute } from "./routes/workflowSchema";
import { workflowUploadRoute } from "./routes/workflowUpload";

const routeTree = rootRoute.addChildren([
  indexRoute,
  inboxRoute,
  inboxDecisionsRoute,
  loginRoute,
  forgotPasswordRoute,
  resetPasswordRoute,
  verifyEmailRoute,
  dashboardRoute,
  decisionDetailRoute,
  disputeDetailRoute,
  awardsRoute,
  matterDetailRoute,
  mattersRoute,
  recipientPortalRoute,
  recipientResponseRoute,
  oversightRoute,
  alertsRoute,
  apexCyclesRoute,
  catalogRoute,
  settingsIndexRoute,
  settingsProfileRoute,
  settingsTenantRoute,
  settingsUsersRoute,
  settingsWorkflowsRoute,
  settingsConnectorsRoute,
  workflowUploadRoute,
  workflowSchemaRoute,
]);

export const router = createRouter({
  routeTree,
  defaultNotFoundComponent: NotFoundPage,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
