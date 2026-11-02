// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

/**
 * Workflow identity marker per design-system §6.7.
 *
 * The chip itself stays neutral — secondary background, secondary text — and
 * the workflow's accent rides on a 5px dot to the left. Same colour value as
 * the workflow YAML's `workflow.color` field.
 */
export function WorkflowChip({
  name,
  color,
  className,
}: {
  name: string;
  color: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm bg-rule-faint px-[9px] py-[3px] text-caption text-ink-soft leading-none",
        className,
      )}
    >
      <span
        aria-hidden
        className="inline-block h-[5px] w-[5px] rounded-full"
        style={{ backgroundColor: color }}
      />
      {name}
    </span>
  );
}
