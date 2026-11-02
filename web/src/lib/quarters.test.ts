// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Quarter math — pure unit tests, no DOM, no React.
 *
 * Used by the governance roadmap timeline (column headers, bar positioning,
 * today-line) and by PromoteInitiativeModal (target-quarter dropdown). Bugs
 * here surface as off-by-one rendering in the timeline.
 */

import { describe, expect, it } from "vitest";

import {
  currentQuarter,
  formatQuarterCompact,
  formatQuarterLong,
  isCurrentQuarter,
  isPastQuarter,
  nextNQuarters,
  quarterCompare,
  quarterFromOffset,
  quartersBetween,
  quartersInRange,
} from "./quarters";

describe("currentQuarter", () => {
  it("derives Q1 from January", () => {
    expect(currentQuarter(new Date(Date.UTC(2026, 0, 15)))).toBe("2026-Q1");
  });
  it("derives Q4 from December", () => {
    expect(currentQuarter(new Date(Date.UTC(2026, 11, 31)))).toBe("2026-Q4");
  });
  it("derives Q2 from April + Q3 from July", () => {
    expect(currentQuarter(new Date(Date.UTC(2026, 3, 1)))).toBe("2026-Q2");
    expect(currentQuarter(new Date(Date.UTC(2026, 6, 1)))).toBe("2026-Q3");
  });
});

describe("quarterFromOffset", () => {
  it("zero offset returns the same quarter", () => {
    expect(quarterFromOffset("2026-Q2", 0)).toBe("2026-Q2");
  });
  it("positive offsets advance correctly across year boundaries", () => {
    expect(quarterFromOffset("2026-Q3", 1)).toBe("2026-Q4");
    expect(quarterFromOffset("2026-Q3", 2)).toBe("2027-Q1");
    expect(quarterFromOffset("2026-Q4", 1)).toBe("2027-Q1");
    expect(quarterFromOffset("2026-Q1", 8)).toBe("2028-Q1");
  });
  it("negative offsets go backward across year boundaries", () => {
    expect(quarterFromOffset("2026-Q1", -1)).toBe("2025-Q4");
    expect(quarterFromOffset("2026-Q2", -5)).toBe("2025-Q1");
  });
  it("rejects invalid quarter strings", () => {
    expect(() => quarterFromOffset("nope", 1)).toThrow();
  });
});

describe("nextNQuarters", () => {
  it("emits exactly N quarters", () => {
    const out = nextNQuarters("2026-Q3", 4);
    expect(out).toEqual(["2026-Q3", "2026-Q4", "2027-Q1", "2027-Q2"]);
  });
  it("empty when N is 0", () => {
    expect(nextNQuarters("2026-Q3", 0)).toEqual([]);
  });
});

describe("quarterCompare", () => {
  it("returns 0 for equal", () => {
    expect(quarterCompare("2026-Q3", "2026-Q3")).toBe(0);
  });
  it("returns negative when a is earlier", () => {
    expect(quarterCompare("2026-Q1", "2026-Q2")).toBeLessThan(0);
    expect(quarterCompare("2025-Q4", "2026-Q1")).toBeLessThan(0);
  });
  it("returns positive when a is later", () => {
    expect(quarterCompare("2026-Q4", "2026-Q1")).toBeGreaterThan(0);
  });
});

describe("quartersBetween", () => {
  it("returns 0 when same", () => {
    expect(quartersBetween("2026-Q2", "2026-Q2")).toBe(0);
  });
  it("returns positive for end-after-start", () => {
    expect(quartersBetween("2026-Q3", "2027-Q1")).toBe(2);
    expect(quartersBetween("2026-Q1", "2028-Q1")).toBe(8);
  });
  it("returns negative for start-after-end", () => {
    expect(quartersBetween("2027-Q1", "2026-Q3")).toBe(-2);
  });
});

describe("quartersInRange", () => {
  it("inclusive of both endpoints", () => {
    expect(quartersInRange("2026-Q3", "2027-Q1")).toEqual([
      "2026-Q3",
      "2026-Q4",
      "2027-Q1",
    ]);
  });
  it("single-quarter range returns one element", () => {
    expect(quartersInRange("2026-Q3", "2026-Q3")).toEqual(["2026-Q3"]);
  });
  it("reversed range returns empty", () => {
    expect(quartersInRange("2027-Q1", "2026-Q3")).toEqual([]);
  });
});

describe("formatters", () => {
  it("compact format matches the mockup", () => {
    expect(formatQuarterCompact("2026-Q3")).toBe("Q3·26");
  });
  it("long format for prose", () => {
    expect(formatQuarterLong("2026-Q3")).toBe("Q3 2026");
  });
  it("passes invalid strings through", () => {
    expect(formatQuarterCompact("not-a-quarter")).toBe("not-a-quarter");
  });
});

describe("isPastQuarter / isCurrentQuarter", () => {
  it("isPastQuarter strict less-than", () => {
    expect(isPastQuarter("2026-Q1", "2026-Q2")).toBe(true);
    expect(isPastQuarter("2026-Q2", "2026-Q2")).toBe(false);
    expect(isPastQuarter("2026-Q3", "2026-Q2")).toBe(false);
  });
  it("isCurrentQuarter equality", () => {
    expect(isCurrentQuarter("2026-Q2", "2026-Q2")).toBe(true);
    expect(isCurrentQuarter("2026-Q1", "2026-Q2")).toBe(false);
  });
});
