// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ds/Tooltip";

/**
 * Inbox density tabs per the SaaS rebrand mockups (§3.6). Same Linear-style
 * underline treatment as ScopeToggle.
 *
 * Tooltips explain each density mode for cold signups. Per gate-to-live
 * plan Item 3.
 */
export type DensityValue = "active" | "all";

const OPTIONS: { value: DensityValue; label: string; hint: string }[] = [
  {
    value: "active",
    label: "Active",
    hint: "Open + decided decisions not yet closed.",
  },
  {
    value: "all",
    label: "All",
    hint: "Everything, including closed and deferred.",
  },
];

export function DensityToggle({
  value,
  onChange,
  className,
}: {
  value: DensityValue;
  onChange: (value: DensityValue) => void;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label="Decision density"
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
