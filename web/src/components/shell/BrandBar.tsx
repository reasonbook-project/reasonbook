// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Link } from "@tanstack/react-router";

import { Mark } from "@/components/brand/Mark";
import { cn } from "@/lib/cn";

/**
 * BrandBar — the slim navy strip that sits above the workspace TopNav.
 *
 * Carries only product identity: mark (home link → /matters) and the
 * "Reasonbook" wordmark. Deliberately spartan — every extra
 * chip here permanently taxes vertical density on every route.
 */
export function BrandBar({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex items-center h-9 px-5",
        "bg-navy-deep",
        "border-b-[0.5px] border-white/10",
        className,
      )}
    >
      <Link
        to="/matters"
        aria-label="Reasonbook home"
        className="flex items-center gap-2.5 focus:outline-none focus:ring-2 focus:ring-white/40 rounded-sm"
      >
        <Mark variant="white" size={22} />
        <span className="font-display font-semibold text-[13.5px] tracking-[-0.005em] text-white">
          Reasonbook
        </span>
      </Link>
    </div>
  );
}
