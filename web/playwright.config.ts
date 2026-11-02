// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { defineConfig, devices } from "@playwright/test";

/**
 * E2E config for the Phase 7.5 Gate 9 canonical flow.
 *
 * The two webServer entries spawn Flask + Vite if they aren't already
 * running; `reuseExistingServer: true` means `make dev` works as-is.
 *
 * The dev server defaults are good enough — Vite already proxies /api to
 * Flask on 5001, so all the SPA needs is its own port (5173).
 *
 * The seed must be applied (`make seed`) before running. The e2e creates
 * its own decisions, but the Riverdale tenant and demo users are seed
 * preconditions.
 */
export default defineConfig({
  testDir: "./e2e",
  // Each spec scopes its own mutations by Date.now()-suffixed titles so
  // they don't race; auth is hoisted to globalSetup so we don't get
  // simultaneous-login conflicts at startup.
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // 50% of available cores on CI; let Playwright pick locally.
  workers: process.env.CI ? "50%" : undefined,
  reporter: process.env.CI ? "list" : "html",
  globalSetup: "./e2e/global-setup",
  use: {
    baseURL: "http://localhost:5173",
    // Authenticated session captured by global-setup.ts. Every spec
    // mounts with this state already loaded — no per-spec login.
    storageState: "e2e/.auth/jamie.json",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: "uv run flask --app dgp.app:create_app run --port 5001",
      cwd: "..",
      port: 5001,
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: "pnpm dev",
      port: 5173,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
});
