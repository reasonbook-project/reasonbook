// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

/**
 * Urgency / state badge per design-system §6.8.
 *
 * Always renders dot + label. Dot is required for colour-blind accessibility:
 * the colour alone is not enough signal. Five variants line up with the
 * decision-status urgencies surfaced throughout the product.
 */
export type StatusVariant =
  | "critical"
  | "warning"
  | "info"
  | "resolved"
  | "deferred";

const VARIANT_STYLES: Record<
  StatusVariant,
  { wrap: string; dot: string }
> = {
  critical: {
    wrap: "bg-critical-bg text-critical-text",
    dot: "bg-critical-dot",
  },
  warning: {
    wrap: "bg-warning-bg text-warning-text",
    dot: "bg-warning-dot",
  },
  info: {
    wrap: "bg-info-bg text-info-text",
    dot: "bg-info-dot",
  },
  resolved: {
    wrap: "bg-resolved-bg text-resolved-text",
    dot: "bg-resolved-dot",
  },
  deferred: {
    wrap: "bg-rule-faint text-ink-soft",
    dot: "bg-ink-faint",
  },
};

export function StatusBadge({
  variant,
  label,
  className,
}: {
  variant: StatusVariant;
  label: string;
  className?: string;
}) {
  const styles = VARIANT_STYLES[variant];
  return (
    <span
      className={cn(
        "inline-flex w-fit items-center gap-1.5 whitespace-nowrap rounded-sm px-2 py-[3px] text-[11px] font-medium leading-none",
        styles.wrap,
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "inline-block h-[5px] w-[5px] shrink-0 rounded-full",
          styles.dot,
        )}
      />
      {label}
    </span>
  );
}
