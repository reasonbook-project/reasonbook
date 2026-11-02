// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * "All clear" / "No at-risk {category}" empty state for the queue drawer.
 *
 * Shown when status=at_risk and filtered_count=0. The dashboard drawer is
 * institution-wide (all_entitled scope), so the total at-risk count is
 * rarely zero for an active tenant — the empty state most commonly fires
 * for a category filter that has no at-risk decisions right now. Copy
 * varies accordingly:
 *
 *   - No category filter, 0 results → "All clear" (the original framing;
 *     genuinely positive when reached).
 *   - Category filter, 0 results    → "No at-risk {Category} decisions"
 *     (honest about the scope — other categories may still have items).
 *
 * Three stats from the queue endpoint's posture_context payload anchor
 * both variants. "Show all open decisions" widens to status=open with the
 * category dropped (handled by the parent).
 */

import { cn } from "@/lib/cn";

import type { PostureContext, QueueCategory } from "@/api/decisionQueue";

const CATEGORY_LABEL: Record<QueueCategory, string> = {
  compliance: "Compliance",
  credit: "Credit",
  ops: "Ops",
};

export type DecisionQueueEmptyProps = {
  posture: PostureContext;
  /** Active category filter when the empty state fires. Null = no filter
   *  applied (the "All clear" case). */
  category: QueueCategory | null;
  onShowAllOpen: () => void;
};

export function DecisionQueueEmpty({
  posture,
  category,
  onShowAllOpen,
}: DecisionQueueEmptyProps) {
  const headline = category
    ? `No at-risk ${CATEGORY_LABEL[category]} decisions`
    : "All clear";
  const subhead = category
    ? "This slice is quiet right now. Other categories may still have items, or widen to all open below."
    : "Nothing at risk right now. Here's where the agency sits at this moment.";
  return (
    <div className="flex flex-1 flex-col items-center justify-center px-6 py-12 text-center">
      {/* Teal check icon — 56px circle. Decorative; aria-hidden so screen
          readers go straight to the headline. Used for both the unfiltered
          "All clear" and the category-filtered "no at-risk in this slice"
          variants — both are positive within their scope. */}
      <div
        aria-hidden="true"
        className="grid h-14 w-14 place-items-center rounded-full bg-teal-50 text-teal-700"
      >
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </div>

      <h3 className="mt-4 text-[18px] font-medium text-ink">{headline}</h3>
      <p className="mt-2 max-w-[320px] text-[13px] text-ink-soft">{subhead}</p>

      <dl className="mt-6 grid grid-cols-3 gap-4 text-left">
        <Stat
          value={String(posture.open_count)}
          label="Open"
          intent="neutral"
        />
        <Stat
          value={
            posture.avg_cycle_days !== null
              ? `${posture.avg_cycle_days.toFixed(1)}d`
              : "—"
          }
          label="Avg cycle"
          intent="neutral"
        />
        <Stat
          value={String(posture.upcoming_count_48h)}
          label="SLA <48h"
          intent={posture.upcoming_count_48h > 0 ? "warning" : "neutral"}
        />
      </dl>

      <button
        type="button"
        onClick={onShowAllOpen}
        className={cn(
          "mt-7 inline-flex items-center gap-1.5 rounded-md border border-rule px-3 py-1.5",
          "text-[13px] font-medium text-ink transition-colors",
          "hover:bg-rule-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-navy",
        )}
      >
        Show all open decisions
        <span aria-hidden="true">→</span>
      </button>
    </div>
  );
}

function Stat({
  value,
  label,
  intent,
}: {
  value: string;
  label: string;
  intent: "neutral" | "warning";
}) {
  return (
    <div className="flex flex-col items-center">
      <dd
        className={cn(
          "text-[22px] font-medium tabular-nums",
          intent === "warning" ? "text-amber-700" : "text-ink",
        )}
      >
        {value}
      </dd>
      <dt className="mt-1 text-[10px] uppercase tracking-[0.08em] text-ink-faint">
        {label}
      </dt>
    </div>
  );
}
