// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type HTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/cn";

/**
 * Card primitives per the SaaS rebrand mockups (§3.7).
 *
 * Three variants:
 *   - default:  --paper bg, 1px --rule-soft border. The everyday card.
 *   - featured: --navy-tint bg, --navy-soft border. For workflow anatomy
 *               strips, editorial empty states, callouts.
 *   - apex:     --ink bg, white text. For the apex tier visual signal.
 *               Sparingly.
 *
 * No drop shadows. Hierarchy comes from spacing, not elevation.
 */
export type CardVariant = "default" | "featured" | "apex";

const VARIANT_CLASSES: Record<CardVariant, string> = {
  default: "border-rule-soft bg-paper text-ink",
  featured: "border-navy-soft bg-navy-tint text-ink",
  apex: "border-ink bg-ink text-paper",
};

export const Card = forwardRef<
  HTMLDivElement,
  HTMLAttributes<HTMLDivElement> & { variant?: CardVariant }
>(function Card(
  { variant = "default", className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        "rounded-md border p-6",
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    />
  );
});
