// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { Mark } from "@/components/brand/Mark";
import { cn } from "@/lib/cn";

/**
 * Loud-surface chrome for /login, /forgot-password, /reset-password,
 * /verify-email — the threshold lockup per design-system §5.3.
 *
 * Cream ground, mark at 80px, Inter weight 600 headline in
 * --navy-deep with tracking-tightest, a mono-eyebrow tagline between
 * hairline rules, italic tagline (one per surface), form slot below.
 */
export function AuthShell({
  headline,
  tagline,
  children,
  className,
  width = "sm",
}: {
  headline: ReactNode;
  tagline?: string;
  children?: ReactNode;
  className?: string;
  width?: "sm" | "md";
}) {
  const widthClass = width === "md" ? "max-w-md" : "max-w-sm";
  return (
    <main
      className={cn(
        "flex min-h-screen items-center justify-center bg-bg-warm px-6 py-16",
        className,
      )}
    >
      <div className={cn("w-full", widthClass)}>
        <div className="flex flex-col items-center text-center">
          <Mark size={80} />
          <h1 className="mt-8 text-page tracking-tightest text-navy-deep">
            {headline}
          </h1>
          <div className="mt-3 flex items-center gap-3 text-ink-faint">
            <span aria-hidden className="h-px w-8 bg-ink-faint/60" />
            <span className="text-mono-label uppercase">
              Fraud prevention for federal &amp; state grants
            </span>
            <span aria-hidden className="h-px w-8 bg-ink-faint/60" />
          </div>
          {tagline && (
            <p className="mt-5 text-[14px] italic text-ink-soft">{tagline}</p>
          )}
        </div>
        {children && <div className="mt-12">{children}</div>}
      </div>
    </main>
  );
}
