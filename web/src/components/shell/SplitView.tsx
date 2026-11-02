// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * SplitView — pairs a LeftTree (or any left aside) with a right
 * content surface. The right side claims the remaining width and
 * owns its own scroll.
 *
 * Used by every unified-shell surface (Matters, Inbox, Signals,
 * Oversight). Layout only; no chrome.
 */
export function SplitView({
  left,
  children,
  className,
}: {
  left: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-1 min-h-0 min-w-0", className)}>
      {left}
      <div className="flex-1 min-w-0 min-h-0 flex flex-col">{children}</div>
    </div>
  );
}
