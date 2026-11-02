// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * ModeTabs — tab strip for switching detail modes (Inspector, Case
 * file, Activity, Audit chain on /matters; Queue / Selected on Inbox
 * and Signals; Findings / Cycle summary on Oversight).
 *
 * Modes are tabs, not routes — switching modes is a state change in
 * the same URL, no SPA navigation, no full data refetch.
 *
 * Each tab optionally carries a `count` (small monospace number) to
 * answer "is there anything here?" before the click.
 */

export type Mode = {
  id: string;
  label: ReactNode;
  /**
   * A short purple "badge" pill for a primary count
   * (e.g., open signals on Inspector, items in Activity).
   * Use for hot numbers — anything the user is meant to react to.
   */
  badge?: ReactNode;
  /**
   * A small muted caption after the label (e.g., "6 sections",
   * "verified"). Use for static descriptors, not hot counts.
   */
  count?: ReactNode;
};

export function ModeTabs({
  modes,
  current,
  onChange,
  className,
}: {
  modes: Mode[];
  current: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn("flex gap-0 -mb-px", className)}
    >
      {modes.map((m) => {
        const isCurrent = m.id === current;
        return (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={isCurrent}
            onClick={() => onChange(m.id)}
            className={cn(
              "px-4 pt-2.5 pb-3",
              "text-[13px]",
              "border-b-[1.5px]",
              isCurrent
                ? "text-ink border-navy font-medium"
                : "text-ink-soft border-transparent hover:text-ink",
            )}
          >
            {m.label}
            {m.badge !== undefined && (
              <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1.5 ml-1.5 rounded-full bg-[#7c3aed] text-paper text-[10px] font-mono font-medium align-middle">
                {m.badge}
              </span>
            )}
            {m.count !== undefined && (
              <span className="font-mono text-[10px] ml-1.5 text-ink-faint">
                {m.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
