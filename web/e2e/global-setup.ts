// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { chromium } from "@playwright/test";

/**
 * Run once per test session: log in as Jamie Kim, save the authenticated
 * cookie + localStorage to e2e/.auth/jamie.json so every spec can skip
 * the login round-trip via the `storageState` config in playwright.config.
 *
 * Re-run automatically on any change to this file. Manual re-run by
 * deleting e2e/.auth/ before the next test invocation — appropriate
 * after a credential rotation or JWT-format change.
 *
 * Reads creds from E2E_USERNAME / E2E_PASSWORD env vars with seed-truth
 * fallbacks. The fallbacks intentionally hard-code the demo password
 * literal so this file doesn't need updating on every DEMO_PASSWORD
 * rotation — set E2E_PASSWORD in the environment when the seed changes.
 */
const STORAGE_STATE = "e2e/.auth/jamie.json";

async function globalSetup() {
  const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:5173";
  const username = process.env.E2E_USERNAME ?? "jamie.kim";
  const password = process.env.E2E_PASSWORD ?? "change-me-e2e-password";

  // Sanity probe: hit the Flask backend directly (bypassing Vite's proxy)
  // so a 404/connect-refused/timeout here pinpoints "backend never started"
  // vs "backend up but login rejected." Surfaces in the CI log before the
  // 30s waitForURL timeout — much faster diagnosis.
  const apiBase = baseURL.replace("5173", "5001");
  try {
    const probe = await fetch(`${apiBase}/api/health`);
    console.log(`[global-setup] backend probe ${apiBase}/api/health → ${probe.status}`);
  } catch (err) {
    console.error(
      `[global-setup] backend probe ${apiBase}/api/health → ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Mirror browser console + network failures to the runner log so we
  // can see whatever the SPA actually said when login broke.
  page.on("console", (msg) => {
    if (msg.type() === "error" || msg.type() === "warning") {
      console.log(`[browser ${msg.type()}] ${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => console.error(`[page error] ${err.message}`));
  page.on("requestfailed", (req) => {
    console.error(
      `[request failed] ${req.method()} ${req.url()} — ${req.failure()?.errorText ?? "unknown"}`,
    );
  });
  page.on("response", (resp) => {
    if (resp.url().includes("/api/") && resp.status() >= 400) {
      console.error(`[api ${resp.status()}] ${resp.request().method()} ${resp.url()}`);
    }
  });

  await page.goto(`${baseURL}/login`);
  await page.getByLabel(/username/i).fill(username);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /sign in/i }).click();

  try {
    await page.waitForURL("**/inbox", { timeout: 30_000 });
  } catch (err) {
    console.error(`[global-setup] login failed. Final URL: ${page.url()}`);
    const bodyText = await page.textContent("body").catch(() => "<no content>");
    console.error(`[global-setup] page body (first 500 chars): ${bodyText?.slice(0, 500)}`);
    await page
      .screenshot({ path: "e2e/.auth/login-failure.png", fullPage: true })
      .catch((screenshotErr) => {
        console.error(`[global-setup] screenshot capture failed: ${screenshotErr}`);
      });
    throw err;
  }

  await page.context().storageState({ path: STORAGE_STATE });
  await browser.close();
}

export default globalSetup;
