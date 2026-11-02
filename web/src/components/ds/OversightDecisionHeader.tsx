// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Apex decision header per the SaaS rebrand.
 *
 * Strategic / board-level decisions still get the editorial register, but
 * via Inter weight 600 with -0.025em tracking rather than Source Serif Pro.
 * Italic tagline uses Inter italic. Cream-warm ground (--bg-warm) preserves
 * the threshold feel without breaking from the brand site palette.
 */
export function OversightDecisionHeader({
  breadcrumb,
  title,
  italicTagline,
  decisionId,
  timestamps,
  rightSlot,
  className,
}: {
  breadcrumb?: ReactNode;
  title: string;
  italicTagline?: string;
  decisionId?: string;
  timestamps?: string;
  rightSlot?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "border-b border-rule-soft bg-bg-warm px-8 py-10",
        className,
      )}
    >
      {breadcrumb && (
        <div className="mb-4 flex items-center gap-2 text-[13px] text-ink-muted">
          {breadcrumb}
        </div>
      )}
      <div className="flex items-start justify-between gap-8">
        <div className="min-w-0">
          <h1 className="text-page tracking-tightest text-navy-deep">
            {title}
          </h1>
          {italicTagline && (
            <p className="mt-2 text-[14px] italic text-ink-soft">
              {italicTagline}
            </p>
          )}
          <div className="mt-4 flex items-center gap-2 text-[11px] text-ink-faint">
            {decisionId && <span className="font-mono">{decisionId}</span>}
            {decisionId && timestamps && <span aria-hidden>·</span>}
            {timestamps && <span>{timestamps}</span>}
          </div>
        </div>
        {rightSlot && <div className="shrink-0">{rightSlot}</div>}
      </div>
    </header>
  );
}
