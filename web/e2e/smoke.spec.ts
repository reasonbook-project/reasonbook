// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { expect, test } from "@playwright/test";

/**
 * Pre-push smoke. The cheapest e2e signal that the SPA boots in a real
 * browser. Run via `make test-e2e-smoke` before pushing UI-bundle-
 * affecting changes (new deps, build-tooling changes, anything that
 * touches module-load behaviour).
 *
 * Catches the class of bug where a Node-only dependency lands in the
 * browser bundle and throws at module load — Vitest's jsdom polyfills
 * mask this (cf. the gray-matter / `Buffer is not defined` regression
 * that shipped at a2ba869 and broke every Playwright shard in CI).
 *
 * The real check is the global-setup login that runs before this spec
 * — if module-load throws, global-setup fails and this spec never
 * runs. The assertion below is a thin "we actually landed on the
 * authenticated app" confirmation; storageState from global-setup
 * means we don't re-log-in here.
 */
test("SPA boots and the authenticated app renders without page errors", async ({
  page,
}) => {
  const pageErrors: Error[] = [];
  page.on("pageerror", (err) => {
    pageErrors.push(err);
  });

  await page.goto("/inbox");

  // Inbox surface must paint — proves the app shell + drawers mounted
  // without their module-level imports throwing.
  await expect(page.getByRole("heading", { name: /inbox/i }).first()).toBeVisible({
    timeout: 10_000,
  });

  // No uncaught JS errors during boot (a "Buffer is not defined" from
  // a Node-only dep would surface here even if the page paints).
  expect(pageErrors, `page errors during boot: ${pageErrors.map((e) => e.message).join("; ")}`).toEqual([]);
});
