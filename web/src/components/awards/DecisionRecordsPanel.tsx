// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";

import type { Matter, MatterDecision } from "@/api/matters";
import { DecisionRecordCard } from "@/components/decision/DecisionRecordCard";
import { EvidenceDrawer } from "@/components/decision/EvidenceDrawer";
import { cn } from "@/lib/cn";

/**
 * Decision-records panel — surfaces the per-tier collection a matter
 * holds. Used in BOTH the Matters inspector and the Case file so the
 * "every consequential participant has a decision" framing reads the
 * same way wherever a matter's decisions appear.
 *
 * See docs/architecture/SURFACE-USER-STORIES.md for the model.
 */

const FEDERAL_DIRECT_SENTINEL = "— federal direct —";
const TIER_SKIPPED_SENTINEL = "— state skipped —";

type TierKey = "federal" | "state" | "recipient";

const TIER_LABEL: Record<TierKey, string> = {
  federal: "Federal",
  state: "State pass-through",
  recipient: "Recipient",
};

export function DecisionRecordsPanel({
  matter,
  workflowId,
  onOpenDecision,
  expandedDecisionId,
  onCollapseDecision,
  onOpenSignals,
}: {
  matter: Matter;
  workflowId: string;
  /** Called when a collapsed row is clicked. Consumers typically
   *  respond by updating the URL to set ?decision=<id>. */
  onOpenDecision: (decisionId: string, workflowId: string) => void;
  /** When set, that decision renders as an expanded composite card in
   *  place. Everything else stays collapsed. */
  expandedDecisionId?: string | null;
  /** Called when the expanded decision's close button is clicked. */
  onCollapseDecision?: () => void;
  /** Wired to the "See § 3 →" affordance on the Signal stage row. */
  onOpenSignals?: () => void;
}) {
  // Evidence-drawer state — one drawer per panel instance; the
  // decisionId scopes it to a specific card's chip when opened, or
  // stays null when the drawer is triggered from an all-on-matter
  // affordance (not yet exposed).
  const [evidenceOpen, setEvidenceOpen] = useState<string | null>(null);
  const openEvidence = (decisionId: string) => setEvidenceOpen(decisionId);
  const closeEvidence = () => setEvidenceOpen(null);

  // Open RFRs on this matter — rendered as the "Awaiting response"
  // section so a reviewer scanning §3 top-to-bottom sees outstanding
  // asks alongside the decisions they turn into.

  const { decisions, nodes } = matter;
  const activeNodes = nodes.filter((n) => n.removed_at === null);
  const nodeById = new Map(activeNodes.map((n) => [n.id, n]));

  type Slot = {
    tier: TierKey;
    nodeId: string | null;
    nodeName: string;
    isMissing: boolean;
    decisions: MatterDecision[];
  };

  const slots: Slot[] = [];

  // Federal slot — always present (federal root + originating decision)
  const federalRoot = activeNodes.find(
    (n) => n.tier === "federal" && n.parent_node_id === null,
  );
  const federalDecisions = decisions.filter(
    (d) =>
      d.is_originating ||
      (d.matter_node_id &&
        nodeById.get(d.matter_node_id)?.tier === "federal" &&
        d.signal_source === "tier_accept"),
  );
  slots.push({
    tier: "federal",
    nodeId: federalRoot?.id ?? null,
    nodeName: matter.awarding_agency,
    isMissing: federalDecisions.length === 0,
    decisions: federalDecisions,
  });

  // State slots
  const stateNodes = activeNodes.filter((n) => n.tier === "state");
  for (const stateNode of stateNodes) {
    const name = stateNode.participant_org_name ?? "State";
    const isPseudo = name === FEDERAL_DIRECT_SENTINEL;
    const isSkipped = name === TIER_SKIPPED_SENTINEL;
    if (isPseudo) continue;
    const stateDecisions = decisions.filter(
      (d) =>
        d.matter_node_id === stateNode.id && d.signal_source === "tier_accept",
    );
    slots.push({
      tier: "state",
      nodeId: stateNode.id,
      nodeName: isSkipped ? TIER_SKIPPED_SENTINEL : name,
      isMissing: isSkipped || stateDecisions.length === 0,
      decisions: stateDecisions,
    });
  }

  // Recipient slots
  const recipientNodes = activeNodes.filter((n) => n.tier === "recipient");
  for (const recipNode of recipientNodes) {
    const name = recipNode.participant_org_name ?? "Recipient";
    const recipDecisions = decisions.filter(
      (d) =>
        d.matter_node_id === recipNode.id && d.signal_source === "tier_accept",
    );
    slots.push({
      tier: "recipient",
      nodeId: recipNode.id,
      nodeName: name,
      isMissing: recipDecisions.length === 0,
      decisions: recipDecisions,
    });
  }

  // Layered actions (investigation, authority recommendations, etc.)
  const tierAcceptIds = new Set(
    slots.flatMap((s) => s.decisions.map((d) => d.id)),
  );
  const nonTierDecisions = decisions.filter((d) => !tierAcceptIds.has(d.id));
  // Party commitments (spec §6, A0-slice-2) — carved out into their
  // own section so a reviewer scanning §3 top-to-bottom finds them
  // next to the tier slots, not buried under "Investigative &
  // authority actions". Real Phase B collapses tier_accept + commitment
  // into one row per party per matter; A0 keeps them adjacent.
  const commitmentDecisions = nonTierDecisions.filter((d) => d.is_commitment);
  const layeredDecisions = nonTierDecisions.filter((d) => !d.is_commitment);

  // Recipient node display_names on this matter — used to flag
  // "off-tree party" commitments where the free-text
  // originating_party_name doesn't correspond to any actual
  // recipient node on the matter. Real Phase B resolves party from
  // the session so this can't happen; A0 makes it visible.
  const recipientDisplayNames = new Set(
    activeNodes
      .filter((n) => n.tier === "recipient" && n.participant_org_name)
      .map((n) => (n.participant_org_name as string).toLowerCase()),
  );
  const isOffTreeParty = (party: string | null | undefined): boolean => {
    if (!party) return false;
    if (recipientDisplayNames.size === 0) return false;
    return !recipientDisplayNames.has(party.toLowerCase());
  };

  return (
    <div className="bg-paper-warm/40">
      {/* Panel-level header used to repeat the "Decision records · N
          held" line here. Removed because Section renders its own
          eyebrow ("§4 · Decision records") above the panel — the two
          together read as a double eyebrow. The tagline moves to the
          matter-level tooltip on the section head. */}

      {/* Awaiting-response band retired 2026-07-08. The Inspector's
          AttentionHero (docs/demo/mockups/case-file-option-c.html)
          renders every open RFR as a top-of-body action card, so
          duplicating them here was pure noise. */}

      {slots.map((slot, i) => (
        <TierSlot
          key={`${slot.tier}-${slot.nodeId ?? i}`}
          slot={slot}
          workflowId={workflowId}
          onOpenDecision={(id) => onOpenDecision(id, workflowId)}
          expandedDecisionId={expandedDecisionId}
          onCollapseDecision={onCollapseDecision}
          onOpenSignals={onOpenSignals}
          onOpenEvidence={openEvidence}
        />
      ))}

      {commitmentDecisions.length > 0 && (
        <div className="border-t-[0.5px] border-rule-soft">
          <div className="flex items-baseline justify-between bg-ok-soft px-4 py-2 font-mono text-[10px] uppercase tracking-[0.08em] text-ok">
            <span>Party commitments</span>
            <span
              className="italic normal-case text-ink-faint"
              title="Legally-binding responses submitted by external parties per spec §6"
            >
              response-is-a-decision
            </span>
          </div>
          <ul className="divide-y-[0.5px] divide-rule-soft">
            {commitmentDecisions.map((d) =>
              d.id === expandedDecisionId ? (
                <li key={d.id} id={`dec-${d.id}`} className="p-2 bg-bg-warm/40">
                  <DecisionRecordCard
                    decision={d}
                    workflowId={workflowId}
                    onCollapse={onCollapseDecision}
                    onOpenSignals={onOpenSignals}
                    onOpenEvidence={() => openEvidence(d.id)}
                  />
                </li>
              ) : (
                <li key={d.id} id={`dec-${d.id}`}>
                  <DecisionRow
                    d={d}
                    onOpen={() => onOpenDecision(d.id, workflowId)}
                    offTreeParty={isOffTreeParty(d.originating_party_name)}
                  />
                </li>
              ),
            )}
          </ul>
        </div>
      )}

      {layeredDecisions.length > 0 && (
        <div className="border-t-[0.5px] border-rule-soft">
          <div className="bg-paper-warm/60 px-4 py-2 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
            Investigative & authority actions
          </div>
          <ul className="divide-y-[0.5px] divide-rule-soft">
            {layeredDecisions.map((d) =>
              d.id === expandedDecisionId ? (
                <li key={d.id} id={`dec-${d.id}`} className="p-2 bg-bg-warm/40">
                  <DecisionRecordCard
                    decision={d}
                    workflowId={workflowId}
                    onCollapse={onCollapseDecision}
                    onOpenSignals={onOpenSignals}
                    onOpenEvidence={() => openEvidence(d.id)}
                  />
                </li>
              ) : (
                <li key={d.id} id={`dec-${d.id}`}>
                  <DecisionRow
                    d={d}
                    onOpen={() => onOpenDecision(d.id, workflowId)}
                  />
                </li>
              ),
            )}
          </ul>
        </div>
      )}

      <EvidenceDrawer
        open={evidenceOpen !== null}
        onClose={closeEvidence}
        matter={matter}
        focusDecisionId={evidenceOpen}
        matterLabel={matter.program_id}
      />
    </div>
  );
}

function TierSlot({
  slot,
  workflowId,
  onOpenDecision,
  expandedDecisionId,
  onCollapseDecision,
  onOpenSignals,
  onOpenEvidence,
}: {
  slot: {
    tier: TierKey;
    nodeName: string;
    isMissing: boolean;
    decisions: MatterDecision[];
  };
  workflowId: string;
  onOpenDecision: (id: string) => void;
  expandedDecisionId?: string | null;
  onCollapseDecision?: () => void;
  onOpenSignals?: () => void;
  onOpenEvidence?: (decisionId: string) => void;
}) {
  const isSkippedTier = slot.nodeName === TIER_SKIPPED_SENTINEL;

  return (
    <div className="border-t-[0.5px] border-rule-soft first:border-t-0">
      <div
        className={cn(
          "flex items-baseline justify-between gap-2 px-4 py-1.5 font-mono text-[10px] uppercase tracking-[0.08em]",
          isSkippedTier
            ? "bg-[#fef2f2] text-[#9c1c1c]"
            : "bg-paper-warm/60 text-ink-faint",
        )}
      >
        <span>
          <span className="text-ink">{TIER_LABEL[slot.tier]}</span>
          <span className="mx-1.5 opacity-50">·</span>
          {isSkippedTier ? <em>{slot.nodeName}</em> : slot.nodeName}
        </span>
        {slot.isMissing && (
          <span className="normal-case italic text-[#9c1c1c]">
            {isSkippedTier
              ? "⚠ No decision on record — see tier-skip signal above"
              : "no decision on record"}
          </span>
        )}
      </div>
      {slot.decisions.length > 0 && (
        <ul className="divide-y-[0.5px] divide-rule-soft">
          {slot.decisions.map((d) =>
            d.id === expandedDecisionId ? (
              <li key={d.id} id={`dec-${d.id}`} className="p-2 bg-bg-warm/40">
                <DecisionRecordCard
                  decision={d}
                  workflowId={workflowId}
                  onCollapse={onCollapseDecision}
                  onOpenSignals={onOpenSignals}
                  onOpenEvidence={
                    onOpenEvidence ? () => onOpenEvidence(d.id) : undefined
                  }
                />
              </li>
            ) : (
              <li key={d.id} id={`dec-${d.id}`}>
                <DecisionRow d={d} onOpen={() => onOpenDecision(d.id)} />
              </li>
            ),
          )}
        </ul>
      )}
    </div>
  );
}

function DecisionRow({
  d,
  onOpen,
  offTreeParty,
}: {
  d: MatterDecision;
  onOpen: () => void;
  /** True when this Decision's originating_party_name doesn't match
   *  any recipient node on the matter — surfaced honestly so a demo
   *  submitted as the wrong party is visible, not silently accepted.
   *  Real Phase B eliminates this: party is resolved from the session,
   *  the form can't drift from the matter's actual recipient. */
  offTreeParty?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="grid w-full grid-cols-[auto_auto_auto_1fr_auto] items-baseline gap-3 border-l-[2px] border-transparent bg-paper py-2 pl-6 pr-4 text-left transition-colors hover:border-navy hover:bg-navy-soft/40"
    >
      <span
        aria-hidden
        className="text-[11px] text-ink-faint transition-colors group-hover:text-navy"
      >
        ›
      </span>
      <span className="font-mono text-[11px] uppercase tracking-[0.04em]">
        <StatusChip status={d.status} />
      </span>
      <span className="font-mono text-[11px] text-ink-faint">
        {d.decision_number}
      </span>
      <span className="truncate text-body-sm text-ink">
        {d.title}
        {d.is_originating && (
          <span className="ml-2 rounded-sm bg-[#dbeafe] px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.06em] text-[#134b86]">
            originating
          </span>
        )}
        {d.is_commitment && (
          <span
            className="ml-2 rounded-sm bg-ok-soft px-1.5 py-[1px] font-mono text-[10px] tracking-[0.06em] text-ok uppercase"
            title={
              d.originating_party_name
                ? `Commitment from ${d.originating_party_name}`
                : "Party commitment"
            }
          >
            commitment
          </span>
        )}
        {offTreeParty && d.originating_party_name && (
          <span
            className="ml-2 rounded-sm bg-amber-soft px-1.5 py-[1px] font-mono text-[10px] tracking-[0.06em] text-amber uppercase"
            title={`Party "${d.originating_party_name}" is not a recipient node on this matter — A0 demo workaround (real Phase B resolves party from the session).`}
          >
            off-tree party · {d.originating_party_name}
          </span>
        )}
      </span>
      <span className="font-mono text-[11px] text-ink-faint">
        {d.decided_at
          ? `decided ${formatRelative(d.decided_at)}`
          : d.created_at
            ? `opened ${formatRelative(d.created_at)}`
            : ""}
      </span>
    </button>
  );
}

function StatusChip({ status }: { status: string }) {
  const palette: Record<string, { fg: string; bg: string }> = {
    open: { fg: "#0d3a6a", bg: "#dbeafe" },
    assigned: { fg: "#15803d", bg: "#dcfce7" },
    in_progress: { fg: "#b7791f", bg: "#fef3c7" },
    decided: { fg: "#7c3aed", bg: "#ede9fe" },
    closed: { fg: "#54607a", bg: "#e2e8f0" },
    deferred: { fg: "#9c1c1c", bg: "#fee2e2" },
    escalated: { fg: "#9c1c1c", bg: "#fee2e2" },
  };
  const colors = palette[status] ?? { fg: "var(--t1)", bg: "transparent" };
  return (
    <span
      className="inline-block rounded-sm px-1.5 py-[1px]"
      style={{ color: colors.fg, background: colors.bg }}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

function formatRelative(iso: string): string {
  const d = new Date(iso);
  const diffMs = Date.now() - d.getTime();
  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (days < 1) return "today";
  if (days < 2) return "yesterday";
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

