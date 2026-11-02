// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * MetricTile per the SaaS rebrand mockups (§3.5).
 *
 * The standard tile shape used across the app for any metric display. Replaces
 * every ad-hoc number-with-label pattern (Inbox stage strip, governance
 * dimension tiles, workflow detail summaries, etc).
 *
 * Contract:
 *   - Card surround: --paper bg, 1px --rule-soft, --radius-lg, padding 1rem.
 *   - Mono label at top: uppercase, 0.14em tracking, --ink-muted.
 *   - Stat number: 32px (--text-stat) navy, tabular-nums.
 *   - Caption: 12px --ink-muted supporting copy.
 *   - Optional trend: 11px mono with intent-keyed colour and direction glyph.
 *
 * Two states:
 *   - normal: value renders in navy, caption in ink-muted, trend visible if set.
 *   - empty:  value and caption render in --ink-faint; trend suppressed.
 *
 * Tiles are clickable (filter affordance). The `active` flag emphasises the
 * selected tile with a navy-tint background and stronger border.
 */
export type MetricTileState = "normal" | "empty";

export type MetricTrend = {
  direction: "up" | "down" | "flat";
  /** Free-form delta string, e.g. "12% wk-over-wk" or "+3 since Friday". */
  delta: string;
  /**
   * Semantic keying. Warning on trends moving in unwanted directions
   * (signals climbing, overdue rising). Success on trends moving in wanted
   * directions (actions clearing, outcomes recorded). Neutral otherwise.
   */
  intent: "warning" | "success" | "neutral";
};

const TREND_GLYPH: Record<MetricTrend["direction"], string> = {
  up: "↗",
  down: "↘",
  flat: "—",
};

const TREND_COLOR: Record<MetricTrend["intent"], string> = {
  warning: "text-accent-warning",
  success: "text-accent-success",
  neutral: "text-ink-muted",
};

export function MetricTile({
  label,
  value,
  caption,
  state = "normal",
  trend,
  active = false,
  onClick,
  className,
  ariaLabel,
}: {
  label: ReactNode;
  value: number | string;
  caption: ReactNode;
  state?: MetricTileState;
  trend?: MetricTrend;
  active?: boolean;
  onClick?: () => void;
  className?: string;
  ariaLabel?: string;
}) {
  const isEmpty = state === "empty";
  const Component = onClick ? "button" : "div";
  return (
    <Component
      type={onClick ? "button" : undefined}
      onClick={onClick}
      aria-pressed={onClick ? active : undefined}
      aria-label={ariaLabel}
      className={cn(
        "flex flex-col items-start gap-[6px] rounded-md border border-rule-soft bg-paper px-4 py-4 text-left transition-colors",
        onClick &&
          "hover:border-rule cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-navy/40",
        active && "border-navy bg-navy-tint",
        className,
      )}
    >
      <div className="text-mono-label uppercase text-ink-muted">{label}</div>
      <div
        className={cn(
          "text-stat font-semibold leading-none tracking-[-0.025em] tabular-nums",
          isEmpty ? "text-ink-faint" : "text-navy",
        )}
      >
        {value}
      </div>
      <div
        className={cn(
          "text-[12px]",
          isEmpty ? "text-ink-faint" : "text-ink-muted",
        )}
      >
        {caption}
      </div>
      {!isEmpty && trend && (
        <div
          className={cn(
            "font-mono text-[11px] tabular-nums",
            TREND_COLOR[trend.intent],
          )}
        >
          <span aria-hidden className="mr-1">
            {TREND_GLYPH[trend.direction]}
          </span>
          {trend.delta}
        </div>
      )}
    </Component>
  );
}
