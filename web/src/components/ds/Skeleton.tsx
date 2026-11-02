// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

/**
 * Skeleton loader per section 4.3.
 *
 * Uses --rule-faint as the resting tint and --rule-soft as the pulse peak —
 * a subtle opacity oscillation, not shimmer. Loading is a brief moment, not
 * a feature to show off.
 *
 * The default Tailwind `animate-pulse` keyframe oscillates opacity between
 * 0.5 and 1.0; combined with --rule-faint that produces a barely-visible
 * pulse that disappears once data arrives.
 */
export function Skeleton({
  className,
  ...rest
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      aria-hidden
      className={cn("animate-pulse bg-rule-faint", className)}
      {...rest}
    />
  );
}

/**
 * Helper for the common decision-row skeleton shape — three full-width
 * rows divided by hairline rules. Matches the rendered DecisionRow height.
 */
export function SkeletonRows({ count = 3 }: { count?: number }) {
  return (
    <div className="px-4 py-4">
      {Array.from({ length: count }, (_, i) => (
        <Skeleton
          key={i}
          className="h-[64px] border-b border-rule-faint last:border-b-0 rounded-none"
        />
      ))}
    </div>
  );
}
