// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Page header per the SaaS rebrand mockups.
 *
 * Two patterns covered:
 *   - Dashboard / Inbox: title + optional subtitle + optional right slot.
 *   - Workflow detail: optional breadcrumb above + eyebrow (workflow chip) +
 *     title + optional `titleAfter` (status chip) + description + right slot
 *     (typically a primary CTA).
 *
 * One primary CTA per page is the discipline rule. Secondary actions belong
 * inline as ghost buttons or below the header as filters/toggles.
 */
export function PageHeader({
  breadcrumb,
  eyebrow,
  title,
  titleAfter,
  subtitle,
  right,
  className,
}: {
  breadcrumb?: ReactNode;
  eyebrow?: ReactNode;
  title: ReactNode;
  titleAfter?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cn("mb-6", className)}>
      {breadcrumb && (
        <div className="mb-3 text-[12px] text-ink-muted">{breadcrumb}</div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-[10px]">
            {eyebrow}
            <h1 className="text-[26px] font-medium leading-[1.2] tracking-[-0.018em] text-ink">
              {title}
            </h1>
            {titleAfter}
          </div>
          {subtitle && (
            <p className="mt-1 text-[13px] text-ink-muted">{subtitle}</p>
          )}
        </div>
        {right && <div className="flex items-center gap-2">{right}</div>}
      </div>
    </header>
  );
}
