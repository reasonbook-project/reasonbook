// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";
import { Link } from "@tanstack/react-router";

import { cn } from "@/lib/cn";

import { WorkflowChip } from "./WorkflowChip";

/**
 * Decision Detail page header per the SaaS rebrand.
 *
 * Two registers, both Inter:
 *  - `operational`: 20px weight 500 ink. Functional voice for everyday
 *    decisions.
 *  - `oversight`: 26px weight 600 navy-deep with -0.025em tracking,
 *    optional italic tagline, --bg-warm ground. Declamatory voice for
 *    agency-level oversight decisions.
 */
export function DecisionDetailHeader({
  variant = "operational",
  breadcrumb,
  title,
  decisionId,
  timestamps,
  italicTagline,
  rightSlot,
  className,
}: {
  variant?: "operational" | "oversight";
  breadcrumb?: ReactNode;
  title: string;
  decisionId?: string;
  timestamps?: string;
  italicTagline?: string;
  rightSlot?: ReactNode;
  className?: string;
}) {
  const isOversight = variant === "oversight";
  return (
    <header
      className={cn(
        "border-b border-rule-soft px-7 py-6",
        isOversight && "bg-bg-warm",
        className,
      )}
    >
      {breadcrumb && (
        <div className="mb-3 flex items-center gap-2 text-[13px] text-ink-muted">
          {breadcrumb}
        </div>
      )}
      <div className="flex items-start justify-between gap-6">
        <div className="min-w-0">
          <h1
            className={cn(
              isOversight
                ? "text-[26px] font-semibold text-navy-deep tracking-[-0.025em]"
                : "text-[20px] font-medium text-ink tracking-tight",
            )}
          >
            {title}
          </h1>
          {isOversight && italicTagline && (
            <p className="mt-1 text-[14px] italic text-ink-soft">
              {italicTagline}
            </p>
          )}
          <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-faint">
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

/**
 * Helper for the breadcrumb slot — produces a typical Inbox › Decisions
 * › [WorkflowChip] structure used by operational decisions.
 */
export function OperationalBreadcrumb({
  workflowName,
  workflowColor,
}: {
  workflowName: string;
  workflowColor: string;
}) {
  return (
    <>
      <span>Inbox</span>
      <span aria-hidden className="text-ink-faint">›</span>
      <span>Decisions</span>
      <span aria-hidden className="text-ink-faint">›</span>
      <WorkflowChip name={workflowName} color={workflowColor} />
    </>
  );
}

/**
 * Federal-determination breadcrumb: Caseload › <Archetype> › <Program>.
 * Used by DET-* decisions promoted from the determination ledger. No
 * WorkflowChip because federal programs don't yet carry a color in the
 * registry — they're text-only until the program metadata grows.
 */
export function FederalBreadcrumb({
  archetypeName,
  programName,
  matterId,
}: {
  archetypeName?: string;
  programName?: string;
  /** When set, prepends a clickable "Register › Matter <short id>" prefix
   *  per TENANCY-MODEL §10 step 8. Surfaces the matter this Decision lives
   *  inside so the user can navigate up to the aggregate. */
  matterId?: string | null;
}) {
  return (
    <>
      {matterId && (
        <>
          {/* Matters list → inspector. Both crumbs land on the unified
              /matters surface; "Matter <id>" pre-selects the matter so
              the user lands on the inspector mode for that matter. */}
          <Link to="/matters" className="text-brand hover:underline">
            Matters
          </Link>
          <span aria-hidden className="text-ink-faint">›</span>
          <Link
            to="/matters"
            search={{ id: matterId }}
            className="text-brand hover:underline"
          >
            Matter {matterId.slice(0, 8)}
          </Link>
          <span aria-hidden className="text-ink-faint">›</span>
        </>
      )}
      <span>Caseload</span>
      {archetypeName && (
        <>
          <span aria-hidden className="text-ink-faint">›</span>
          <span>{archetypeName}</span>
        </>
      )}
      {programName && (
        <>
          <span aria-hidden className="text-ink-faint">›</span>
          <span>{programName}</span>
        </>
      )}
    </>
  );
}

/**
 * Oversight breadcrumb: Oversight › Agency & oversight › [oversight cycle chip].
 * The cycle chip uses the navy-deep ground from the oversight workflow color
 * so it reads as the only navy chip in the system (per design system §3.1).
 */
export function OversightBreadcrumb({ cycleName }: { cycleName?: string | null }) {
  return (
    <>
      <span>Oversight</span>
      <span aria-hidden className="text-ink-faint">›</span>
      <span>Agency & oversight</span>
      {cycleName && (
        <>
          <span aria-hidden className="text-ink-faint">›</span>
          <WorkflowChip name={cycleName} color="#042C53" />
        </>
      )}
    </>
  );
}
