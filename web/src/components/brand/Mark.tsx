// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import markColor from "@/assets/brand/mark-color.svg";
import markWhite from "@/assets/brand/mark-color-white.svg";
import { cn } from "@/lib/cn";

/**
 * The Reasonbook mark — stacked-books badge.
 *
 * `color` (default) — Reasonbook-blue tile with white book marks; use on
 * light grounds (login, examiner covers).
 * `white` — the book marks on a transparent ground; use on navy grounds
 * (brand bar), where the white cards read cleanly against the dark field.
 */
export function Mark({
  size = 28,
  variant = "color",
  className,
}: {
  size?: number;
  variant?: "color" | "white";
  className?: string;
}) {
  return (
    <img
      src={variant === "white" ? markWhite : markColor}
      width={size}
      height={size}
      alt="Reasonbook mark"
      className={cn("block shrink-0 select-none", className)}
      draggable={false}
    />
  );
}
