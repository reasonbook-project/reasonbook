// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

/**
 * Export button family per design-system §6.9.
 *
 * Two variants:
 *  - `primary`: brand-blue fill, white text — used when export is the only
 *    or dominant action on the surface (Decision Detail toolbar).
 *  - `outlined`: brand-blue text on transparent fill with a 0.5px brand-blue
 *    border — used when export shares the surface with other primary actions
 *    (settings header where Save dominates).
 */
export function ExportButton({
  variant = "primary",
  label,
  onClick,
  className,
  type = "button",
  disabled,
}: {
  variant?: "primary" | "outlined";
  label: string;
  onClick?: () => void;
  className?: string;
  type?: "button" | "submit";
  disabled?: boolean;
}) {
  // Disabled state desaturates to grayscale + drops opacity, so it's
  // unambiguously dead — distinct from the active state at any zoom or
  // viewport. Active primary keeps the brand-blue fill from the design
  // system (§3.1) plus a small drop-shadow for visual lift on light
  // grounds. The previous fix added a same-color ring (invisible) and
  // shadow-sm; the recorded "Record decision" button still read as
  // muted next to the cream form ground.
  const base =
    "inline-flex items-center justify-center rounded-md px-4 py-2 text-[13px] font-medium leading-none transition-colors disabled:cursor-not-allowed disabled:opacity-40 disabled:grayscale";
  const styles =
    variant === "primary"
      ? "bg-navy text-white shadow hover:bg-navy-deep hover:shadow-md"
      : "border-hairline border-navy text-navy hover:bg-navy/5";
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(base, styles, className)}
    >
      {label}
    </button>
  );
}
