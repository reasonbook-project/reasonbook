// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";

import type { Decision, DecisionEvent } from "@/api/decisions";
import { AnatomyStageSection } from "@/components/ds/AnatomyStageSection";
import { CommitteeActionForm } from "@/components/decision/CommitteeActionForm";
import { useDecisionEvents } from "@/hooks/useDecisions";
import { useAuthStore } from "@/stores/auth";

const BOARD_ACTIONS = new Set([
  "noted_by_board",
  "ratified_by_board",
  "ratified_by_committee",
  "deferred_to_next_cycle",
]);

const ACTION_LABELS: Record<string, string> = {
  ratified_by_board: "Ratified by board",
  noted_by_board: "Noted by board",
  ratified_by_committee: "Ratified by committee",
  deferred_to_next_cycle: "Deferred to next cycle",
};

/**
 * Committee stage — oversight-only section between Decision (3) and Action
 * (4). The audit committee chair / committee-of-record records ratification
 * here before an oversight decision proceeds to Action.
 *
 * Reads committee action events from `decision_events`
 * (action ∈ noted_by_board / ratified_by_board / ratified_by_committee /
 * deferred_to_next_cycle — the `_by_board` action labels are historical;
 * new ratifications write `_by_committee`).
 *
 * Renders three states:
 *   - empty + viewer is a committee persona → matrix affordance to record
 *   - empty + viewer is not a committee persona → "Awaiting committee ratification"
 *   - populated → list of committee events, most recent first
 *
 * Active when the decision is in_progress or decided; suppressed once closed.
 */
export function CommitteeStage({
  decision,
  dimmed,
}: {
  decision: Decision;
  dimmed?: boolean;
}) {
  const user = useAuthStore((s) => s.user);
  const eventsQuery = useDecisionEvents(decision.id, "audit");

  const boardEvents: DecisionEvent[] = (eventsQuery.data?.items ?? [])
    .filter((e) => BOARD_ACTIONS.has(e.action))
    // newest first
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

  const latest = boardEvents[0] ?? null;
  const timestamp = latest
    ? format(parseISO(latest.created_at), "MMM d, h:mm a")
    : undefined;

  const canRecord = Boolean(user?.oversight_capabilities?.can_record_committee_action);
  const isAccepting =
    decision.status === "in_progress" || decision.status === "decided";

  return (
    <AnatomyStageSection
      stageNumber="C"
      stageName="COMMITTEE"
      timestamp={timestamp}
      dimmed={dimmed}
    >
      {boardEvents.length > 0 ? (
        <ul className="space-y-3">
          {boardEvents.map((event) => (
            <BoardEventRow key={event.id} event={event} />
          ))}
        </ul>
      ) : (
        <p className="text-body-sm text-ink-muted">
          Awaiting committee ratification.
        </p>
      )}

      {canRecord && isAccepting && (
        <div className="mt-4 border-t-hairline border-rule-soft pt-4">
          <CommitteeActionForm decisionId={decision.id} />
        </div>
      )}
    </AnatomyStageSection>
  );
}

function BoardEventRow({ event }: { event: DecisionEvent }) {
  const when = format(parseISO(event.created_at), "MMM d, yyyy · h:mm a");
  const label = ACTION_LABELS[event.action] ?? event.action;
  const committee =
    (event.metadata as { committee?: string } | null)?.committee ?? null;

  return (
    <li className="space-y-1">
      <div className="flex items-baseline gap-2">
        <span className="text-body font-medium text-ink">{label}</span>
        {committee && (
          <span className="text-body-sm text-ink-soft">· {committee}</span>
        )}
      </div>
      <div className="text-[11px] text-ink-faint">
        {event.user_name ?? event.user_username ?? "Unknown user"} · {when}
      </div>
      {event.comment && (
        <p className="text-body-sm leading-[1.55] text-ink">{event.comment}</p>
      )}
    </li>
  );
}
