// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Shared filter primitives for the Semantic Layer Catalog + per-workflow
 * Schema Explorer.
 *
 * Pure functions, no React. Each tab component composes these to filter
 * its own item list. Search is a case-insensitive substring match across
 * a concatenated text blob; dimensions are an OR'd set match against
 * each item's dimension field. Search ∩ dimensions when both are active.
 */

/**
 * Lowercase substring match. Empty query matches everything. Whitespace
 * in the query is split into tokens — every token must appear somewhere
 * in the haystack (AND across tokens) so "vendor soc" matches both
 * "vendor SOC review" and "review of SOC vendor scope" without forcing
 * the user to remember word order.
 */
export function matchesQuery(haystack: string, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return true;
  const lowered = haystack.toLowerCase();
  return trimmed.split(/\s+/).every((token) => lowered.includes(token));
}

/**
 * OR-match against the active dimension set. Empty active set matches
 * everything (no filter applied). Items with no dimension always pass
 * when the active set is empty; when the set is populated they fail
 * (since they can't satisfy any chip).
 */
export function matchesDimensions(
  itemDimension: string | null | undefined,
  activeDims: readonly string[],
): boolean {
  if (activeDims.length === 0) return true;
  if (!itemDimension) return false;
  return activeDims.includes(itemDimension);
}

/**
 * Collect the unique dimensions present in a list of items, preserving
 * first-seen order. Drives the chip row above each tab — chips populate
 * dynamically from what's in the current view (after the workflow
 * filter applies but before search/dim narrows).
 */
export function collectDimensions<T>(
  items: readonly T[],
  getDimension: (item: T) => string | null | undefined,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of items) {
    const d = getDimension(item);
    if (d && !seen.has(d)) {
      seen.add(d);
      out.push(d);
    }
  }
  return out;
}

/**
 * Format a snake_case dimension as a display label. The catalog renders
 * dimensions in the design system's mono-uppercase tracked style (e.g.
 * `bsa_filing` → `BSA_FILING`). Kept as a helper so the formatting
 * lives in one place.
 */
export function formatDimensionLabel(dim: string): string {
  return dim.toUpperCase();
}
