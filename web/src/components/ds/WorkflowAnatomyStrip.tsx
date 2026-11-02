// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Card } from "./Card";

/**
 * WorkflowAnatomyStrip per the workflow detail mockup.
 *
 * Renders the canonical Signal → Owner → Decision → Action → Outcome
 * lifecycle as a 5-up grid with arrow separators on desktop. Below the
 * `md` breakpoint the grid stacks vertically and the arrows become
 * downward chevrons.
 *
 * Wraps in Card.featured (--navy-tint bg, navy-soft border) to match
 * the editorial register of workflow detail pages.
 */
export type AnatomyStage = {
  /** Mono uppercase label, e.g. `Signal`, `Owner`. */
  label: string;
  /** Plain-language body line, e.g. `Model output or override event`. */
  body: string;
};

export function WorkflowAnatomyStrip({
  stages,
  title = "Workflow anatomy",
  className,
}: {
  stages: [
    AnatomyStage,
    AnatomyStage,
    AnatomyStage,
    AnatomyStage,
    AnatomyStage,
  ];
  title?: string;
  className?: string;
}) {
  return (
    <Card variant="featured" className={className}>
      <div className="text-mono-label uppercase text-navy-deep">{title}</div>
      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr] md:items-center md:gap-2">
        {stages.map((stage, idx) => (
          <Stage key={stage.label} stage={stage} isLast={idx === stages.length - 1} />
        ))}
      </div>
    </Card>
  );
}

function Stage({
  stage,
  isLast,
}: {
  stage: AnatomyStage;
  isLast: boolean;
}) {
  return (
    <>
      <div>
        <div className="text-mono-label uppercase text-navy">{stage.label}</div>
        <div className="mt-1 text-[13px] font-medium leading-tight text-ink">
          {stage.body}
        </div>
      </div>
      {!isLast && (
        <div
          aria-hidden
          className="text-center text-[16px] text-navy md:px-1"
        >
          {/* Right-arrow on md+, downward on stacked layout */}
          <span className="md:inline hidden">→</span>
          <span className="md:hidden inline">↓</span>
        </div>
      )}
    </>
  );
}
