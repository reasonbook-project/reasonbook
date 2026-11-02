// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import { OVERSIGHT_WORKFLOW_ID, oversightTagline, isOversightDecision } from "./oversight";

describe("isOversightDecision", () => {
  it("identifies the oversight workflow", () => {
    expect(isOversightDecision({ workflow_id: OVERSIGHT_WORKFLOW_ID })).toBe(true);
  });

  it("rejects operational workflows", () => {
    expect(isOversightDecision({ workflow_id: "01-regulatory-compliance" })).toBe(false);
  });

  it("handles undefined input", () => {
    expect(isOversightDecision(undefined)).toBe(false);
  });
});

describe("oversightTagline", () => {
  const baseDecision = {
    outcome_recorded_at: null,
    decided_at: null,
    status: "open",
    oversight_cycle_id: null,
  } as const;

  it("returns null when there is no useful state", () => {
    expect(oversightTagline(baseDecision, null)).toBeNull();
  });

  it("prefers outcome over decided", () => {
    const tag = oversightTagline(
      {
        ...baseDecision,
        outcome_recorded_at: "2026-04-15T00:00:00Z",
        decided_at: "2026-04-12T00:00:00Z",
      },
      null,
    );
    expect(tag).toMatch(/^Outcome recorded /);
  });

  it("uses decided date when no outcome", () => {
    const tag = oversightTagline(
      { ...baseDecision, decided_at: "2026-04-12T00:00:00Z" },
      null,
    );
    expect(tag).toMatch(/^Decided /);
  });

  it("falls back to cycle context for in-flight decisions", () => {
    const tag = oversightTagline(baseDecision, {
      name: "Q2 2026 Board Cycle",
      cycle_end: "2026-06-30",
      status: "active",
    });
    expect(tag).toContain("Q2 2026 Board Cycle");
    expect(tag).toContain("closes");
  });

  it("calls out concluded cycles distinctly", () => {
    const tag = oversightTagline(baseDecision, {
      name: "Q1 2026 Board Cycle",
      cycle_end: "2026-03-31",
      status: "concluded",
    });
    expect(tag).toBe("Q1 2026 Board Cycle concluded.");
  });

  it("renders deferred status with cycle name when present", () => {
    const tag = oversightTagline(
      { ...baseDecision, status: "deferred" },
      {
        name: "Q2 2026 Board Cycle",
        cycle_end: "2026-06-30",
        status: "active",
      },
    );
    expect(tag).toContain("Deferred");
    expect(tag).toContain("Q2 2026 Board Cycle");
  });
});
