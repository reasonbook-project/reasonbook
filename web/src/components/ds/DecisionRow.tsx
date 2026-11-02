// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ChangeEvent, type ReactNode } from "react";

import { cn } from "@/lib/cn";

import { StatusBadge, type StatusVariant } from "./StatusBadge";

/**
 * The most-rendered component in the product per design-system §6.3.
 *
 * Default three-column layout (after the severity stripe + checkbox):
 *   [urgency badge · 96px] [title + one-line body · 1fr] [right metadata · 100px]
 *
 * Severity stripe: a 4px solid vertical band on the left edge, full row
 * height, flush left. Drives off the ``severity`` prop. Purely visual
 * (no hover, no click target). When omitted, no stripe renders.
 *
 * Phase 8.5 bulk-ops: when ``selectable`` is set, an extra leading column
 * holds a checkbox. Clicking the checkbox toggles selection without
 * triggering the row's onClick (navigation). The checkbox renders inside
 * its own ``<div>`` outside the button/div tag so its click event
 * cleanly stops at the input — a checkbox inside a `<button>` is invalid
 * markup anyway.
 *
 * The badge column reserves 96px but the badge itself sizes to its content.
 * The body line truncates with ellipsis — single line, never wraps. The
 * decision ID lives in the right-metadata column above the due date,
 * demoted to text-[10px] muted-foreground so the due date reads as the
 * primary right-side scan target. ~70px row height target.
 */
export type RowSeverity = "low" | "medium" | "high" | "critical";

// 4px stripe (round 2 — widened from 3px for clearer separation).
// Color tokens picked to ladder cleanly low → critical in the inbox.
const SEVERITY_STRIPE: Record<RowSeverity, string> = {
  low: "bg-gray-300",
  medium: "bg-amber-300",
  high: "bg-orange-500",
  critical: "bg-red-600",
};

export function DecisionRow({
  status,
  statusLabel,
  title,
  body,
  rightMetadata,
  decisionId,
  severity,
  onClick,
  isLast,
  className,
  selectable,
  selected,
  onToggleSelected,
}: {
  status: StatusVariant;
  statusLabel: string;
  title: string;
  /** Single-line summary; renders truncated with ellipsis if it overflows. */
  body?: ReactNode;
  /** Lower-priority right-aligned metadata (deadline, opened-ago timestamp). */
  rightMetadata?: ReactNode;
  /** If provided, rendered atop the right-metadata column in mono. */
  decisionId?: string;
  /** Severity drives the left-edge stripe color; omit for no stripe. */
  severity?: RowSeverity;
  onClick?: () => void;
  isLast?: boolean;
  className?: string;
  /** Phase 8.5 — when true, render a leading checkbox for bulk selection. */
  selectable?: boolean;
  /** Phase 8.5 — current checkbox state. */
  selected?: boolean;
  /** Phase 8.5 — fires when the user toggles the checkbox. */
  onToggleSelected?: (next: boolean) => void;
}) {
  const Tag = onClick ? "button" : "div";

  return (
    <div
      className={cn(
        "flex w-full items-stretch transition-colors",
        onClick && "hover:bg-rule-faint",
        !isLast && "border-b-[0.5px] border-rule-soft",
        className,
      )}
    >
      {severity && (
        <div
          aria-hidden="true"
          data-testid="severity-stripe"
          className={cn("w-[4px] shrink-0", SEVERITY_STRIPE[severity])}
        />
      )}
      <div className="flex flex-1 items-center gap-3 pl-4 pr-4">
        {selectable && (
          <input
            type="checkbox"
            aria-label={`Select ${title}`}
            checked={selected ?? false}
            onChange={(e: ChangeEvent<HTMLInputElement>) =>
              onToggleSelected?.(e.target.checked)
            }
            className="h-4 w-4 shrink-0 cursor-pointer accent-navy"
          />
        )}
        <Tag
          type={onClick ? "button" : undefined}
          onClick={onClick}
          className={cn(
            "grid min-w-0 flex-1 grid-cols-[96px_1fr_100px] items-center gap-4 py-[14px] text-left",
            onClick && "cursor-pointer",
          )}
        >
          <div className="flex items-center">
            <StatusBadge variant={status} label={statusLabel} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-body font-medium tracking-tight text-ink">
              {title}
            </div>
            {body && (
              <div className="mt-1 truncate text-body-sm text-ink-soft">
                {body}
              </div>
            )}
          </div>
          <div className="flex flex-col items-end gap-1 text-[11px] text-ink-faint">
            {decisionId && (
              <span className="font-mono text-[10px] font-normal text-muted-foreground">
                {decisionId}
              </span>
            )}
            {rightMetadata}
          </div>
        </Tag>
      </div>
    </div>
  );
}
