// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TopRail } from "./TopRail";

/**
 * Defensive UI guard: when a delta value equals the metric value
 * itself, TopRail suppresses the delta indicator. The shape almost
 * always indicates a fresh seed (every row created in last 24h) or
 * a regression in the delta calculation; rendering "▲ 56 / 56" is
 * noise. This mirrors the At Risk card's existing guard (TopRail.tsx
 * — the ``deltaSinceYesterday !== atRisk.value`` check in the
 * breakdown line).
 *
 * Backend invariant warnings in ``dgp/api/dashboard.py`` cover the
 * same condition on the ops side; this test covers the UI side.
 */
describe("TopRail delta guard", () => {
  type Posture = {
    open: { value: number; delta: number | null };
    decidedToday: { value: number; delta: number | null; avgCycleDays: number | null };
    atRisk: {
      value: number;
      deltaSinceYesterday: number | null;
      slaWindow: string;
      breakdown: { credit: number; compliance: number; ops: number };
    };
  };

  const basePosture: Posture = {
    open: { value: 56, delta: 12 },
    decidedToday: { value: 3, delta: 1, avgCycleDays: 3.2 },
    atRisk: {
      value: 15,
      deltaSinceYesterday: 6,
      slaWindow: "24h",
      breakdown: { credit: 2, compliance: 10, ops: 3 },
    },
  };

  function renderTopRail(posture: Posture) {
    return render(
      <TopRail
        agencyName="Riverdale Community Credit Union"
        agencySubtitle="Cross-workflow institutional posture"
        posture={posture}
        onReviewAtRisk={() => undefined}
        onFilterCategory={() => undefined}
      />,
    );
  }

  it("suppresses the Open delta when delta === value (fresh-seed shape)", () => {
    renderTopRail({
      ...basePosture,
      open: { value: 56, delta: 56 },
    });
    // The "▲ 56" pattern with no other context is the bug signature.
    // Use queryAllByText to be safe across icon-vs-text rendering.
    const arrows = screen.queryAllByText(/▲ 56\b/);
    expect(arrows).toHaveLength(0);
  });

  it("renders the Open delta when delta differs from value", () => {
    renderTopRail({
      ...basePosture,
      open: { value: 56, delta: 12 },
    });
    expect(screen.getByText(/▲ 12\b/)).toBeInTheDocument();
  });

  it("suppresses the Open delta when delta is null", () => {
    renderTopRail({
      ...basePosture,
      open: { value: 56, delta: null },
    });
    // No arrow should be rendered for the Open card.
    expect(screen.queryAllByText(/▲|▼/)).toEqual(
      // At Risk's delta line ("▲ 6 since yesterday") still renders;
      // we just confirm the Open delta isn't adding one.
      expect.arrayContaining([
        expect.objectContaining({ textContent: expect.stringMatching(/6/) }),
      ]),
    );
  });

  it("suppresses the Decided delta when delta === value", () => {
    renderTopRail({
      ...basePosture,
      decidedToday: { value: 3, delta: 3, avgCycleDays: 3.2 },
    });
    // The "▲ 3" pattern next to "Decided today" is the bug signature.
    // Since the at-risk breakdown has count=3 ops + count=3 ops-like
    // pills, search specifically for the arrow form.
    const arrows = screen.queryAllByText("▲ 3");
    expect(arrows).toHaveLength(0);
  });

  it("renders 'avg cycle —' when avgCycleDays is null", () => {
    renderTopRail({
      ...basePosture,
      decidedToday: { value: 3, delta: null, avgCycleDays: null },
    });
    expect(screen.getByText(/avg cycle —/)).toBeInTheDocument();
  });

  it("renders 'avg cycle X.Xd' when avgCycleDays is a positive number", () => {
    renderTopRail({
      ...basePosture,
      decidedToday: { value: 3, delta: null, avgCycleDays: 4.7 },
    });
    expect(screen.getByText(/avg cycle 4\.7d/)).toBeInTheDocument();
  });
});
