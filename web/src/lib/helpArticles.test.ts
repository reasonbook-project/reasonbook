// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

// Tests for the help-corpus loader + search infrastructure. The boot-
// time validation paths (bad surface, missing title, id/path mismatch,
// dangling related ref) can't be unit-tested without mocking the glob
// — they're exercised every time the module loads, which means every
// pnpm dev / pnpm build / pnpm test catches a regression.

import { describe, expect, it } from "vitest";

import {
  HELP_ARTICLES,
  HELP_SURFACE_ORDER,
  getArticleById,
  groupArticles,
  searchArticles,
} from "@/lib/helpArticles";

describe("help corpus loader", () => {
  it("auto-discovers a meaningful number of articles via glob", () => {
    // Corpus crossed 30 articles before Phase 6 shipped; the glob
    // should pick all of them up. Asserting a floor not a ceiling so
    // the test doesn't tighten on every new article.
    expect(HELP_ARTICLES.length).toBeGreaterThanOrEqual(30);
  });

  it("parses frontmatter — every article has id, title, surface, body", () => {
    for (const a of HELP_ARTICLES) {
      expect(a.id).toMatch(/^[a-z0-9-]+\/[a-z0-9-]+$/);
      expect(a.title.length).toBeGreaterThan(0);
      expect(HELP_SURFACE_ORDER).toContain(a.surface);
      expect(a.body.length).toBeGreaterThan(0);
    }
  });

  it("strips frontmatter from the body — the first frontmatter line is gone", () => {
    const claim = getArticleById("decisions/claim");
    expect(claim).toBeDefined();
    // The frontmatter opens with `---\nid: decisions/claim`; if it
    // wasn't stripped the body would start with `---`.
    expect(claim!.body.startsWith("---")).toBe(false);
  });

  it("hoists frontmatter summary to the article meta", () => {
    // These three articles moved their summary from the hand-typed
    // registry into frontmatter as part of the Phase 6 sweep.
    const create = getArticleById("inbox/create-decision-manually");
    expect(create?.summary).toMatch(/manually-creatable/);
    const atRisk = getArticleById("dashboard/at-risk-drilldown");
    expect(atRisk?.summary).toMatch(/At Risk tile/);
    const promote = getArticleById("roadmap/promote-initiative");
    expect(promote?.summary).toMatch(/SMART criteria/);
  });

  it("hoists frontmatter tags + related onto the meta", () => {
    const claim = getArticleById("decisions/claim");
    expect(Array.isArray(claim?.tags)).toBe(true);
    expect(claim?.tags?.length).toBeGreaterThan(0);
    expect(Array.isArray(claim?.related)).toBe(true);
  });

  it("groupArticles preserves HELP_SURFACE_ORDER", () => {
    const groups = groupArticles(HELP_ARTICLES);
    const surfaceSeq = groups.map((g) => g.surface);
    // surfaceSeq is HELP_SURFACE_ORDER filtered to surfaces that have
    // at least one article. Each surface in surfaceSeq must appear in
    // the same relative order as in HELP_SURFACE_ORDER.
    const indices = surfaceSeq.map((s) => HELP_SURFACE_ORDER.indexOf(s));
    const sorted = [...indices].sort((a, b) => a - b);
    expect(indices).toEqual(sorted);
  });
});

describe("searchArticles (MiniSearch-backed)", () => {
  it("returns the full corpus when the query is empty", () => {
    expect(searchArticles("").length).toBe(HELP_ARTICLES.length);
    expect(searchArticles("   ").length).toBe(HELP_ARTICLES.length);
  });

  it("ranks title matches above body-only matches", () => {
    // "finalize" is in the title of decisions/finalize and in the body
    // of several other articles. The title match must come first.
    const results = searchArticles("finalize");
    expect(results.length).toBeGreaterThan(0);
    expect(results[0]?.id).toBe("decisions/finalize");
  });

  it("supports prefix matching (typing 'fina' finds 'finalize')", () => {
    const results = searchArticles("fina");
    expect(results.some((r) => r.id === "decisions/finalize")).toBe(true);
  });

  it("uses exact match for short acronyms (no fuzzy expansion at ≤3 chars)", () => {
    // "SAR" should match the body of decisions/finalize (mentions SAR)
    // and NOT fuzzy-match Governance Profile (which contains "bar" —
    // 1 edit from "SAR" and would have matched under unguarded fuzzy).
    const results = searchArticles("SAR");
    const ids = results.map((r) => r.id);
    expect(ids).toContain("decisions/finalize");
    expect(ids).not.toContain("governance/profile");
  });

  it("tolerates a typo on longer terms via fuzzy", () => {
    // "finalise" (British spelling, 1 edit from "finalize") should
    // still surface the finalize article.
    const results = searchArticles("finalise");
    expect(results.some((r) => r.id === "decisions/finalize")).toBe(true);
  });

  it("combines multiple terms with AND", () => {
    // Each returned article must match BOTH "claim" and "evidence"
    // somewhere across its indexed fields. The decisions/claim article
    // mentions both; pure-evidence-only articles should not match.
    const results = searchArticles("claim evidence");
    expect(results.length).toBeGreaterThan(0);
    for (const r of results) {
      const haystack = `${r.title} ${r.tags?.join(" ") ?? ""} ${r.body}`.toLowerCase();
      expect(haystack).toContain("claim");
      expect(haystack).toContain("evidence");
    }
  });

  it("returns empty for a query that matches nothing", () => {
    expect(searchArticles("zzzzzzzzzzzzz")).toEqual([]);
  });
});
