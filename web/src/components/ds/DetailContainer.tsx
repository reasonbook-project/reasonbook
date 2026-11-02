// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import { cn } from "@/lib/cn";

import { ModeTabs, type Mode } from "./ModeTabs";

/**
 * DetailContainer — the right-side surface in the unified shell.
 * Composes the thin breadcrumb strip, header (title + subtitle +
 * actions), optional ModeTabs, and the body slot.
 *
 * This component is layout only. It doesn't know about modes' content;
 * the consumer renders the right body for the current mode.
 *
 * Composition example:
 *
 *   <DetailContainer
 *     breadcrumb={<Breadcrumb crumbs={[...]} />}
 *     title="ABLE FORCE, INC."
 *     subtitle="HUD · CDBG · FY26 · $8,500,000"
 *     actions={<><Button>Verify chain</Button>...</>}
 *     modes={[{id: "inspector", label: "Inspector"}, ...]}
 *     currentMode="inspector"
 *     onModeChange={setMode}
 *   >
 *     {bodyForCurrentMode}
 *   </DetailContainer>
 */
export function DetailContainer({
  breadcrumb,
  eyebrow,
  title,
  subtitle,
  actions,
  modes,
  currentMode,
  onModeChange,
  children,
  className,
}: {
  breadcrumb?: ReactNode;
  /** Small mono line above the title (e.g. "Inspector · Formal record…").
   *  Renders in the "regulatory register" style. */
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  modes?: Mode[];
  currentMode?: string;
  onModeChange?: (id: string) => void;
  children: ReactNode;
  className?: string;
}) {
  const showHeader = title || subtitle || actions || eyebrow;
  const showModes = modes && modes.length > 0 && currentMode && onModeChange;

  return (
    <section
      className={cn(
        "flex-1 min-w-0 min-h-0 flex flex-col bg-paper",
        className,
      )}
    >
      {breadcrumb && (
        <div className="px-6 py-2.5 bg-bg-warm border-b-[0.5px] border-rule text-[12px] text-ink-soft">
          {breadcrumb}
        </div>
      )}

      {showHeader && (
        <header
          className={cn(
            "px-6 pt-5",
            !showModes && "pb-5",
            "border-b-[0.5px]",
            showModes ? "border-transparent" : "border-rule",
          )}
        >
          <div className="min-w-0">
            {eyebrow && (
              <p className="mb-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-ink-faint">
                {eyebrow}
              </p>
            )}
            {title && (
              <h1 className="text-[22px] leading-tight font-display font-medium tracking-[-0.01em] text-ink mb-1">
                {title}
              </h1>
            )}
            {subtitle && (
              <p className="text-[12px] font-mono uppercase tracking-[0.04em] text-ink-muted">
                {subtitle}
              </p>
            )}
          </div>

          {actions && (
            <div className="mt-3 flex items-center gap-2">{actions}</div>
          )}

          {showModes && (
            <div className="mt-4 border-b-[0.5px] border-rule">
              <ModeTabs
                modes={modes}
                current={currentMode}
                onChange={onModeChange}
              />
            </div>
          )}
        </header>
      )}

      <div className="flex-1 h-0 min-h-0 overflow-y-auto overscroll-contain">
        {children}
      </div>
    </section>
  );
}

/**
 * Breadcrumb — thin clickable crumb trail rendered in the breadcrumb
 * strip of DetailContainer. Last crumb renders as `current` (not
 * clickable, slightly emphasized).
 */
export type BreadcrumbCrumb = {
  label: ReactNode;
  onClick?: () => void;
  current?: boolean;
};

export function Breadcrumb({
  crumbs,
  className,
}: {
  crumbs: BreadcrumbCrumb[];
  className?: string;
}) {
  return (
    <nav
      aria-label="Breadcrumb"
      className={cn("flex items-center flex-wrap gap-0", className)}
    >
      {crumbs.map((c, i) => (
        <span key={i} className="flex items-center">
          {i > 0 && <span aria-hidden className="mx-1.5 text-ink-faint">›</span>}
          {c.current || !c.onClick ? (
            <span
              className={cn(
                c.current ? "text-ink font-medium" : "text-ink-soft",
              )}
              aria-current={c.current ? "page" : undefined}
            >
              {c.label}
            </span>
          ) : (
            <button
              type="button"
              onClick={c.onClick}
              className="text-navy hover:underline"
            >
              {c.label}
            </button>
          )}
        </span>
      ))}
    </nav>
  );
}
