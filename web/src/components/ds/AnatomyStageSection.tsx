// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Structural unit of the Decision Detail view per design-system §6.4.
 *
 * Layout:
 *   [stage label · uppercase tracked]  ─── hairline spacer ───  [timestamp]
 *   {content slot}
 *
 * Future stages (those not yet reached) render at opacity-55 to read as
 * dimmed-but-present.
 */
export function AnatomyStageSection({
  stageNumber,
  stageName,
  timestamp,
  dimmed,
  isLast,
  headerAccessory,
  children,
  className,
}: {
  /** Numeric for operational stages (1-5). Oversight Decision Detail passes
   *  a short string label ("C") for the Committee stage, which sits between
   *  Decision (3) and Action (4) without renumbering the rest. */
  stageNumber: number | string;
  stageName: string;
  timestamp?: string;
  dimmed?: boolean;
  isLast?: boolean;
  /** Right-aligned slot in the section header. Used for stage-edit toggles. */
  headerAccessory?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "px-5 py-[18px] transition-opacity",
        dimmed && "opacity-55",
        !isLast && "border-b-hairline border-rule-soft",
        className,
      )}
    >
      <header className="flex items-center gap-3">
        <span className="text-tracked font-medium uppercase text-ink-soft">
          {stageNumber} · {stageName}
        </span>
        <span
          aria-hidden
          className="h-px flex-1 bg-rule-soft"
        />
        {timestamp && (
          <span className="text-[11px] text-ink-faint">
            {timestamp}
          </span>
        )}
        {headerAccessory && <span>{headerAccessory}</span>}
      </header>
      {children && <div className="mt-3">{children}</div>}
    </section>
  );
}
