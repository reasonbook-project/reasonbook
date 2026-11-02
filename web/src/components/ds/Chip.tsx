// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Chip primitives per the SaaS rebrand mockups (§3.8).
 *
 * Five variants, all using mono-label typography (11px, weight 500,
 * 0.12em tracking, uppercase, 3px radius, 0.25rem × 0.5rem padding):
 *
 *   - default: --navy-soft bg, --navy text. e.g. `In progress`.
 *   - apex:    --ink bg, white text. The apex tier visual marker.
 *   - warning: amber-100 bg, --accent-warning text. `Needs attention`,
 *              `Overdue`, `Owner unassigned`, `Setup needed`.
 *   - success: emerald-100 bg, --accent-success text. `Complete`. Used rarely.
 *   - number:  --navy-soft bg, --navy text, mono-num typography. For
 *              workflow-number anchors next to a decision-row title.
 *
 * StatusBadge (decision-row urgency dot) is a different surface and stays
 * unchanged — chips here are nav/inline emphasis markers.
 */
export type ChipVariant =
  | "default"
  | "apex"
  | "warning"
  | "success"
  | "number";

const VARIANT_CLASSES: Record<ChipVariant, string> = {
  default: "bg-navy-soft text-navy",
  apex: "bg-ink text-paper",
  warning: "bg-amber-100 text-accent-warning",
  success: "bg-emerald-100 text-accent-success",
  number: "bg-navy-soft text-navy",
};

export function Chip({
  variant = "default",
  children,
  className,
}: {
  variant?: ChipVariant;
  children: ReactNode;
  className?: string;
}) {
  const isNumber = variant === "number";
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[3px] px-2 py-[3px] font-medium leading-none whitespace-nowrap",
        isNumber
          ? "font-mono text-[11px] tracking-[0.06em] tabular-nums"
          : "text-[11px] uppercase tracking-[0.12em]",
        VARIANT_CLASSES[variant],
        className,
      )}
    >
      {children}
    </span>
  );
}
