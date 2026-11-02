// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * The list body of the queue drawer.
 *
 * Renders:
 *   - Filter toolbar (Compliance / Credit / Ops toggle pills)
 *   - "{filteredCount} of {totalCount}" count line
 *   - Row list (or a thin loading skeleton + error message)
 *
 * Composes <DecisionQueueRow> for each decision. The drawer header lives
 * in <DecisionQueueDrawer>; this component owns only the body.
 */

import { cn } from "@/lib/cn";

import { DecisionQueueRow } from "./DecisionQueueRow";

import type { QueueCategory, QueueDecision } from "@/api/decisionQueue";

const CATEGORIES: QueueCategory[] = ["compliance", "credit", "ops"];

const CATEGORY_LABEL: Record<QueueCategory, string> = {
  compliance: "Compliance",
  credit: "Credit",
  ops: "Ops",
};

export type DecisionQueueListProps = {
  decisions: QueueDecision[];
  filteredCount: number;
  totalCount: number;
  activeCategory: QueueCategory | null;
  onCategoryChange: (category: QueueCategory | null) => void;
  onSelectDecision: (decision: QueueDecision) => void;
  isLoading: boolean;
  errorMessage: string | null;
};

export function DecisionQueueList({
  decisions,
  filteredCount,
  totalCount,
  activeCategory,
  onCategoryChange,
  onSelectDecision,
  isLoading,
  errorMessage,
}: DecisionQueueListProps) {
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <CategoryToolbar
        active={activeCategory}
        onChange={onCategoryChange}
      />

      <div className="border-b border-rule-soft bg-bg-warm px-4 py-2 text-[11px] uppercase tracking-[0.08em] text-ink-faint">
        {filteredCount === totalCount
          ? `${totalCount} at risk`
          : `${filteredCount} of ${totalCount} at risk`}
      </div>

      {errorMessage ? (
        <div className="px-4 py-6 text-[13px] text-amber-800">
          Couldn't load the queue: {errorMessage}
        </div>
      ) : isLoading ? (
        <LoadingSkeleton />
      ) : (
        <div className="flex-1 overflow-y-auto">
          {decisions.map((d) => (
            <DecisionQueueRow
              key={d.id}
              decision={d}
              onSelect={onSelectDecision}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CategoryToolbar({
  active,
  onChange,
}: {
  active: QueueCategory | null;
  onChange: (category: QueueCategory | null) => void;
}) {
  return (
    <div
      role="toolbar"
      aria-label="Filter by category"
      className="flex items-center gap-1.5 border-b border-rule-soft px-4 py-2.5"
    >
      <button
        type="button"
        onClick={() => onChange(null)}
        aria-pressed={active === null}
        className={pillClass(active === null)}
      >
        All categories
      </button>
      {CATEGORIES.map((cat) => (
        <button
          key={cat}
          type="button"
          onClick={() => onChange(active === cat ? null : cat)}
          aria-pressed={active === cat}
          className={pillClass(active === cat)}
        >
          {CATEGORY_LABEL[cat]}
        </button>
      ))}
    </div>
  );
}

function pillClass(active: boolean): string {
  return cn(
    "rounded-full border px-3 py-1 text-[12px] font-medium transition-colors",
    active
      ? "border-navy bg-navy-tint text-navy-deep"
      : "border-rule-soft bg-paper text-ink-soft hover:bg-bg-warm hover:text-ink",
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex-1 space-y-2 px-4 py-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading queue</span>
      {[0, 1, 2, 3].map((i) => (
        <div
          key={i}
          className="h-10 animate-pulse rounded bg-rule-soft/60"
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
