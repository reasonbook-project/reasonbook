// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";

import type { Alert, DispositionAction } from "@/api/alerts";
import { DispositionDrawer } from "@/components/alerts/DispositionDrawer";
import { DecisionRecordsPanel } from "@/components/awards/DecisionRecordsPanel";
import { ControlPointsPanel } from "@/components/matters/ControlPointsPanel";
import { type Matter, type MatterNode, type RfrRow } from "@/api/matters";
import { useMatterRfrs } from "@/hooks/useMatters";
import { cn } from "@/lib/cn";

/**
 * Inspector body — single wide column for a matter's case file.
 *
 * Header subtitle now carries the at-a-glance award identification
 * (agency · program · period · $ obligated · originating decision),
 * so the Record lane's Award ID card retired 2026-07-08. Process
 * adherence moved into this stack too — with those two out of the
 * Record lane, the Record lane itself dissolves and Work spans the
 * full width.
 *
 * Reading order (top-to-bottom, all in Work):
 *   1. FundFlowHorizontal — visual anchor. Show operators the flow
 *      before they see the queue.
 *   2. AttentionHero — open RFRs + open signals as action cards.
 *      Empty state collapses to a reassuring "quiet matter" line.
 *   3. DecisionRecordsPanel — per-tier decision tree.
 *   4. ProcessAdherenceCard — control-point roll-up.
 */
export function InspectorBody({
  matter,
  expandedDecisionId,
  onExpandDecision,
}: {
  matter: Matter;
  expandedDecisionId?: string | null;
  onExpandDecision?: (decisionId: string | null) => void;
}) {
  const rfrsQuery = useMatterRfrs(matter.id, "open");
  const openRfrs = rfrsQuery.data?.items ?? [];

  const decisionCountsByTier = useMemo(() => {
    const nodeById = new Map(matter.nodes.map((n) => [n.id, n]));
    const buckets = { federal: 0, state: 0, recipient: 0 };
    for (const d of matter.decisions) {
      let tier: string | null = null;
      if (d.matter_node_id) {
        tier = nodeById.get(d.matter_node_id)?.tier ?? null;
      } else if (d.is_originating) {
        tier = "federal";
      }
      if (tier === "federal") buckets.federal += 1;
      else if (tier === "state") buckets.state += 1;
      else if (tier === "recipient") buckets.recipient += 1;
    }
    return buckets;
  }, [matter.decisions, matter.nodes]);

  return (
    <div className="pl-6 pr-10 py-6 space-y-5">
      <FundFlowHorizontal matter={matter} />
      <AttentionHero matter={matter} rfrs={openRfrs} />
      <section
        className={cn(
          "overflow-hidden rounded-md border-[0.5px] bg-paper",
          expandedDecisionId ? "border-navy" : "border-rule-soft",
        )}
      >
        <div className="flex w-full items-center gap-2 border-b-[0.5px] border-rule-soft bg-paper-warm px-4 py-2">
          <i className="ti ti-file-text text-[14px] text-ink-muted" />
          <span className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-ink">
            Decision records
          </span>
        </div>
        <div className="space-y-3 px-2 py-2">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <DecisionTierStat
              label="Federal"
              value={decisionCountsByTier.federal}
            />
            <DecisionTierStat
              label="State"
              value={decisionCountsByTier.state}
            />
            <DecisionTierStat
              label="Recipient"
              value={decisionCountsByTier.recipient}
            />
            <DecisionTierStat
              label="Total"
              value={matter.decisions.length}
            />
          </div>
          <DecisionRecordsPanel
            matter={matter}
            workflowId={matter.program_id}
            onOpenDecision={(id) => onExpandDecision?.(id)}
            expandedDecisionId={expandedDecisionId ?? null}
            onCollapseDecision={
              onExpandDecision ? () => onExpandDecision(null) : undefined
            }
          />
        </div>
      </section>
      <ProcessAdherenceCard matter={matter} />
    </div>
  );
}

function DecisionTierStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3">
      <div className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
        {label}
      </div>
      <div className="mt-1 text-[24px] font-medium leading-none text-brand-ink">
        {value}
      </div>
    </div>
  );
}

/* ─── Attention hero ─────────────────────────────────────────────────── */

function AttentionHero({
  matter,
  rfrs,
}: {
  matter: Matter;
  rfrs: RfrRow[];
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [triageAction, setTriageAction] =
    useState<DispositionAction | null>(null);
  const hasSignal = Boolean(matter.signal);
  const count = rfrs.length + (hasSignal ? 1 : 0);

  if (count === 0) {
    return (
      <div className="flex items-center gap-2 rounded-md border-[0.5px] border-rule-soft bg-paper-warm px-4 py-3">
        <i className="ti ti-shield-check text-[16px] text-cleared" />
        <span className="text-body-sm text-ink-soft">
          This matter is quiet — nothing needs you now.
        </span>
      </div>
    );
  }

  return (
    <section className="overflow-hidden rounded-md border-[0.5px] border-rule-soft bg-paper">
      <header className="flex items-center justify-between border-b-[0.5px] border-rule-soft bg-paper-warm px-4 py-2">
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-ink">
          Needs you now
        </span>
        <span className="font-mono text-[11px] text-ink-faint">
          {count} item{count === 1 ? "" : "s"}
        </span>
      </header>
      <div className="grid grid-cols-1 gap-3 p-3 sm:grid-cols-2">
        {rfrs.map((rfr) => (
          <RfrActionCard
            key={rfr.id}
            rfr={rfr}
            onOpen={() =>
              void navigate({ to: `/matters/${matter.id}/response` })
            }
          />
        ))}
        {matter.signal && (
          <SignalActionCard
            signal={matter.signal}
            onTriage={setTriageAction}
          />
        )}
      </div>
      {matter.signal && triageAction && (
        <DispositionDrawer
          alert={matterSignalToAlert(matter.signal, matter)}
          action={triageAction}
          onClose={() => setTriageAction(null)}
          onDispositioned={() => {
            void qc.invalidateQueries({ queryKey: ["matter", matter.id] });
            void qc.invalidateQueries({ queryKey: ["matters"] });
            void qc.invalidateQueries({ queryKey: ["alerts"] });
          }}
        />
      )}
    </section>
  );
}

/** Adapt a MatterSignal (summary payload attached to the matter) to the
 *  Alert shape DispositionDrawer expects. The drawer only reads `id`,
 *  `title`, and `severity`; the remaining fields are stubbed with the
 *  matter's context so the object typechecks. */
function matterSignalToAlert(
  signal: NonNullable<Matter["signal"]>,
  matter: Matter,
): Alert {
  return {
    id: signal.alert_id,
    tenant_id: "",
    source: "flow_graph",
    signal_ref: {},
    severity:
      signal.severity === "critical" ||
      signal.severity === "high" ||
      signal.severity === "medium" ||
      signal.severity === "low"
        ? signal.severity
        : "medium",
    subject_entity: {},
    matter_id: matter.id,
    fund_flow_ref: [],
    title: signal.title,
    body: signal.body,
    target_program_id: matter.program_id,
    detected_at: new Date().toISOString(),
    current_status: "new",
  };
}

function RfrActionCard({
  rfr,
  onOpen,
}: {
  rfr: RfrRow;
  onOpen: () => void;
}) {
  return (
    <div className="flex flex-col rounded-md border-[0.5px] border-rule-soft border-l-[4px] border-l-accent-warning bg-paper p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full border-[0.5px] border-accent-warning/40 bg-accent-warning/10 px-2 py-0.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-accent-warning">
          <i className="ti ti-clock-hour-4 text-[11px]" />
          Response requested
        </span>
        <span className="font-mono text-[11px] text-ink-faint">
          {rfr.rfr_number}
        </span>
      </div>
      <h3 className="mb-1 font-display text-[14.5px] font-medium text-ink">
        {rfr.prompt_body}
      </h3>
      <p className="mb-3 text-body-sm text-ink-soft">
        Awaiting {rfr.target_party_name}.
      </p>
      <div className="mt-auto flex items-center justify-between">
        <span className="inline-flex items-center gap-1 text-[12px] text-ink-soft">
          <i className="ti ti-calendar-event text-[13px] text-accent-warning" />
          {formatDueLine(rfr.due_at)}
        </span>
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-1.5 rounded-md bg-navy px-3 py-1.5 font-display text-[12.5px] font-medium text-paper hover:bg-navy-deep"
        >
          Review
          <i className="ti ti-arrow-right text-[13px]" />
        </button>
      </div>
    </div>
  );
}

function SignalActionCard({
  signal,
  onTriage,
}: {
  signal: NonNullable<Matter["signal"]>;
  onTriage: (action: DispositionAction) => void;
}) {
  const severityLabel = signal.severity ? ` · ${signal.severity}` : "";
  return (
    <div className="flex flex-col rounded-md border-[0.5px] border-rule-soft border-l-[4px] border-l-flag bg-paper p-4">
      <div className="mb-2 flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full border-[0.5px] border-flag/40 bg-flag/10 px-2 py-0.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.08em] text-flag">
          <i className="ti ti-alert-triangle text-[11px]" />
          Open signal{severityLabel}
        </span>
      </div>
      <h3 className="mb-1 font-display text-[14.5px] font-medium text-ink">
        {signal.title}
      </h3>
      {signal.body && (
        <p className="mb-3 text-body-sm text-ink-soft">{signal.body}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-[12px] text-ink-soft">
          <i className="ti ti-flame text-[13px] text-flag" />
          {signal.kind === "tier_skip" && signal.skipped_tier
            ? `${signal.skipped_tier} skipped`
            : "No decision on record"}
        </span>
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onTriage("promote")}
            className="rounded-md bg-navy px-2.5 py-1 font-display text-[12px] font-medium text-paper hover:bg-navy-deep"
          >
            Promote
          </button>
          <button
            type="button"
            onClick={() => onTriage("dismiss")}
            className="rounded-md border-[0.5px] border-rule bg-paper px-2.5 py-1 font-display text-[12px] font-medium text-ink hover:bg-bg-warm"
          >
            Dismiss
          </button>
          <button
            type="button"
            onClick={() => onTriage("hold")}
            className="rounded-md border-[0.5px] border-rule bg-paper px-2.5 py-1 font-display text-[12px] font-medium text-ink hover:bg-bg-warm"
          >
            Hold
          </button>
        </div>
      </div>
    </div>
  );
}

function formatDueLine(due: string | null): string {
  if (!due) return "No due date";
  const then = new Date(due);
  const now = new Date();
  const days = Math.round(
    (then.getTime() - now.getTime()) / (1000 * 60 * 60 * 24),
  );
  const day = then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  if (days < 0) return `Overdue ${-days}d · ${day}`;
  if (days === 0) return `Due today · ${day}`;
  return `Due in ${days}d · ${day}`;
}

/* ─── Fund flow (horizontal 3-tier) ──────────────────────────────────── */
//
// Per docs/architecture/fund-flow-visual-rules.md.
//
// Two rendering shapes:
//   1. Arc-bypass — fires when a tier-skip signal names a skipped tier.
//      Renders a red arc from the tier before the gap to the tier after,
//      with the skipped tier as a dashed ghost placeholder below the
//      arc. Arc is the ONLY red element in the graph — boxes stay
//      neutral, identity signals do NOT paint their subject red, banner
//      loses its warm wash. Rationale: when everything is red, red
//      stops meaning anything; the tier-skip is a fact about the hop,
//      not about the institutions on either end.
//   2. Grid — the default. Three tiers connected by straight edges.
//      Per-signal attribution paints specific nodes / edges red
//      (identity → subject node; flow_graph anomaly → the edges).
//
// Canonical tier labels (see project_canonical_vocabulary):
//   Position 1 (data tier=federal)   → "Federal"
//   Position 2 (data tier=state)     → "State pass-through"
//   Position 3 (data tier=recipient) → "Recipient"

type MatterSignalLike = Matter["signals"][number];

type FlowAttribution = {
  hasAnySignal: boolean;
  arcActive: boolean;
  stateNodeRed: boolean;
  recipientNodeRed: boolean;
  stateSkipped: boolean;
  recipientSkipped: boolean;
  agencyToStateEdgeRed: boolean;
  stateToRecipientEdgeRed: boolean;
  bannerTitles: string[];
  signalCount: number;
  /** Short-form for the header when the arc explains the exception —
   *  e.g. "state pass-through bypassed". Empty string in grid mode. */
  arcHeaderNote: string;
  /** Actor-named arc label — e.g. "$1.8M · HHS bypassed the state
   *  pass-through". Empty string in grid mode. */
  arcLabel: string;
};

function attributeSignals(
  signals: MatterSignalLike[],
  matter: Matter,
  state: MatterNode | null,
  recipient: MatterNode | null,
): FlowAttribution {
  const attr: FlowAttribution = {
    hasAnySignal: signals.length > 0,
    arcActive: false,
    stateNodeRed: false,
    recipientNodeRed: false,
    stateSkipped: false,
    recipientSkipped: false,
    agencyToStateEdgeRed: false,
    stateToRecipientEdgeRed: false,
    bannerTitles: [],
    signalCount: signals.length,
    arcHeaderNote: "",
    arcLabel: "",
  };

  // First pass — determine arc mode. A state-tier-skip signal triggers
  // the arc-bypass shape; skipped_tier=recipient is not yet supported
  // as an arc rendering (falls through to grid).
  const stateTierSkipSignal = signals.find(
    (s) =>
      (s.source === "tier_skip" || s.kind === "tier_skip") &&
      s.skipped_tier === "state",
  );
  attr.arcActive = Boolean(stateTierSkipSignal);

  if (attr.arcActive && stateTierSkipSignal) {
    attr.stateSkipped = true; // ghost renders regardless of pseudo-org
    attr.arcHeaderNote = "state pass-through bypassed";
    const actor = shortAgencyName(matter.awarding_agency);
    const totalLabel = formatDollars(matter.amount_obligated);
    attr.arcLabel = `${totalLabel} · ${actor} bypassed the state pass-through`;
  }

  // Second pass — banner list + non-arc per-element attribution.
  for (const sig of signals) {
    const source = sig.source ?? sig.kind ?? "";
    const isTierSkip = source === "tier_skip" || sig.kind === "tier_skip";

    // Banner: substitute tier-skip's full title with just "Tier-skip"
    // in arc mode — the arc already carries the actor + action, so
    // repeating it in the banner is noise.
    if (isTierSkip && attr.arcActive) {
      attr.bannerTitles.push("Tier-skip");
    } else {
      attr.bannerTitles.push(sig.title);
    }

    if (attr.arcActive) {
      // Arc mode: the arc is the only red element in the graph. No
      // per-element attribution on nodes or edges — identity signals,
      // flow-graph anomalies, and additional tier-skip variants all
      // surface via the banner.
      continue;
    }

    // Grid mode: existing per-element attribution.
    if (isTierSkip) {
      if (sig.skipped_tier === "recipient") {
        attr.recipientNodeRed = true;
        attr.recipientSkipped = !recipient;
        attr.stateToRecipientEdgeRed = true;
      }
      // state-tier skip in grid mode shouldn't happen (arc would be
      // active); no-op if it does.
      continue;
    }

    if (source === "identity" && sig.subject_participant_org_id) {
      if (state?.participant_org_id === sig.subject_participant_org_id) {
        attr.stateNodeRed = true;
      } else if (
        recipient?.participant_org_id === sig.subject_participant_org_id
      ) {
        attr.recipientNodeRed = true;
      }
      continue;
    }

    if (source === "flow_graph") {
      attr.agencyToStateEdgeRed = true;
      attr.stateToRecipientEdgeRed = true;
      continue;
    }
  }

  return attr;
}

/** Best-effort short form of a federal agency for the arc label —
 *  e.g. "Department of Health and Human Services" → "HHS". Falls back
 *  to the full name if no acronym mapping matches. */
function shortAgencyName(full: string): string {
  const s = full.toLowerCase();
  if (s.includes("health and human services")) return "HHS";
  if (s.includes("agriculture")) return "USDA";
  if (s.includes("defense")) return "DoD";
  if (s.includes("state")) return "DoS";
  if (s.includes("housing and urban development")) return "HUD";
  if (s.includes("education")) return "ED";
  if (s.includes("labor")) return "DOL";
  if (s.includes("veterans")) return "VA";
  if (s.includes("treasury")) return "Treasury";
  if (s.includes("justice")) return "DOJ";
  if (s.includes("energy")) return "DOE";
  if (s.includes("transportation")) return "DOT";
  if (s.includes("interior")) return "DOI";
  if (s.includes("commerce")) return "DOC";
  if (s.includes("homeland security")) return "DHS";
  return full;
}

function FundFlowHorizontal({ matter }: { matter: Matter }) {
  const active = matter.nodes.filter((n) => !n.removed_at);
  const state = active.find((n) => n.tier === "state") ?? null;
  const recipient = active.find((n) => n.tier === "recipient") ?? null;

  const signals = matter.signals ?? (matter.signal ? [matter.signal] : []);
  const attr = attributeSignals(signals, matter, state, recipient);

  const showStatePosition = Boolean(state) || attr.stateSkipped;
  const showRecipientPosition = Boolean(recipient) || attr.recipientSkipped;
  const nodeCount =
    1 + (showStatePosition ? 1 : 0) + (showRecipientPosition ? 1 : 0);
  const edgeCount = Math.max(nodeCount - 1, 0);
  const totalLabel = formatDollars(matter.amount_obligated);

  // Header meta reflects the shape. Arc mode names the exception
  // directly; grid mode counts tiers + hops.
  const metaLine = attr.arcActive
    ? `3 tiers expected · 1 hop actual · ${totalLabel} obligated`
    : `${nodeCount} tier${nodeCount === 1 ? "" : "s"} · ${edgeCount} hop${edgeCount === 1 ? "" : "s"} · ${totalLabel} obligated`;

  // Panel + banner styling: arc mode drops the warm-red wash so the
  // arc is the only red thing in the frame. Grid mode keeps the wash
  // as a matter-level "there's a signal here" cue.
  const panelBorderCls = attr.arcActive
    ? "border-rule-soft"
    : attr.hasAnySignal
      ? "border-flag/40"
      : "border-rule-soft";
  const headerBgCls = attr.arcActive
    ? "border-rule-soft bg-paper-warm"
    : attr.hasAnySignal
      ? "border-flag/30 bg-flag/5"
      : "border-rule-soft bg-paper-warm";
  const bodyBgCls = attr.arcActive
    ? "bg-navy-tint"
    : attr.hasAnySignal
      ? "bg-flag/5"
      : "bg-bg-warm";

  return (
    <section
      className={cn(
        "overflow-hidden rounded-md border-[0.5px] bg-paper",
        panelBorderCls,
      )}
    >
      <header
        className={cn(
          "flex items-center justify-between border-b-[0.5px] px-4 py-2",
          headerBgCls,
        )}
      >
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-ink">
          Fund flow
        </span>
        <span className="font-mono text-[11px] text-ink-faint">{metaLine}</span>
      </header>
      <div
        className={cn(
          "flex justify-center px-8 pb-4",
          attr.arcActive ? "pt-16" : "pt-8",
          bodyBgCls,
        )}
      >
        {/* Inner shell — fixed content width so the arc SVG's coord
            system aligns to the actual box positions regardless of
            panel width. Three boxes (200px each) + two spacers (80px
            each) = 760px. */}
        <div
          className="relative"
          style={{ width: attr.arcActive ? 760 : undefined }}
        >
          {attr.arcActive && (
            <>
              {/* Arc SVG sits in its own strip ABOVE the boxes.
                  -top-8 puts the SVG bottom edge exactly at the box
                  top edge; h-8 (32px) gives room for the arc peak.
                  viewBox 760×32 with preserveAspectRatio=none maps
                  1:1 in x (shell is 760px) and 1:1 in y (SVG is 32px).
                  Arc endpoints at (100, 32) = Federal center-top;
                  (660, 32) = Recipient center-top. Peak at y=0. */}
              <svg
                className="pointer-events-none absolute inset-x-0 -top-8 h-8 w-full"
                viewBox="0 0 760 32"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                <path
                  d="M 100 32 C 100 0, 660 0, 660 32"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  className="text-flag"
                />
              </svg>
              <div className="pointer-events-none absolute left-1/2 -top-14 -translate-x-1/2 whitespace-nowrap rounded-sm bg-flag/5 px-1.5 py-0.5 font-mono text-[11px] font-medium text-flag">
                {attr.arcLabel}
              </div>
            </>
          )}

          <div className="flex items-center gap-0">
            <FlowNode
              role="Federal"
              name={matter.awarding_agency}
              amount={totalLabel}
              fault={false}
              neutral={attr.arcActive}
            />
            {attr.arcActive && <div className="w-[80px] flex-shrink-0" />}
            {!attr.arcActive && showStatePosition && (
              <FlowEdge label={totalLabel} fault={attr.agencyToStateEdgeRed} />
            )}
            {showStatePosition &&
              (attr.arcActive || attr.stateSkipped ? (
                <FlowNodeGhost role="State pass-through" />
              ) : (
                state && (
                  <FlowNode
                    role="State pass-through"
                    name={displayNameFor(state)}
                    amount={formatDollars(state.amount)}
                    fault={attr.stateNodeRed}
                  />
                )
              ))}
            {attr.arcActive && <div className="w-[80px] flex-shrink-0" />}
            {!attr.arcActive && showRecipientPosition && (
              <FlowEdge
                label={totalLabel}
                fault={attr.stateToRecipientEdgeRed}
              />
            )}
            {showRecipientPosition &&
              (recipient ? (
                <FlowNode
                  role="Recipient"
                  name={displayNameFor(recipient)}
                  amount={formatDollars(
                    recipient.amount ?? matter.amount_obligated,
                  )}
                  fault={attr.arcActive ? false : attr.recipientNodeRed}
                  neutral={attr.arcActive}
                />
              ) : (
                attr.recipientSkipped && <FlowNodeGhost role="Recipient" />
              ))}
          </div>
        </div>
      </div>
      {attr.hasAnySignal && (
        <div
          className={cn(
            "flex items-center gap-2 border-t-[0.5px] px-4 py-2 text-[12.5px]",
            attr.arcActive
              ? "border-rule-soft bg-paper-warm text-ink"
              : "border-flag/30 bg-flag/5 text-flag",
          )}
        >
          <i
            className={cn(
              "ti ti-alert-triangle text-[14px]",
              attr.arcActive ? "text-flag" : "text-flag",
            )}
          />
          <span>
            <strong className="font-medium">
              {attr.signalCount === 1
                ? "Risk signal."
                : `${attr.signalCount} risk signals.`}
            </strong>{" "}
            {attr.bannerTitles.join(" · ")}
          </span>
        </div>
      )}
    </section>
  );
}

function FlowNode({
  role,
  name,
  amount,
  fault,
  neutral = false,
}: {
  role: string;
  name: string;
  amount: string | null;
  fault: boolean;
  /** Arc mode — force neutral styling regardless of any signal
   *  attribution on this node. Border Rule, tier label navy, text Ink.
   *  The arc carries the red, so the boxes stay quiet. */
  neutral?: boolean;
}) {
  const borderCls = neutral
    ? "border-rule"
    : fault
      ? "border-flag"
      : "border-cleared";
  const roleColorCls = neutral
    ? "text-navy"
    : fault
      ? "text-flag"
      : "text-cleared";
  return (
    <div
      className={cn(
        "relative z-10 flex-shrink-0 rounded-[10px] border-[1.5px] bg-paper px-4 py-3 text-center",
        borderCls,
      )}
      style={{ width: 200 }}
    >
      <div
        className={cn(
          "mb-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em]",
          roleColorCls,
        )}
      >
        {role}
      </div>
      <div className="text-[13px] leading-snug text-ink">{name}</div>
      {amount && (
        <div className="mt-1 font-mono text-[10.5px] text-ink-soft">
          {amount}
        </div>
      )}
    </div>
  );
}

/** Ghost placeholder for a bypassed tier — dashed Rule border, muted
 *  text, always $0 (that's the point). Sits under the arc in arc mode,
 *  or on its own when a matter's data model has no ParticipantOrg for
 *  the skipped tier. */
function FlowNodeGhost({ role }: { role: string }) {
  return (
    <div
      className="relative z-10 flex-shrink-0 rounded-[10px] border-[1.5px] border-dashed border-rule bg-transparent px-4 py-3 text-center opacity-75"
      style={{ width: 200 }}
    >
      <div className="mb-1 font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-ink-muted">
        {role}
      </div>
      <div className="text-[12.5px] italic text-ink-muted">— skipped —</div>
      <div className="mt-1 font-mono text-[10.5px] text-ink-muted">$0</div>
    </div>
  );
}

function FlowEdge({ label, fault }: { label: string | null; fault: boolean }) {
  return (
    <div
      className="relative flex-shrink-0"
      style={{ width: 80, height: 2.5 }}
    >
      <div
        className={cn(
          "absolute inset-0",
          fault ? "bg-flag" : "bg-cleared",
        )}
      />
      {label && (
        <span
          className={cn(
            "absolute left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-[11px] font-medium",
            fault ? "text-flag" : "text-cleared",
          )}
          style={{ top: -20 }}
        >
          {label}
        </span>
      )}
    </div>
  );
}

function displayNameFor(node: MatterNode): string {
  return node.participant_org_name ?? node.tier;
}

function formatDollars(v: string | number | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1_000_000) {
    return `$${(n / 1_000_000).toFixed(1)}M`;
  }
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

/* ─── Process adherence ──────────────────────────────────────────────── */

function ProcessAdherenceCard({ matter }: { matter: Matter }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="overflow-hidden rounded-md border-[0.5px] border-rule-soft bg-paper">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 border-b-[0.5px] border-rule-soft bg-paper-warm px-4 py-2 text-left hover:bg-bg-warm"
      >
        <i className="ti ti-checklist text-[14px] text-ink-muted" />
        <span className="font-mono text-[11px] font-medium uppercase tracking-[0.1em] text-ink">
          Process adherence
        </span>
        <i
          className={cn(
            "ml-auto text-[14px] text-ink-muted transition-transform",
            expanded ? "ti ti-chevron-up" : "ti ti-chevron-down",
          )}
        />
      </button>
      {expanded && (
        <div className="px-2 py-2">
          <ControlPointsPanel
            matterId={matter.id}
            matterOriginatingDecisionId={matter.originating_decision_id}
          />
        </div>
      )}
    </section>
  );
}
