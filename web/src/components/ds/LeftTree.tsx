// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode, useState } from "react";

import { cn } from "@/lib/cn";

/**
 * LeftTree — compositional tree container for the unified-surface
 * shell. Per the UI improvements design (see
 * docs/architecture/_archive/ui-improvements/), the tree contains the
 * "subordinate elements" of the current primary surface — agencies →
 * programs → matters on /matters, scope / stage / workflow on /inbox,
 * status / source / severity on /signals, etc.
 *
 * Composition:
 *
 *   <LeftTree>
 *     <LeftTree.Search placeholder="Search…" value={q} onChange={setQ} />
 *     <LeftTree.Section title="Scope">
 *       <LeftTree.Node selected count={12}>Mine</LeftTree.Node>
 *       <LeftTree.Node count={47}>Team</LeftTree.Node>
 *     </LeftTree.Section>
 *   </LeftTree>
 *
 * Sub-components attach as named exports on the LeftTree namespace so
 * call sites read declaratively without long import lists.
 */
function LeftTreeRoot({
  children,
  className,
  width = 300,
}: {
  children: ReactNode;
  className?: string;
  /** Default 300px — matches the unified-surface mockups. */
  width?: number;
}) {
  return (
    <aside
      style={{ width }}
      className={cn(
        "shrink-0 flex flex-col",
        "border-r-[0.5px] border-rule",
        "bg-bg-warm",
        className,
      )}
    >
      {children}
    </aside>
  );
}

function LeftTreeSearch({
  placeholder = "Search…",
  value,
  onChange,
}: {
  placeholder?: string;
  value?: string;
  onChange?: (v: string) => void;
}) {
  // Unwired callers get nothing rather than a dead controlled input —
  // typing was silently no-op'ing because React kept resetting `value`
  // to "" each render.
  if (value === undefined && onChange === undefined) return null;
  return (
    <div className="px-3.5 py-3 border-b-[0.5px] border-rule">
      <input
        type="search"
        placeholder={placeholder}
        value={value ?? ""}
        onChange={(e) => onChange?.(e.target.value)}
        className={cn(
          "w-full px-2.5 py-1.5",
          "border-[0.5px] border-rule rounded",
          "bg-paper text-[12px] text-ink-soft placeholder:text-ink-faint",
          "focus:outline-none focus:border-navy",
        )}
      />
    </div>
  );
}

function LeftTreeSection({
  title,
  children,
  className,
  collapsible = false,
  defaultOpen = false,
  summary,
}: {
  /** Plain string or a HelpTerm-wrapped node — the section header is
   *  small uppercase text; both render correctly inside it. */
  title?: ReactNode;
  children: ReactNode;
  className?: string;
  /** When true, the title becomes a clickable toggle with a caret. */
  collapsible?: boolean;
  /** Initial state when `collapsible` — defaults to closed. Facet
   *  sections come in closed so the tree body doesn't get pushed off
   *  screen; the reader opens what they want to filter on. */
  defaultOpen?: boolean;
  /** Small hint shown next to the title in the closed state so a
   *  reader who's collapsed the section can still see the current
   *  selection (e.g. "Open"). Only rendered when collapsible. */
  summary?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const showBody = collapsible ? open : true;
  return (
    <div
      className={cn(
        "py-2 border-b-[0.5px] border-rule-soft last:border-b-0",
        className,
      )}
    >
      {title &&
        (collapsible ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="flex w-full items-center gap-1.5 px-3.5 pt-1 pb-2 text-left text-[10px] tracking-[0.08em] uppercase text-ink-faint font-medium hover:text-ink-soft"
          >
            <span>{title}</span>
            {summary && !open && (
              <span className="normal-case tracking-normal text-ink-soft font-normal">
                · {summary}
              </span>
            )}
            <i
              aria-hidden
              className={cn(
                "ml-auto text-[14px] text-ink-muted",
                open ? "ti ti-chevron-down" : "ti ti-chevron-right",
              )}
            />
          </button>
        ) : (
          <div className="px-3.5 pt-1 pb-2 text-[10px] tracking-[0.08em] uppercase text-ink-faint font-medium">
            {title}
          </div>
        ))}
      {showBody && children}
    </div>
  );
}

/**
 * LeftTree.Node — a clickable row inside the tree.
 *
 * `level` controls indentation. 1 = top, 2 = nested (28px), 3 = doubly
 * nested (42px). Higher levels are visually de-emphasized.
 *
 * `dot` renders a small status indicator before the label (flag / amber
 * / green / muted). Use it for stage/status sections where color
 * encodes meaning.
 *
 * `count` renders an IBM Plex Mono number on the right.
 *
 * `twist` controls the expand/collapse glyph for parent nodes. Pass
 * "open" to render ▾, "closed" to render ▸, omit for leaf nodes.
 */
type Level = 1 | 2 | 3;
type Dot = "flag" | "amber" | "green" | "muted";

const LEVEL_PADDING_LEFT: Record<Level, string> = {
  1: "pl-3.5",
  2: "pl-7",
  3: "pl-[42px]",
};

const SELECTED_LEVEL_PADDING_LEFT: Record<Level, string> = {
  1: "pl-[12px]",
  2: "pl-[26px]",
  3: "pl-[40px]",
};

const DOT_COLOR: Record<Dot, string> = {
  flag: "bg-flag",
  amber: "bg-accent-warning",
  green: "bg-cleared",
  muted: "bg-ink-faint",
};

function LeftTreeNode({
  children,
  count,
  level = 1,
  selected = false,
  dot,
  twist,
  badge,
  onClick,
  className,
}: {
  children: ReactNode;
  count?: number | string;
  level?: Level;
  selected?: boolean;
  dot?: Dot;
  twist?: "open" | "closed";
  /** Free-form badge after the label (e.g., "tier-skip"). */
  badge?: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  const padding = selected
    ? SELECTED_LEVEL_PADDING_LEFT[level]
    : LEVEL_PADDING_LEFT[level];
  const textSize = level === 3 ? "text-[12.5px]" : "text-[13px]";
  const textColor = selected
    ? "text-ink"
    : level === 3
      ? "text-ink-soft"
      : "text-ink";
  const weight = level === 1 ? "font-medium" : "font-normal";

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full text-left pr-3.5 py-[5px]",
        "flex items-center gap-1.5",
        padding,
        textSize,
        textColor,
        weight,
        selected && "bg-navy-soft/40 border-l-2 border-navy",
        !selected && "hover:bg-bg-warm",
        "transition-colors",
        className,
      )}
    >
      {twist && (
        <span
          aria-hidden
          className={cn(
            "w-[10px] text-[9px]",
            twist === "open" ? "text-ink-muted" : "text-ink-faint",
          )}
        >
          {twist === "open" ? "▾" : "▸"}
        </span>
      )}
      {dot && (
        <span
          aria-hidden
          className={cn("w-1.5 h-1.5 rounded-full", DOT_COLOR[dot])}
        />
      )}
      <span className="flex-1 truncate">{children}</span>
      {badge && <span className="shrink-0">{badge}</span>}
      {count !== undefined && (
        <span className="font-mono text-[11px] text-ink-faint shrink-0">
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * LeftTree.Tabs — optional tab strip rendered just under the search
 * input. Used on /matters to switch between matter-types
 * (Matters / Cases / Disputes) that share the same hierarchy below.
 */
function LeftTreeTabs({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex px-3.5 gap-1 border-b-[0.5px] border-rule",
        className,
      )}
    >
      {children}
    </div>
  );
}

function LeftTreeTab({
  current = false,
  count,
  onClick,
  children,
}: {
  current?: boolean;
  count?: number | string;
  onClick?: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "px-2 py-2.5 text-[11px] tracking-[0.06em] uppercase font-medium",
        "border-b-[1.5px] -mb-px",
        current
          ? "text-ink border-navy"
          : "text-ink-muted border-transparent hover:text-ink-soft",
      )}
    >
      {children}
      {count !== undefined && (
        <span className="font-mono text-[10px] ml-1 normal-case tracking-normal text-ink-faint">
          {count}
        </span>
      )}
    </button>
  );
}

/**
 * Body wrapper that scrolls independently of search + tabs. Keep this
 * the only scrollable region so the search input stays anchored.
 */
function LeftTreeBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex-1 overflow-y-auto py-2", className)}>
      {children}
    </div>
  );
}

/**
 * LeftTree.CheckboxRow — multi-select facet row. Renders a small
 * checkbox on the left, an optional colored dot (semantic — flag /
 * amber / green / muted), the label, and the count on the right.
 *
 * Used on the /matters rail's Stage / Owner / Signals facet sections
 * where multiple options can be active simultaneously. Toggling calls
 * `onToggle(next)` — the checked state is fully controlled by the
 * caller.
 */
function LeftTreeCheckboxRow({
  children,
  count,
  dot,
  checked = false,
  onToggle,
  className,
}: {
  children: ReactNode;
  count?: number | string;
  dot?: Dot;
  checked?: boolean;
  onToggle?: (next: boolean) => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onToggle?.(!checked)}
      aria-pressed={checked}
      className={cn(
        "w-full flex items-center gap-2 pl-3.5 pr-3.5 py-[5px]",
        "text-[12.5px] text-ink hover:bg-bg-warm transition-colors",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "shrink-0 inline-flex items-center justify-center",
          "w-3 h-3 border-[0.5px] rounded-sm",
          checked
            ? "bg-navy border-navy text-paper"
            : "bg-paper border-rule",
        )}
      >
        {checked && (
          <span className="text-[9px] leading-none">✓</span>
        )}
      </span>
      {dot && (
        <span
          aria-hidden
          className={cn("shrink-0 w-1.5 h-1.5 rounded-full", DOT_COLOR[dot])}
        />
      )}
      <span className="flex-1 truncate text-left">{children}</span>
      {count !== undefined && (
        <span className="font-mono text-[11px] text-ink-faint shrink-0">
          {count}
        </span>
      )}
    </button>
  );
}

export const LeftTree = Object.assign(LeftTreeRoot, {
  Search: LeftTreeSearch,
  Section: LeftTreeSection,
  Node: LeftTreeNode,
  CheckboxRow: LeftTreeCheckboxRow,
  Tabs: LeftTreeTabs,
  Tab: LeftTreeTab,
  Body: LeftTreeBody,
});
