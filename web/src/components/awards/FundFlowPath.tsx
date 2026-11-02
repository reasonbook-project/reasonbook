// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { MatterNode } from "@/api/matters";
import { cn } from "@/lib/cn";

/**
 * Fund-flow path render. The visual spine of the demo — turns a
 * matter's federal→state→recipient tree into the prototype's
 * canonical "Agency → $X → Recipient → $Y → Subrecipient" chip line.
 *
 * Two variants:
 *  - `compact` — single row of small chips for inline Register / alert
 *    cards. Amount labels sit on the arrows.
 *  - `detail` — larger cards in the matter detail "Fund-flow path"
 *    surface. Same chip vocabulary, more breathing room.
 *
 * Two node modifiers:
 *  - `flag` — red border + soft red bg. Used for tier-skip / signal
 *    targets.
 *  - `ghost` — dashed border + muted text. Used for the skipped middle
 *    tier in a tier-skip signal (e.g. "State · — skipped —").
 *
 * The "— federal direct —" pseudo-state node we synthesize in the
 * matters loader is hidden by default — set `showFederalDirect` to
 * render it (debug / demo of the synthetic placeholder).
 */
export type PathNodeView = {
  tier: "federal" | "state" | "recipient";
  label: string;
  amount?: string | null;
  modifier?: "flag" | "ghost";
};

const FEDERAL_DIRECT_SENTINEL = "— federal direct —";

type Variant = "compact" | "detail";

export function FundFlowPath({
  nodes,
  variant = "compact",
  showFederalDirect = false,
  className,
  pathNote,
}: {
  nodes: PathNodeView[];
  variant?: Variant;
  showFederalDirect?: boolean;
  className?: string;
  /** Optional note rendered below the path (e.g. "$415k reached the
   *  subrecipient directly, skipping the state tier"). */
  pathNote?: string | null;
}) {
  const visible = showFederalDirect
    ? nodes
    : nodes.filter((n) => n.label !== FEDERAL_DIRECT_SENTINEL);

  if (visible.length === 0) {
    return (
      <div className={cn("text-body-sm italic text-ink-muted", className)}>
        Path not available.
      </div>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div
        className={cn(
          "flex items-stretch gap-1.5",
          variant === "compact" ? "flex-wrap" : "",
        )}
      >
        {visible.map((node, i) => (
          <PathSegment
            key={`${node.tier}-${node.label}-${i}`}
            node={node}
            variant={variant}
            isLast={i === visible.length - 1}
            edgeAmount={
              // Edge label shows the AMOUNT THAT ARRIVED AT THE NEXT
              // NODE — so it sits on the arrow between this node and
              // the next, sourced from the next node's amount.
              i < visible.length - 1 ? visible[i + 1]?.amount ?? null : null
            }
          />
        ))}
      </div>
      {pathNote && (
        <p className="flex items-start gap-1.5 text-[12px] text-ink-muted">
          <i className="ti ti-info-circle mt-[1px] text-critical-text" />
          {pathNote}
        </p>
      )}
    </div>
  );
}

function PathSegment({
  node,
  variant,
  isLast,
  edgeAmount,
}: {
  node: PathNodeView;
  variant: Variant;
  isLast: boolean;
  edgeAmount: string | null;
}) {
  return (
    <>
      <PathNode node={node} variant={variant} />
      {!isLast && (
        <PathArrow amount={edgeAmount} variant={variant} flagged={node.modifier === "flag"} />
      )}
    </>
  );
}

function PathNode({ node, variant }: { node: PathNodeView; variant: Variant }) {
  const tierLabel = TIER_LABEL[node.tier];
  const flag = node.modifier === "flag";
  const ghost = node.modifier === "ghost";

  const sizing =
    variant === "compact"
      ? "min-w-[120px] max-w-[260px] px-2.5 py-1.5"
      : "min-w-[160px] flex-1 px-3 py-2.5";

  const base =
    "flex-1 rounded-sm border-[0.5px] text-center transition-colors";

  const tierBase = ghost
    ? "border-dashed border-rule-soft bg-transparent text-ink-faint"
    : flag
      ? "border-critical-text/40 bg-critical/5"
      : node.tier === "federal"
        ? "border-tier-federal/30 bg-tier-federal/[0.04]"
        : node.tier === "state"
          ? "border-tier-state/30 bg-tier-state/[0.04]"
          : "border-tier-contractor/30 bg-tier-contractor/[0.04]";

  const tierTextColor = ghost
    ? "text-ink-faint"
    : flag
      ? "text-critical-text"
      : node.tier === "federal"
        ? "text-tier-federal"
        : node.tier === "state"
          ? "text-tier-state"
          : "text-tier-contractor";

  return (
    <div className={cn(base, tierBase, sizing)}>
      <div
        className={cn(
          "font-mono text-[9px] uppercase tracking-[0.08em]",
          tierTextColor,
        )}
      >
        {tierLabel}
      </div>
      <div
        className={cn(
          "mt-0.5 truncate font-medium text-ink",
          variant === "compact" ? "text-[12px]" : "text-body",
          ghost && "italic text-ink-faint",
        )}
        title={node.label}
      >
        {node.label}
      </div>
    </div>
  );
}

function PathArrow({
  amount,
  variant,
  flagged,
}: {
  amount: string | null;
  variant: Variant;
  flagged: boolean;
}) {
  const arrowColor = flagged ? "text-critical-text" : "text-ink-faint";
  return (
    <div className="flex flex-none flex-col items-center justify-center">
      {amount && (
        <span
          className={cn(
            "font-mono leading-tight",
            variant === "compact" ? "text-[10px]" : "text-[11px]",
            flagged ? "text-critical-text" : "text-ink-soft",
          )}
        >
          {amount}
        </span>
      )}
      <span className={cn("leading-none", arrowColor, variant === "compact" ? "text-[14px]" : "text-[16px]")}>
        →
      </span>
    </div>
  );
}

const TIER_LABEL: Record<PathNodeView["tier"], string> = {
  federal: "Agency",
  state: "State",
  recipient: "Recipient",
};

/* ───────────────────────────────────────────────────────────────────────────
 * Helpers — turn MatterNode[] into PathNodeView[] for the renderer.
 * ─────────────────────────────────────────────────────────────────────────── */

/**
 * Build the path from a matter's nodes. Walks federal root → first
 * state → that state's recipients. Multi-recipient matters render the
 * first recipient on the spine; subsequent recipients fan out below
 * (callers can render them separately).
 *
 * In the v1 demo, every node carries `amount` set by the matters
 * loader (or null for the synthetic CDBG matters).
 */
export function matterToPath(
  nodes: MatterNode[],
): { primary: PathNodeView[]; extras: PathNodeView[] } {
  const active = nodes.filter((n) => n.removed_at === null);
  const byParent: Record<string, MatterNode[]> = {};
  let federalRoot: MatterNode | undefined;
  for (const n of active) {
    if (n.parent_node_id === null && n.tier === "federal") {
      federalRoot = n;
    } else if (n.parent_node_id) {
      (byParent[n.parent_node_id] ??= []).push(n);
    }
  }

  if (!federalRoot) return { primary: [], extras: [] };

  const primary: PathNodeView[] = [
    {
      tier: "federal",
      label: federalRoot.participant_org_name ?? "Federal",
      amount: amount(federalRoot),
    },
  ];

  const states = byParent[federalRoot.id] ?? [];
  if (states.length === 0) return { primary, extras: [] };

  // Walk one state for the spine; show the rest as "extras" callers
  // can render alongside.
  const [firstState, ...restStates] = states;
  primary.push({
    tier: "state",
    label: firstState.participant_org_name ?? "State",
    amount: amount(firstState),
  });

  const recipients = byParent[firstState.id] ?? [];
  if (recipients.length > 0) {
    primary.push({
      tier: "recipient",
      label: recipients[0].participant_org_name ?? "Recipient",
      amount: amount(recipients[0]),
    });
  }

  const extras: PathNodeView[] = [];
  for (const s of restStates) {
    extras.push({
      tier: "state",
      label: s.participant_org_name ?? "State",
      amount: amount(s),
    });
  }
  for (const r of recipients.slice(1)) {
    extras.push({
      tier: "recipient",
      label: r.participant_org_name ?? "Recipient",
      amount: amount(r),
    });
  }
  return { primary, extras };
}

function amount(n: MatterNode): string | null {
  if (!n.amount) return null;
  const v = Number(n.amount);
  if (!Number.isFinite(v) || v === 0) return null;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}
