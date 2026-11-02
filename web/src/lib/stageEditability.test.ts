// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import { canEditStage } from "./stageEditability";

/**
 * Mirror of dgp/decisions/manager.py EDITABLE_STAGES. Catches drift if either
 * side moves and the other doesn't — these tests fail the moment the matrix
 * diverges from the backend.
 */
describe("canEditStage", () => {
  it("signal stage is reachable from every status", () => {
    for (const status of [
      "open",
      "assigned",
      "in_progress",
      "decided",
      "closed",
      "deferred",
      "escalated",
    ] as const) {
      expect(canEditStage("signal", status)).toBe(true);
    }
  });

  it("decision stage opens at in_progress and stays through closed", () => {
    expect(canEditStage("decision", "open")).toBe(false);
    expect(canEditStage("decision", "assigned")).toBe(false);
    expect(canEditStage("decision", "in_progress")).toBe(true);
    expect(canEditStage("decision", "decided")).toBe(true);
    expect(canEditStage("decision", "closed")).toBe(true);
    expect(canEditStage("decision", "deferred")).toBe(false);
    expect(canEditStage("decision", "escalated")).toBe(false);
  });

  it("action stage opens at decided", () => {
    expect(canEditStage("action", "in_progress")).toBe(false);
    expect(canEditStage("action", "decided")).toBe(true);
    expect(canEditStage("action", "closed")).toBe(true);
  });

  it("outcome stage opens only at closed", () => {
    expect(canEditStage("outcome", "decided")).toBe(false);
    expect(canEditStage("outcome", "closed")).toBe(true);
  });
});
