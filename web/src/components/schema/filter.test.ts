// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from "vitest";

import {
  collectDimensions,
  formatDimensionLabel,
  matchesDimensions,
  matchesQuery,
} from "./filter";

describe("matchesQuery", () => {
  it("returns true for empty query (no filter applied)", () => {
    expect(matchesQuery("anything", "")).toBe(true);
    expect(matchesQuery("anything", "   ")).toBe(true);
  });

  it("is case-insensitive substring match", () => {
    expect(matchesQuery("OIG referral filing", "sar")).toBe(true);
    expect(matchesQuery("bsa sar filing", "SAR")).toBe(true);
  });

  it("requires every whitespace token to appear (AND across tokens)", () => {
    expect(matchesQuery("Vendor SOC review", "vendor soc")).toBe(true);
    // Word order doesn't matter
    expect(matchesQuery("review of SOC vendor scope", "vendor soc")).toBe(true);
    // Missing token fails
    expect(matchesQuery("vendor review", "vendor soc")).toBe(false);
  });

  it("returns false when no tokens match", () => {
    expect(matchesQuery("alpha beta gamma", "delta")).toBe(false);
  });
});

describe("matchesDimensions", () => {
  it("returns true when no dims are active (no filter)", () => {
    expect(matchesDimensions("oig_referral", [])).toBe(true);
    expect(matchesDimensions(null, [])).toBe(true);
  });

  it("returns true when item dim is in the active set (OR match)", () => {
    expect(
      matchesDimensions("oig_referral", ["due_diligence", "oig_referral"]),
    ).toBe(true);
  });

  it("returns false when item dim is not in the active set", () => {
    expect(matchesDimensions("oig_referral", ["due_diligence"])).toBe(false);
  });

  it("returns false when item has no dim and the active set is non-empty", () => {
    expect(matchesDimensions(null, ["oig_referral"])).toBe(false);
    expect(matchesDimensions(undefined, ["oig_referral"])).toBe(false);
  });
});

describe("collectDimensions", () => {
  it("returns unique dimensions in first-seen order", () => {
    const items = [
      { d: "alpha" },
      { d: "beta" },
      { d: "alpha" },
      { d: "gamma" },
      { d: "beta" },
    ];
    expect(collectDimensions(items, (x) => x.d)).toEqual([
      "alpha",
      "beta",
      "gamma",
    ]);
  });

  it("skips items with null/undefined dimension", () => {
    const items = [
      { d: "alpha" },
      { d: null },
      { d: undefined },
      { d: "beta" },
    ];
    expect(collectDimensions(items, (x) => x.d)).toEqual(["alpha", "beta"]);
  });

  it("returns empty array when no items have dimensions", () => {
    const items = [{ d: null }, { d: undefined }];
    expect(collectDimensions(items, (x) => x.d)).toEqual([]);
  });
});

describe("formatDimensionLabel", () => {
  it("uppercases the dimension string", () => {
    expect(formatDimensionLabel("oig_referral")).toBe("OIG_REFERRAL");
    expect(formatDimensionLabel("review_cycle")).toBe("REVIEW_CYCLE");
  });
});
