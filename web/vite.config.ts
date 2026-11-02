// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/// <reference types="vitest" />
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:5001",
        changeOrigin: true,
      },
    },
    // Allow `?raw` imports from the inherited DGP help corpus at
    // ../docs/legacy/help/ (one level above the web/ root). Fresh
    // Reasonbook help articles will land at ../docs/help/ once
    // authored; both paths are allowed.
    fs: {
      allow: [".", "../docs/help", "../docs/legacy/help"],
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Playwright e2e specs live in ./e2e and use their own runner.
    exclude: ["**/node_modules/**", "**/dist/**", "e2e/**"],
  },
});
