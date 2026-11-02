// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

import { formatDimensionLabel } from "./filter";

/**
 * Dimension chip row rendered inside a schema tab when the tab has
 * dimensions to filter on. Chips populate from `available` (computed
 * from the items currently in view, before search/dim narrows). Multi-
 * select OR — clicking toggles a chip in/out of the active set.
 *
 * "Clear all" link surfaces only when at least one chip is active. When
 * no dimensions are available (e.g. on the States & flow or
 * Documentation tabs) the component renders nothing — caller can
 * mount it unconditionally.
 */
export function DimChips({
  available,
  active,
  onToggle,
  onClear,
  className,
}: {
  available: readonly string[];
  active: readonly string[];
  onToggle: (dim: string) => void;
  onClear: () => void;
  className?: string;
}) {
  if (available.length === 0) return null;
  return (
    <div className={cn("mb-4 flex flex-wrap items-center gap-2", className)}>
      {available.map((d) => {
        const on = active.includes(d);
        return (
          <button
            key={d}
            type="button"
            onClick={() => onToggle(d)}
            aria-pressed={on}
            className={cn(
              "inline-flex items-center rounded-full px-2.5 py-0.5 font-mono text-[10px] uppercase tracking-tracked transition-colors",
              on
                ? "bg-navy text-paper"
                : "border border-rule bg-paper text-ink-soft hover:border-navy hover:text-ink",
            )}
          >
            {formatDimensionLabel(d)}
          </button>
        );
      })}
      {active.length > 0 && (
        <button
          type="button"
          onClick={onClear}
          className="text-body-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          Clear all
        </button>
      )}
    </div>
  );
}

/**
 * "Showing X of Y items" line rendered above the filtered item list.
 * Suppressed when the filter is inactive (visible == total) — no value
 * to show "Showing 47 of 47" repeatedly.
 */
export function FilterCount({
  visible,
  total,
}: {
  visible: number;
  total: number;
}) {
  if (visible === total) return null;
  return (
    <p className="mb-3 text-body-sm text-ink-muted">
      Showing {visible} of {total} {total === 1 ? "item" : "items"}.
    </p>
  );
}

/**
 * Empty-state for when the search query returns no matches. Includes a
 * "Clear search" link that calls back to the search-input owner.
 */
export function NoMatchesState({
  query,
  onClearSearch,
}: {
  query: string;
  onClearSearch: () => void;
}) {
  return (
    <div className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-6 text-body-sm text-ink-muted">
      No items match &ldquo;{query}&rdquo;.{" "}
      <button
        type="button"
        onClick={onClearSearch}
        className="text-ink-soft underline-offset-2 hover:text-ink hover:underline"
      >
        Clear search
      </button>
    </div>
  );
}
