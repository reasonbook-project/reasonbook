// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";
import { Card } from "./Card";

/**
 * Editorial empty state per the SaaS rebrand mockups (section 4).
 *
 * Three-part pattern wrapped in a Card.featured (navy-tint bg, navy-soft
 * border): optional eyebrow + headline + explanatory body + action row.
 *
 * Voice rules (section 4.2):
 *   - First-person plural where natural ("We capture..." not "Decisions are
 *     captured").
 *   - Concrete over conceptual. Name the trigger condition that produces
 *     records, not the abstraction.
 *   - Sober. No exclamation points. No "Get started!" energy.
 *   - Reserved product phrases capitalized exactly where they appear
 *     (Apex Workflow, etc.).
 *
 * Examples:
 *   eyebrow="Workflow 06 · Model Risk & AI"
 *   headline="No decisions captured here yet."
 *   body="Decisions appear when a model output, override, or governance
 *        event creates a signal. The first signal arrives when you connect
 *        a model output source or create a governance event manually."
 *   actions=<><Button arrow>Connect a source</Button>
 *           <Button variant="ghost" arrow>Create a decision record</Button></>
 */
export function EmptyState({
  eyebrow,
  headline,
  body,
  actions,
  className,
}: {
  eyebrow?: ReactNode;
  headline: ReactNode;
  body?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <Card
      variant="featured"
      className={cn("max-w-2xl px-8 py-9", className)}
    >
      {eyebrow && (
        <div className="text-mono-label uppercase text-navy-deep">
          {eyebrow}
        </div>
      )}
      <h2
        className={cn(
          "text-[22px] font-medium leading-[1.25] tracking-tight text-navy-deep",
          eyebrow ? "mt-3" : "",
        )}
      >
        {headline}
      </h2>
      {body && (
        <div className="mt-3 text-[14px] leading-relaxed text-ink-soft">
          {body}
        </div>
      )}
      {actions && (
        <div className="mt-5 flex flex-wrap items-center gap-3">{actions}</div>
      )}
    </Card>
  );
}
