// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * Institutional click-popover primitive. Sibling of `Tooltip` — same
 * restraint (0.5px rule border, ink text, paper ground, no drop shadow
 * beyond Radix's default), but opens on click and stays open until
 * dismissed (outside click, Escape, or the trigger toggled again).
 *
 * Use for content that's too long to live in a Tooltip but too small
 * to warrant a Drawer or Dialog. Today's primary caller is the help
 * affordance inside other drawers, where opening a second Drawer
 * conflicts with the first — see HelpLink `variant="popover"`.
 *
 * Width caps at 360px (wider than Tooltip's 280px to fit a short
 * article summary). Portals to body to escape parent overflow:hidden.
 */
export function Popover({
  trigger,
  children,
  side = "bottom",
  align = "start",
  sideOffset = 8,
  ariaLabel,
}: {
  trigger: ReactNode;
  children: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
  align?: "start" | "center" | "end";
  sideOffset?: number;
  ariaLabel?: string;
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          side={side}
          align={align}
          sideOffset={sideOffset}
          aria-label={ariaLabel}
          collisionPadding={12}
          className={cn(
            "z-[60] max-w-[360px] rounded-md border-[0.5px] border-rule bg-paper p-4 text-[13px] leading-[1.5] text-ink shadow-lg",
            "data-[state=open]:animate-in data-[state=open]:fade-in-0",
          )}
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
