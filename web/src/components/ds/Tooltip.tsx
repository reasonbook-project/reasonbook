// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Institutional tooltip primitive. Restrained per design-system §6 —
 * 0.5px navy-tint border, ink text, navy-tint ground. No drop shadow,
 * no animation flourish beyond Radix's default fade-in.
 *
 * Use sparingly. Today's only callers are the inbox scope + density
 * toggles where the labels alone don't read as self-explanatory for a
 * cold signup. Adding tooltips elsewhere requires a real reason — the
 * institutional register is restraint, and tooltips are easy to over-use.
 */
export function Tooltip({
  content,
  children,
  side = "top",
  delayDuration = 200,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  delayDuration?: number;
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={delayDuration}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            sideOffset={6}
            className={cn(
              "max-w-[280px] rounded-md border-[0.5px] border-rule bg-navy-tint px-3 py-2 text-[12px] leading-[1.45] text-ink",
              "data-[state=delayed-open]:animate-in data-[state=delayed-open]:fade-in-0",
            )}
          >
            {content}
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}
