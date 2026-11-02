// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ds/Tooltip";

/**
 * Inbox scope tabs per the SaaS rebrand mockups (§3.6).
 *
 * Linear-style underline tabs. Inactive: --ink-soft, transparent bottom
 * border, weight 500. Active: --ink, 2px navy bottom border, weight 500.
 * No background fills. The parent provides the 1px container border that
 * the active tab's 2px overlay sits flush against via -mb-px.
 *
 * Tooltips explain each scope for cold signups who don't yet know what
 * "Mine / Team / All entitled" means. Per gate-to-live plan Item 3.
 */
export type ScopeValue = "mine" | "team" | "all_entitled";

const OPTIONS: { value: ScopeValue; label: string; hint: string }[] = [
  {
    value: "mine",
    label: "Mine",
    hint: "Decisions assigned to you as owner.",
  },
  {
    value: "team",
    label: "Team",
    hint: "Decisions assigned to people who report to you.",
  },
  {
    value: "all_entitled",
    label: "All entitled",
    hint: "Every decision across the workflows you have access to.",
  },
];

export function ScopeToggle({
  value,
  onChange,
  className,
}: {
  value: ScopeValue;
  onChange: (value: ScopeValue) => void;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Decision scope"
      className={cn("flex items-center gap-6", className)}
    >
      {OPTIONS.map((opt) => {
        const active = opt.value === value;
        return (
          <Tooltip key={opt.value} content={opt.hint}>
            <button
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(opt.value)}
              className={cn(
                "border-b-2 py-2 text-[14px] font-medium transition-colors",
                active
                  ? "border-navy text-ink"
                  : "border-transparent text-ink-soft hover:text-ink",
              )}
            >
              {opt.label}
            </button>
          </Tooltip>
        );
      })}
    </div>
  );
}
