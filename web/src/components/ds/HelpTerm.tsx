// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import {
  glossary,
  type GlossaryKey,
  type GlossaryTerm,
} from "@/glossary/terms";
import { cn } from "@/lib/cn";

import { Tooltip } from "./Tooltip";

/**
 * HelpIcon — the small `?` glyph used as the default tooltip trigger.
 *
 * Sized to align with x-height of body copy. Uses the rule color at
 * rest, navy on hover, so it reads as a deliberate affordance without
 * shouting.
 */
export function HelpIcon({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        "inline-flex items-center justify-center",
        "w-[14px] h-[14px] rounded-full",
        "border-[0.5px] border-ink-faint text-ink-faint",
        "text-[9px] font-medium leading-none",
        "bg-paper",
        "hover:border-navy hover:text-navy cursor-help",
        className,
      )}
    >
      ?
    </span>
  );
}

/**
 * HelpTerm — wraps a term with a `?` icon that shows its glossary
 * definition on hover.
 *
 * Two usage shapes:
 *
 *   <HelpTerm term="archetype" />
 *     Renders the term's canonical label from the glossary plus the
 *     `?` icon.
 *
 *   <HelpTerm term="archetype">Decision type</HelpTerm>
 *     Renders the children as the label (for when context demands a
 *     different surface word) plus the `?` icon.
 *
 * The popover shows the term label, the definition, and (if defined)
 * a single concrete example. Keep glossary entries terse — see
 * glossary/terms.ts.
 *
 * Backed by the institutional Tooltip primitive (Radix-based). Hover
 * delay matches that primitive's default.
 */
export function HelpTerm({
  term,
  children,
  className,
  iconOnly = false,
  side = "top",
}: {
  term: GlossaryKey;
  children?: ReactNode;
  className?: string;
  /** Render just the `?` icon, no label. For dense layouts. */
  iconOnly?: boolean;
  side?: "top" | "right" | "bottom" | "left";
}) {
  // Cast widens the literal entry type so optional fields (example)
  // narrow correctly on access. The satisfies clause on the glossary
  // guarantees every entry conforms to GlossaryTerm.
  const entry: GlossaryTerm = glossary[term];
  const label = children ?? entry.label;

  const content = (
    <span className="block">
      <span className="block font-medium text-[12.5px] text-ink mb-0.5">
        {entry.label}
      </span>
      <span className="block text-ink-soft">{entry.definition}</span>
      {entry.example && (
        <span className="mt-1.5 pt-1.5 block border-t border-rule-soft text-[11px] italic text-ink-muted">
          {entry.example}
        </span>
      )}
    </span>
  );

  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {!iconOnly && <span>{label}</span>}
      <Tooltip content={content} side={side}>
        <span tabIndex={0} className="inline-flex">
          <HelpIcon />
        </span>
      </Tooltip>
    </span>
  );
}
