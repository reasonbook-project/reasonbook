// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import type { MatterDecision } from "@/api/matters";
import type { Decision } from "@/api/decisions";
import type { WorkflowAction } from "@/api/workflows";
import { ClaimButton } from "@/components/decision/ClaimButton";
import { CommitmentIntegrityCard } from "@/components/decision/CommitmentIntegrityCard";
import { hasFlagEvidence } from "@/components/decision/EvidenceDrawer";
import { FinalizeForm } from "@/components/decision/FinalizeForm";
import { ActionStageBody } from "@/components/decision/stages/ActionSection";
import { OutcomeStageBody } from "@/components/decision/stages/OutcomeSection";
import { useDecision, useDecisionEvents } from "@/hooks/useDecisions";
import { useWorkflowConfig } from "@/hooks/useWorkflows";
import { cn } from "@/lib/cn";
import { useAuthStore } from "@/stores/auth";

/**
 * DecisionRecordCard — the composite decision-record card per
 * docs/architecture/_archive/ui-improvements/04-decision-detail-options.html.
 *
 * Shape:
 *   Header (id · title · evidence chip · status pill · collapse ×)
 *   Progress strip (5 stages: Signal · Owner · Decision · Action · Outcome)
 *   5 stage sections:
 *     - Signal   collapsed to summary + link back to § 3 · Signals
 *     - Owner    compact one-liner
 *     - Decision expanded when current: options + rationale + record
 *                summary when done
 *     - Action   step tracker when current
 *                summary when done
 *                stub when pending
 *     - Outcome  final artifact when done
 *                stub when pending
 *
 * Evidence lives in a right-side drawer (built in a follow-up commit);
 * the chip in the header is the trigger.
 *
 * Signal → § 3 linking uses onOpenSignals; the case file already has
 * a § 3 · Signals section so we don't render signal details twice.
 */
export function DecisionRecordCard({
  decision,
  workflowId,
  onCollapse,
  onOpenSignals,
  onOpenEvidence,
  ownerName,
  ownerRole,
  ownerClaimedAt,
  signalSummary,
  className,
}: {
  decision: MatterDecision;
  /** Program / workflow id this decision belongs to. Drives the
   *  workflow-config lookup for the Decision-current pane
   *  (available_actions). Required to render the record-decision UI;
   *  when omitted, the Decision stage falls back to a read-only
   *  summary + a "Go to full record" pointer. */
  workflowId?: string;
  onCollapse?: () => void;
  onOpenSignals?: () => void;
  /** Wired to the header Evidence chip. When set, the chip becomes a
   *  button that opens the right-side drawer scoped to this decision. */
  onOpenEvidence?: () => void;
  ownerName?: string | null;
  ownerRole?: string | null;
  ownerClaimedAt?: string | null;
  signalSummary?: string | null;
  className?: string;
}) {
  // Load the full Decision once for the whole card — stages 3–5 all
  // need it (options + rationale, action edit form, outcome capture).
  // Loading state renders a placeholder inside each stage that needs
  // it; the header + progress strip render immediately from the
  // MatterDecision the parent already has.
  const decisionQuery = useDecision(decision.id);
  const fullDecision = decisionQuery.data;
  const currentUserId = useAuthStore((s) => s.user?.id);
  // Event count powers the Commitment integrity card's "on record"
  // line — skip the fetch when this isn't a commitment so non-
  // commitment rows don't pay for it.
  const eventsQuery = useDecisionEvents(
    decision.is_commitment ? decision.id : undefined,
    "audit",
  );
  const eventCount = eventsQuery.data?.items?.length ?? null;

  const stage = computeCurrentStage(decision);
  const terminalAtDecision = terminatedAtDecision(decision);
  const stateFor = (s: Stage): StageState => {
    // Stages 4 and 5 don't apply when the workflow terminates at
    // Decision. Return "not-applicable" so the strip renders them
    // dimmed with an empty ring instead of a completed-green dot.
    if (terminalAtDecision && (s === "action" || s === "outcome")) {
      return "not-applicable";
    }
    return stageState(s, stage);
  };
  const evidenceCount = (decision.evidence_refs ?? []).length;
  const hasFlag = hasFlagEvidence(decision);

  return (
    <article
      className={cn(
        "bg-navy-tint border-[1.5px] border-navy rounded-md overflow-hidden",
        className,
      )}
    >
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-3 border-b-[0.5px] border-rule-soft">
        <span className="font-mono text-[12px] text-navy-deep font-medium">
          {decision.decision_number}
        </span>
        <span className="text-[13.5px] text-ink font-medium truncate">
          {decision.title}
        </span>
        <div className="ml-auto flex items-center gap-2">
          <EvidenceChip
            count={evidenceCount}
            hasFlag={hasFlag}
            onOpen={onOpenEvidence}
          />
          <StatusPill status={decision.status} />
          {onCollapse && (
            <button
              type="button"
              onClick={onCollapse}
              className="text-[13px] text-ink-muted hover:text-ink px-1"
              aria-label="Collapse"
            >
              ×
            </button>
          )}
        </div>
      </header>

      {/* Progress strip */}
      <div className="grid grid-cols-5 border-b-[0.5px] border-rule">
        <StageCell
          idx={1}
          name="Signal"
          state={stateFor("signal")}
          meta="tier accept"
        />
        <StageCell
          idx={2}
          name="Owner"
          state={stateFor("owner")}
          meta={ownerName ?? undefined}
        />
        <StageCell
          idx={3}
          name="Decision"
          state={stateFor("decision")}
          meta={
            decision.decided_at
              ? formatShortDate(decision.decided_at)
              : stateFor("decision") === "current"
                ? "you are here"
                : "pending"
          }
        />
        <StageCell
          idx={4}
          name="Action"
          state={stateFor("action")}
          meta={
            stateFor("action") === "pending"
              ? "unlocks on decision"
              : stateFor("action") === "current"
                ? "in flight"
                : terminalAtDecision
                  ? "n/a"
                  : "complete"
          }
        />
        <StageCell
          idx={5}
          name="Outcome"
          state={stateFor("outcome")}
          meta={
            stateFor("outcome") === "pending"
              ? "unlocks on action"
              : stateFor("outcome") === "current"
                ? "in review"
                : terminalAtDecision
                  ? "n/a"
                  : "captured"
          }
        />
      </div>

      {/* Stage sections */}
      <div className="px-5 py-2">
        <StageSection
          num={1}
          name="Signal"
          state={stateFor("signal")}
        >
          <SignalRow
            summary={signalSummary}
            onOpenSignals={onOpenSignals}
          />
        </StageSection>

        <StageSection
          num={2}
          name="Owner"
          state={stateFor("owner")}
        >
          <OwnerRow
            name={ownerName}
            role={ownerRole}
            claimedAt={ownerClaimedAt}
            claimed={stateFor("owner") === "done"}
            fullDecision={fullDecision}
            currentUserId={currentUserId}
          />
        </StageSection>

        <StageSection
          num={3}
          name="Decision"
          state={stateFor("decision")}
        >
          <DecisionRow
            decision={decision}
            fullDecision={fullDecision}
            state={stateFor("decision")}
            workflowId={workflowId}
          />
        </StageSection>

        <StageSection
          num={4}
          name="Action"
          state={stateFor("action")}
        >
          <ActionRow
            state={stateFor("action")}
            fullDecision={fullDecision}
            terminalAtDecision={terminalAtDecision}
          />
        </StageSection>

        <StageSection
          num={5}
          name="Outcome"
          state={stateFor("outcome")}
          last
        >
          <OutcomeRow
            state={stateFor("outcome")}
            fullDecision={fullDecision}
            outcomeText={decision.outcome_text}
            terminalAtDecision={terminalAtDecision}
          />
        </StageSection>
      </div>

      {/* Commitment integrity — federal-PM audit-evidence panel that
          only renders for party commitments (spec §6). Sits below the
          5-stage anatomy so the standard record reads first and the
          integrity assertions land as an addendum. */}
      {decision.is_commitment && (
        <CommitmentIntegrityCard
          decision={decision}
          fullDecision={fullDecision}
          eventCount={eventCount}
        />
      )}
    </article>
  );
}

/* ─── Stage machinery ─────────────────────────────────────────────── */

export type Stage = "signal" | "owner" | "decision" | "action" | "outcome";
export type StageState = "done" | "current" | "pending" | "not-applicable";
/** "done" sentinel = terminal (status closed). No stage is "current". */
type EffectiveStage = Stage | "done";

function computeCurrentStage(d: MatterDecision): EffectiveStage {
  // Terminal — status closed. Every stage collapses to "done"; no NOW
  // pill anywhere. Covers both (a) workflows that close after recording
  // an outcome and (b) workflows that terminate at Decision itself
  // (e.g. identity-review, where the button-press IS the decision).
  if (d.status === "closed") return "done";
  if (d.outcome_text) return "outcome";
  if (d.selected_option || d.decided_at) return "action"; // decision done
  if (d.status !== "open" && d.status !== "deferred") return "decision"; // owner done
  return "owner";
}

function stageState(stage: Stage, currentStage: EffectiveStage): StageState {
  if (currentStage === "done") return "done";
  const order: Stage[] = ["signal", "owner", "decision", "action", "outcome"];
  const stageIdx = order.indexOf(stage);
  const curIdx = order.indexOf(currentStage);
  if (stageIdx < curIdx) return "done";
  if (stageIdx === curIdx) return "current";
  return "pending";
}

/** True for closed decisions with no downstream artefacts recorded —
 *  the workflow terminated at Decision (identity-review is the current
 *  example). Drives the Action/Outcome meta labels ("n/a" instead of
 *  "complete"/"captured"). */
function terminatedAtDecision(d: MatterDecision): boolean {
  return d.status === "closed" && !d.outcome_text;
}

/* ─── Header sub-components ───────────────────────────────────────── */

function EvidenceChip({
  count,
  hasFlag,
  onOpen,
}: {
  count: number;
  hasFlag: boolean;
  onOpen?: () => void;
}) {
  const badgeBg = hasFlag ? "bg-[#9c1c1c]" : "bg-[#7c3aed]";
  const chipBg = hasFlag
    ? "bg-[#fee2e2] border-[#9c1c1c]/40 hover:bg-[#fecaca]"
    : "bg-bg-warm border-rule hover:bg-paper-warm";
  const label =
    count === 0
      ? "Open evidence drawer (no items)"
      : `Open evidence drawer · ${count} item${count === 1 ? "" : "s"}${hasFlag ? " (flagged)" : ""}`;
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!onOpen}
      aria-label={label}
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full",
        "border-[0.5px] text-[11.5px] text-ink transition-colors",
        chipBg,
        !onOpen && "cursor-default opacity-70",
      )}
    >
      <span aria-hidden className="text-ink-faint">📎</span>
      <span>Evidence</span>
      {count > 0 && (
        <span
          className={cn(
            "inline-flex items-center justify-center min-w-[16px] h-[16px] px-1",
            "rounded-full text-paper text-[9px] font-mono font-medium",
            badgeBg,
          )}
        >
          {count}
        </span>
      )}
    </button>
  );
}

function StatusPill({ status }: { status: string }) {
  const palette: Record<string, string> = {
    open: "bg-navy-soft text-navy-deep",
    assigned: "bg-navy-soft text-navy-deep",
    in_progress: "bg-accent-warning/15 text-accent-warning",
    decided: "bg-cleared/15 text-cleared",
    closed: "bg-cleared/15 text-cleared",
    deferred: "bg-flag-soft text-flag",
    escalated: "bg-flag-soft text-flag",
  };
  return (
    <span
      className={cn(
        "px-2 py-0.5 rounded-sm text-[10px] uppercase tracking-[0.08em] font-medium",
        palette[status] ?? "bg-bg-warm text-ink-soft",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  );
}

/* ─── Progress strip ──────────────────────────────────────────────── */

function StageCell({
  idx,
  name,
  state,
  meta,
}: {
  idx: number;
  name: string;
  state: StageState;
  meta?: string;
}) {
  const dot =
    state === "done"
      ? "bg-cleared"
      : state === "current"
        ? "bg-navy"
        : state === "not-applicable"
          ? "border-[1px] border-ink-faint bg-transparent"
          : "bg-ink-faint";
  const nameColor =
    state === "current"
      ? "text-navy-deep"
      : state === "pending" || state === "not-applicable"
        ? "text-ink-soft"
        : "text-ink";
  // Current cell pops forward: bright paper against the navy-tint
  // card body, a thicker navy top rule, and a small vertical tick
  // dot that sits above the strip like a bookmark.
  const bg =
    state === "current"
      ? "bg-paper border-t-[3px] border-navy pt-[9px]"
      : "bg-bg-warm pt-3";
  return (
    <div
      className={cn(
        "relative px-4 pb-3 border-r-[0.5px] border-rule-soft last:border-r-0",
        bg,
        (state === "pending" || state === "not-applicable") && "opacity-70",
      )}
    >
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.08em] text-ink-faint font-medium mb-1">
        <span
          aria-hidden
          className={cn(
            "rounded-full",
            state === "current" ? "w-2 h-2" : "w-1.5 h-1.5",
            dot,
          )}
        />
        <span>Stage {idx}</span>
        {state === "current" && (
          <span
            className="ml-auto rounded-sm bg-navy-soft px-1 text-[9px] font-mono uppercase tracking-[0.08em] text-navy-deep"
            aria-label="current stage"
          >
            now
          </span>
        )}
      </div>
      <div className={cn("font-display font-medium text-[13.5px]", nameColor)}>
        {name}
      </div>
      {meta && (
        <div className="text-[11px] text-ink-faint mt-0.5 truncate">
          {meta}
        </div>
      )}
    </div>
  );
}

/* ─── Stage section wrapper ───────────────────────────────────────── */

function StageSection({
  num,
  name,
  state,
  children,
  last = false,
}: {
  num: number;
  name: string;
  state: StageState;
  children: ReactNode;
  last?: boolean;
}) {
  const marker =
    state === "done"
      ? { glyph: "✓", color: "text-cleared" }
      : state === "current"
        ? { glyph: "▲", color: "text-navy" }
        : state === "not-applicable"
          ? { glyph: "—", color: "text-ink-faint" }
          : { glyph: "○", color: "text-ink-faint" };
  return (
    <div
      className={cn(
        "py-2.5",
        !last && "border-b-[0.5px] border-rule-faint",
      )}
    >
      <div className="flex items-baseline gap-2.5 text-[10px] uppercase tracking-[0.08em] font-medium mb-1.5">
        <span className={cn(marker.color)}>
          {marker.glyph} {num} · {name}
          {state === "current" && (
            <span className="ml-1.5 text-ink-soft normal-case tracking-normal">· current</span>
          )}
        </span>
      </div>
      <div>{children}</div>
    </div>
  );
}

/* ─── Row content per stage ───────────────────────────────────────── */

function SignalRow({
  summary,
  onOpenSignals,
}: {
  summary?: string | null;
  onOpenSignals?: () => void;
}) {
  return (
    <div className="flex items-baseline gap-3 text-[12.5px]">
      <span className="text-ink-soft flex-1">
        {summary ?? "Signal fired to open this decision."}
      </span>
      {onOpenSignals && (
        <button
          type="button"
          onClick={onOpenSignals}
          className="text-navy hover:underline text-[12px]"
        >
          See § 3 →
        </button>
      )}
    </div>
  );
}

function OwnerRow({
  name,
  role,
  claimedAt,
  claimed,
  fullDecision,
  currentUserId,
}: {
  name?: string | null;
  role?: string | null;
  claimedAt?: string | null;
  claimed: boolean;
  /** Full Decision so the ClaimButton has what it needs — status,
   *  owner_id — to render its own label ("Claim" / "Pick up" /
   *  "Reclaim from owner"). Undefined during the initial load; the
   *  claim affordance stays hidden until the fetch completes. */
  fullDecision?: Decision;
  currentUserId?: string | null;
}) {
  if (!claimed) {
    return (
      <div className="space-y-2">
        <div className="text-[12.5px] text-ink-muted italic">
          Unclaimed — waiting for an owner.
        </div>
        {fullDecision && (
          <ClaimButton
            decision={fullDecision}
            currentUserId={currentUserId}
          />
        )}
      </div>
    );
  }
  return (
    <div className="text-[12.5px] text-ink-soft">
      {name ?? "—"}
      {role && <span className="text-ink-muted"> ({role})</span>}
      {claimedAt && (
        <span className="text-ink-muted">
          {" · claimed "}
          {formatShortDate(claimedAt)}
        </span>
      )}
    </div>
  );
}

function DecisionRow({
  decision,
  fullDecision,
  state,
  workflowId,
}: {
  decision: MatterDecision;
  fullDecision: Decision | undefined;
  state: StageState;
  workflowId?: string;
}) {
  if (state === "done") {
    return (
      <div className="text-[12.5px] text-ink-soft">
        <span className="text-navy-deep font-medium">
          {decision.selected_option ?? "Decided"}
        </span>
        {decision.decided_at && (
          <span className="text-ink-faint">
            {" · "}
            {formatShortDate(decision.decided_at)}
          </span>
        )}
      </div>
    );
  }
  if (state === "current") {
    return (
      <DecisionCurrentPane
        fullDecision={fullDecision}
        workflowId={workflowId}
      />
    );
  }
  return (
    <div className="text-[12.5px] text-ink-muted italic">
      Awaiting owner claim before the decision opens.
    </div>
  );
}

/**
 * The real work surface for stage 3 when the decision is the current
 * stage. Fetches the full Decision and the workflow config, then
 * decides whether to show:
 *
 *   - a Claim / Pick-up button (open / assigned, or in_progress owned
 *     by someone else)
 *   - the FinalizeForm (in_progress, viewer is the owner)
 *
 * The card only ever fetches when the Decision stage is current — done
 * and pending stages read from the MatterDecision snapshot the parent
 * already loaded, so we don't pay the extra request for collapsed
 * rows.
 */
function DecisionCurrentPane({
  fullDecision,
  workflowId,
}: {
  fullDecision: Decision | undefined;
  workflowId?: string;
}) {
  const user = useAuthStore((s) => s.user);
  const workflowConfigQuery = useWorkflowConfig(workflowId);

  if (!fullDecision) {
    return (
      <div className="rounded-md border-[0.5px] border-rule-soft bg-bg-warm px-3.5 py-3 text-[12.5px] text-ink-muted italic">
        Loading decision…
      </div>
    );
  }

  const decision = fullDecision;
  const isOwner = decision.owner_id === user?.id;
  const decisionType = workflowConfigQuery.data?.decision_types.find(
    (t) => t.id === decision.decision_type,
  );
  const availableActions = decisionType?.available_actions ?? [];

  // FinalizeForm renders when the viewer owns the decision AND it's in
  // the recording phase. Otherwise show a claim gate (or a "waiting for
  // owner" message when someone else owns it).
  const canRecord = isOwner && decision.status === "in_progress";

  return (
    <div className="rounded-md border-[0.5px] border-rule bg-paper px-4 py-3.5">
      <DecisionQuestion title={decision.title} />
      {canRecord ? (
        <FinalizeForm decision={decision} availableActions={availableActions} />
      ) : (
        <div className="space-y-3">
          <ClaimGate decision={decision} currentUserId={user?.id} />
          {availableActions.length > 0 && (
            <OptionsPreview actions={availableActions} />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Navy-tinted prompt at the top of the Decision-current pane. The
 * mockup renders the human-readable "should we do X?" question above
 * the options; we use the decision title verbatim since it's already
 * phrased as the matter under decision (e.g. "CDBG FY26 — federal
 * award" → shown as prompt).
 */
function DecisionQuestion({ title }: { title: string }) {
  const withQuestionMark = title.trim().endsWith("?") ? title : `${title}?`;
  return (
    <div className="mb-3 rounded-md bg-navy-soft px-3.5 py-2.5 font-display text-[15px] font-medium text-navy-deep">
      {withQuestionMark}
    </div>
  );
}

/**
 * Gate shown above the options preview when the viewer can't yet
 * record. Wraps ClaimButton with a small explanatory heading that
 * tells the reader why the record UI isn't live yet.
 */
function ClaimGate({
  decision,
  currentUserId,
}: {
  decision: Decision;
  currentUserId: string | null | undefined;
}) {
  const ownedByOther =
    decision.owner_id && decision.owner_id !== currentUserId;
  const heading = ownedByOther
    ? "Currently owned by another user."
    : decision.status === "assigned"
      ? "Assigned to you — pick it up to open the record."
      : "Claim ownership to open the record.";
  return (
    <div className="space-y-2">
      <div className="text-[12.5px] text-ink-soft">{heading}</div>
      <ClaimButton decision={decision} currentUserId={currentUserId} />
    </div>
  );
}

/**
 * Read-only preview of the available actions shown before the owner
 * has claimed the decision. Not interactive; just gives context on
 * what the recorded outcome will look like.
 */
function OptionsPreview({
  actions,
}: {
  actions: WorkflowAction[];
}) {
  return (
    <div>
      <div className="mb-2 text-[10px] uppercase tracking-[0.08em] text-ink-faint font-medium">
        Options available on the record
      </div>
      <ul className="space-y-1.5">
        {actions.map((a) => (
          <li
            key={a.id}
            className="rounded-sm border-[0.5px] border-rule-soft bg-bg-warm px-3 py-2 text-[12px]"
          >
            <div className="text-ink font-medium">{a.name}</div>
            {a.description && (
              <div className="text-ink-soft mt-0.5">{a.description}</div>
            )}
            <div className="text-[10px] text-ink-faint mt-0.5 font-mono">
              authority · {a.authority_required}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ActionRow({
  state,
  fullDecision,
  terminalAtDecision,
}: {
  state: StageState;
  fullDecision: Decision | undefined;
  terminalAtDecision?: boolean;
}) {
  if (state === "pending") {
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        Unlocks once a decision is recorded above.
      </div>
    );
  }
  if (terminalAtDecision) {
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        No downstream action — this workflow terminates at Decision.
      </div>
    );
  }
  if (!fullDecision) {
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        Loading action…
      </div>
    );
  }
  return (
    <div className="rounded-md border-[0.5px] border-rule bg-paper px-4 py-3.5">
      <ActionStageBody decision={fullDecision} />
    </div>
  );
}

function OutcomeRow({
  state,
  fullDecision,
  outcomeText,
  terminalAtDecision,
}: {
  state: StageState;
  fullDecision: Decision | undefined;
  outcomeText: string | null;
  terminalAtDecision?: boolean;
}) {
  if (state === "pending") {
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        Unlocks once action completes.
      </div>
    );
  }
  if (terminalAtDecision) {
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        No downstream outcome — recorded at Decision.
      </div>
    );
  }
  if (!fullDecision) {
    // Compact done-with-text fallback so a fully-decided card still
    // shows the outcome narrative while the full Decision loads.
    if (state === "done" && outcomeText) {
      return (
        <div className="rounded-md border-[0.5px] border-cleared bg-cleared/10 px-3.5 py-2.5 text-[12.5px] text-ink">
          {outcomeText}
        </div>
      );
    }
    return (
      <div className="text-[12.5px] text-ink-muted italic">
        Loading outcome…
      </div>
    );
  }
  return (
    <div className="rounded-md border-[0.5px] border-rule bg-paper px-4 py-3.5">
      <OutcomeStageBody decision={fullDecision} />
    </div>
  );
}

/* ─── Helpers ─────────────────────────────────────────────────────── */

function formatShortDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

