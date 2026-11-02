// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Single decision row in the queue drawer.
 *
 * Slim columns per D1 (real fields only):
 *   [DECISION_NUMBER] [CATEGORY PILL] [TITLE] [SLA] [ASSIGNEE INITIALS]
 *
 * Layout sized for a 480px drawer (D3). The decision_number column is
 * narrow because mono digits read cleanly at 86px; the assignee column
 * shows just the avatar (no name) to claw back width for the title.
 *
 * The entire row is a button — clicking anywhere navigates to the
 * full decision detail at /workflows/{workflowId}/decisions/{id}.
 * The spec's "Review" button is intentionally not rendered; row-click
 * is the unambiguous affordance and Tab + Enter satisfies keyboard
 * accessibility per spec §"Accessibility".
 *
 * Hover / focus surfaces a popover showing the full title + description
 * — useful because the title column truncates at the drawer's slim
 * width and a CRO often wants the rationale context before committing
 * to a click-through.
 */

import { Avatar } from "@/components/ds/Avatar";
import { CategoryPill } from "@/components/ds/CategoryPill";
import { SLAIndicator } from "@/components/ds/SLAIndicator";
import { cn } from "@/lib/cn";

import type { QueueDecision } from "@/api/decisionQueue";

export type DecisionQueueRowProps = {
  decision: QueueDecision;
  onSelect: (decision: QueueDecision) => void;
};

export function DecisionQueueRow({ decision, onSelect }: DecisionQueueRowProps) {
  const handleClick = () => onSelect(decision);
  const popoverId = `qrow-popover-${decision.id}`;
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={handleClick}
        aria-describedby={popoverId}
        className={cn(
          "grid w-full items-center gap-3 border-b border-rule-soft px-4 py-3 text-left transition-colors",
          "hover:bg-bg-warm focus-visible:bg-bg-warm focus-visible:outline-none",
        )}
        style={{ gridTemplateColumns: "86px 88px 1fr 64px 28px" }}
      >
        <span className="font-mono text-[12px] text-ink-soft">
          {decision.decision_number}
        </span>
        <span>
          {decision.category ? (
            <CategoryPill category={decision.category} />
          ) : (
            <span className="text-[11px] text-ink-faint">—</span>
          )}
        </span>
        <span className="truncate text-[13px] font-medium text-ink">
          {decision.title}
        </span>
        <span className="text-[12px] text-ink-soft">
          {decision.sla_deadline ? (
            <SLAIndicator deadline={decision.sla_deadline} />
          ) : (
            <span className="text-ink-faint">—</span>
          )}
        </span>
        <span className="justify-self-end">
          {decision.assignee ? (
            <span title={decision.assignee.name}>
              <Avatar initials={decision.assignee.initials} />
            </span>
          ) : (
            <span className="text-[11px] text-ink-faint">—</span>
          )}
        </span>
      </button>

      <RowPopover id={popoverId} decision={decision} />
    </div>
  );
}

/**
 * Hover-/focus-revealed popover anchored to the row.
 *
 * CSS-only — visibility keys off the parent's `group-hover` and
 * `group-focus-within` state. Pointer-events-none so it doesn't catch
 * hover and feedback-loop with the row's hover state. Positioned
 * just below the row with a 6px gap; max-width 360px to keep long
 * descriptions readable without wrapping into a wall of text.
 */
function RowPopover({ id, decision }: { id: string; decision: QueueDecision }) {
  return (
    <div
      id={id}
      role="tooltip"
      className={cn(
        "pointer-events-none absolute left-4 right-4 top-full z-10 mt-1 max-w-[360px] rounded-md",
        "border border-rule-soft bg-paper px-3 py-2.5 text-[12px] text-ink shadow-lg",
        "opacity-0 transition-opacity duration-150",
        "group-hover:opacity-100 group-focus-within:opacity-100",
      )}
    >
      <div className="font-medium leading-snug text-ink">{decision.title}</div>
      {decision.description && (
        <div className="mt-1.5 leading-snug text-ink-soft">
          {decision.description}
        </div>
      )}
      <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-faint">
        <span className="font-mono">{decision.decision_number}</span>
        {decision.assignee && (
          <>
            <span aria-hidden="true">·</span>
            <span>Owned by {decision.assignee.name}</span>
          </>
        )}
      </div>
    </div>
  );
}
