// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Chip } from "./Chip";

/**
 * Single source of truth for workflow surface status. Drives the chip
 * variant + label so consumers can't pass arbitrary strings.
 *
 *   - active:        Workflow is running and has decisions in flight.
 *   - setup_needed:  Workflow is entitled but not yet wired (no source,
 *                    no first decision).
 *   - apex:          Apex tier marker.
 */
export type WorkflowStatus = "active" | "setup_needed" | "apex";

const STATUS_DEFS: Record<
  WorkflowStatus,
  { label: string; variant: "default" | "warning" | "apex" }
> = {
  active: { label: "Active", variant: "default" },
  setup_needed: { label: "Setup needed", variant: "warning" },
  apex: { label: "Apex", variant: "apex" },
};

export function WorkflowStatusChip({
  status,
  className,
}: {
  status: WorkflowStatus;
  className?: string;
}) {
  const def = STATUS_DEFS[status];
  return (
    <Chip variant={def.variant} className={className}>
      {def.label}
    </Chip>
  );
}
