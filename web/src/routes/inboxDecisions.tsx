// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import {
  createRoute,
  useLocation,
  useNavigate,
} from "@tanstack/react-router";
import { useQueries } from "@tanstack/react-query";
import { formatDistanceToNow, parseISO } from "date-fns";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import { listDecisions, type DecisionStage } from "@/api/decisions";
import { Button } from "@/components/ds/Button";
import { CreateDecisionDrawer } from "@/components/decision/CreateDecisionDrawer";
import { BulkActionBar } from "@/components/inbox/BulkActionBar";
import { useInboxSelectionStore } from "@/stores/inboxSelection";
import { DecisionRow } from "@/components/ds/DecisionRow";
import { type DensityValue } from "@/components/ds/DensityToggle";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { EmptyState } from "@/components/ds/EmptyState";
import { HelpTerm } from "@/components/ds/HelpTerm";
import { LeftTree } from "@/components/ds/LeftTree";
import { type ScopeValue } from "@/components/ds/ScopeToggle";
import { SkeletonRows } from "@/components/ds/Skeleton";
import type { StatusVariant } from "@/components/ds/StatusBadge";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { HelpLink } from "@/components/help/HelpLink";
import { useArchetypes } from "@/hooks/useArchetypes";
import { useDecisions } from "@/hooks/useDecisions";
import { useWorkflows } from "@/hooks/useWorkflows";

// `awaiting_recipient` is present in the local StageKey but NOT yet in the
// backend DecisionStage union — the RFR (RequestForResponse) model that
// makes the count meaningful is still to be built. Labels + counts init
// are wired so the band lands cleanly once the backend endpoint returns
// this stage. Push into stageKeys is gated below.
// See: docs/architecture/backlog/awaiting-recipient-stage-band.md
type StageKey = "decisions" | "actions" | "awaiting_committee" | "awaiting_recipient" | "outcomes" | "closed";

import { rootRoute } from "./__root";

/**
 * Decision-based Inbox — the pre-P1 view. Kept reachable at
 * /inbox/decisions as the audit path per docs/architecture/
 * MVP-BUILD-QUEUE.md P1. Default landing is the Matters-first
 * Inbox at /inbox.
 */
export const inboxDecisionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inbox/decisions",
  component: InboxPage,
});

function InboxPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const scope = (params.get("scope") as ScopeValue) || "mine";
  const density = (params.get("density") as DensityValue) || "active";
  const stageParam = params.get("stage") as StageKey | null;
  const workflowFilter = params.get("workflow") || undefined;
  const archetypeFilter = params.get("archetype") || undefined;

  // Phase 8.5 — bulk-ops selection. Lives outside the component so the
  // BulkActionBar shares the same state without prop-drilling. Selection
  // clears whenever any filter changes — staleness across filter swaps is
  // the worst class of bulk-ops bug.
  const selected = useInboxSelectionStore((s) => s.selected);
  const toggleSelected = useInboxSelectionStore((s) => s.toggle);
  const clearSelection = useInboxSelectionStore((s) => s.clear);
  const filterKey = `${scope}|${density}|${stageParam ?? ""}|${workflowFilter ?? ""}|${archetypeFilter ?? ""}`;
  useEffect(() => {
    clearSelection();
    // We deliberately depend on the filter key, not on clearSelection — the
    // store function reference is stable but lint can't prove it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey]);

  const updateSearch = (updates: Record<string, string | undefined>) => {
    void navigate({
      to: "/inbox",
      search: (prev) => {
        const next: Record<string, string> = { ...(prev as object) } as Record<string, string>;
        for (const [k, v] of Object.entries(updates)) {
          if (v === undefined || v === "") {
            delete next[k];
          } else {
            next[k] = v;
          }
        }
        return next;
      },
    });
  };

  // awaiting_recipient is a UI-only StageKey until the RFR backend lands
  // (see backlog/awaiting-recipient-stage-band.md). Never send it to the
  // API — treat it as "no stage filter" if it ever appears via URL.
  const stageForApi: DecisionStage | undefined =
    stageParam && stageParam !== "awaiting_recipient"
      ? (stageParam as DecisionStage)
      : undefined;

  // Main query — the rendered list reflects the active filters.
  const decisionsQuery = useDecisions({
    scope,
    density,
    stage: stageForApi,
    workflow_id: workflowFilter,
    archetype: archetypeFilter,
  });

  // Stage counts: one count query per bucket. Run them in parallel;
  // their refetchInterval matches the main query so the strip stays in
  // sync. The Closed tile is conditional on density='all' so the strip
  // grows from three tiles to four when the user widens scope.
  // Without the Closed tile the header count ("52 decisions") and the
  // tile sum (Decisions+Actions+Outcomes) didn't reconcile in All view.
  //
  // P51 Phase 2: the "Awaiting board" tile sits between Actions and
  // Outcomes, surfacing apex decisions in the oversight band.
  const stageKeys: StageKey[] = (() => {
    const active: StageKey[] = ["decisions", "actions"];
    active.push("awaiting_committee");
    // awaiting_recipient goes here once the RFR backend endpoint returns
    // this stage. See docs/architecture/backlog/awaiting-recipient-stage-band.md
    active.push("outcomes");
    if (density === "all") active.push("closed");
    return active;
  })();
  const stageQueries = useQueries({
    queries: stageKeys.map((stageKey) => ({
      queryKey: [
        "decisions",
        "count",
        { scope, density, stage: stageKey, workflow_id: workflowFilter, archetype: archetypeFilter },
      ] as const,
      queryFn: () =>
        listDecisions({
          scope,
          density,
          stage: stageKey as DecisionStage,
          workflow_id: workflowFilter,
          archetype: archetypeFilter,
          limit: 1,
        }),
      staleTime: 5_000,
      refetchInterval: 10_000,
    })),
  });
  const stageCounts: Record<StageKey, number> = {
    decisions: 0,
    actions: 0,
    awaiting_committee: 0,
    awaiting_recipient: 0,
    outcomes: 0,
    closed: 0,
  };
  stageKeys.forEach((key, idx) => {
    stageCounts[key] = stageQueries[idx]?.data?.total ?? 0;
  });

  const { data: workflowsData } = useWorkflows();
  const workflowsById = useMemo(() => {
    const map: Record<string, { name: string; color: string }> = {};
    for (const w of workflowsData?.workflows ?? []) {
      map[w.id] = { name: w.name, color: w.color ?? "#94a3b8" };
    }
    return map;
  }, [workflowsData?.workflows]);

  const { data: archetypesData } = useArchetypes();
  const archetypeName = useMemo(() => {
    if (!archetypeFilter) return undefined;
    const found = (archetypesData?.archetypes ?? []).find((a) => a.id === archetypeFilter);
    return found?.name ?? archetypeFilter;
  }, [archetypeFilter, archetypesData?.archetypes]);

  // Round-2 inbox split: server-sorted items partition into active
  // (assigned / in_progress) above and decided rows below in their own
  // collapsed "Recently decided" section. Server already ordered by
  // severity → due → opened, so partitioning preserves the order
  // within each bucket.
  //
  // P51 Phase 2: apex decisions in `decided` AND awaiting_committee_
  // ratification get their own bucket — they're not "recently decided"
  // in the operational sense, the board is the next gate.
  //
  // When the user has explicitly clicked a stage tile (stageParam set),
  // the partition is suppressed — they asked for that stage, the rows
  // belong in the main list, not hidden in a collapsed section below an
  // empty-state. The collapsed below-list sections only make sense in
  // the default mixed view where they pull decided rows out of the way.
  const { activeItems, awaitingBoardItems, decidedItems } = useMemo(() => {
    const raw = decisionsQuery.data?.items ?? [];
    if (stageParam) {
      return {
        activeItems: raw,
        awaitingBoardItems: [],
        decidedItems: [],
      };
    }
    const active: typeof raw = [];
    const awaitingBoard: typeof raw = [];
    const decided: typeof raw = [];
    for (const d of raw) {
      if (d.status !== "decided") {
        active.push(d);
      } else if (d.awaiting_committee_endorsement) {
        awaitingBoard.push(d);
      } else {
        decided.push(d);
      }
    }
    return {
      activeItems: active,
      awaitingBoardItems: awaitingBoard,
      decidedItems: decided,
    };
  }, [decisionsQuery.data?.items, stageParam]);
  const items = activeItems;
  const total = decisionsQuery.data?.total ?? 0;

  const scopeLabel =
    scope === "mine" ? "your queue" : scope === "team" ? "team queue" : "all entitled";
  const countPhrase = `${total} ${total === 1 ? "decision" : "decisions"}`;
  const pageTitle = archetypeName ?? "Inbox";
  const subtitle = archetypeName
    ? `${countPhrase} · ${scopeLabel}`
    : workflowFilter
      ? `${workflowsById[workflowFilter]?.name ?? workflowFilter} · ${countPhrase}`
      : `${countPhrase} · ${scopeLabel}`;

  const [createOpen, setCreateOpen] = useState(false);

  /**
   * Land on the matter that owns this decision, with the decision
   * expanded inside the case-file. Decisions without a matter
   * (grant-debarment adverse actions etc.) fall through to the
   * standalone decision-detail route so we don't send the reader to a
   * "Couldn't load this matter" dead end.
   */
  const navigateToDecision = (d: {
    id: string;
    workflow_id: string;
    matter_id: string | null;
  }) => {
    if (d.matter_id) {
      void navigate({
        to: "/matters",
        search: { id: d.matter_id, mode: "case-file", decision: d.id },
      });
      return;
    }
    void navigate({
      to: "/workflows/$workflowId/decisions/$decisionId",
      params: { workflowId: d.workflow_id, decisionId: d.id },
    });
  };

  return (
    <AppShellV2>
      <SplitView
        left={
          <InboxTree
            scope={scope}
            stageParam={stageParam}
            workflowFilter={workflowFilter}
            stageKeys={stageKeys}
            stageCounts={stageCounts}
            workflowsById={workflowsById}
            onScopeChange={(s) => updateSearch({ scope: s })}
            onStageChange={(s) =>
              updateSearch({ stage: s ?? undefined })
            }
            onWorkflowChange={(w) =>
              updateSearch({ workflow: w ?? undefined })
            }
          />
        }
      >
        <DetailContainer
          title={pageTitle}
          subtitle={subtitle}
          actions={
            <Button compact onClick={() => setCreateOpen(true)}>
              + New decision
            </Button>
          }
        >
          <div className="px-6 py-5">
            <CreateDecisionDrawer
              open={createOpen}
              onClose={() => setCreateOpen(false)}
            />

            <BulkActionBar
              selectedIds={Array.from(selected)}
              onClear={clearSelection}
            />

            <div className="mt-3 rounded-md border-[0.5px] border-rule-soft bg-paper">
              {decisionsQuery.isLoading && <SkeletonRows />}
              {decisionsQuery.isError && (
                <div className="p-6">
                  <EmptyState
                    headline="We couldn't load decisions."
                    body={
                      <>
                        The Inbox query failed. Refresh to try again, or
                        contact support if it keeps happening.
                      </>
                    }
                    actions={
                      <Button arrow onClick={() => void decisionsQuery.refetch()}>
                        Try again
                      </Button>
                    }
                  />
                </div>
              )}
              {decisionsQuery.isSuccess && items.length === 0 && (
                <EmptyInbox
                  scope={scope}
                  workflowName={
                    workflowFilter
                      ? workflowsById[workflowFilter]?.name
                      : undefined
                  }
                  onWidenScope={() => updateSearch({ scope: "team" })}
                />
              )}
              {decisionsQuery.isSuccess &&
                items.map((d, idx) => {
                  const wf = workflowsById[d.workflow_id];
                  const bodyText = [wf?.name, d.signal_summary]
                    .filter(Boolean)
                    .join(" · ");
                  return (
                    <DecisionRow
                      key={d.id}
                      status={statusToVariant(d.status, d.priority)}
                      statusLabel={statusLabel(d.status, d.priority)}
                      title={d.title}
                      body={bodyText || null}
                      decisionId={d.decision_number}
                      severity={d.severity}
                      rightMetadata={<RowMetadata decision={d} />}
                      isLast={idx === items.length - 1}
                      selectable
                      selected={selected.has(d.id)}
                      onToggleSelected={() => toggleSelected(d.id)}
                      onClick={() => navigateToDecision(d)}
                    />
                  );
                })}
            </div>

            {decisionsQuery.isSuccess && awaitingBoardItems.length > 0 && (
              <RecentlyDecidedSection
                title="Awaiting committee ratification"
                items={awaitingBoardItems}
                workflowsById={workflowsById}
                onSelect={(d) => navigateToDecision(d)}
              />
            )}
            {decisionsQuery.isSuccess && decidedItems.length > 0 && (
              <RecentlyDecidedSection
                items={decidedItems}
                workflowsById={workflowsById}
                onSelect={(d) => navigateToDecision(d)}
              />
            )}
          </div>
        </DetailContainer>
      </SplitView>
    </AppShellV2>
  );
}

/* ─── Inbox tree (scope + stage + workflow + saved views) ────────── */

const SCOPE_OPTIONS: { value: ScopeValue; label: string }[] = [
  { value: "mine", label: "Mine" },
  { value: "team", label: "Team" },
  { value: "all_entitled", label: "All agency" },
];

// Scope-relative labels: in Mine, "my" names who owes the next step.
// In Team / All agency the same records exist; the label names what's next
// without personalising it. Committee is the actor in both cases, so
// "Awaiting committee" carries across scopes unchanged.
const TREE_STAGE_LABEL: Record<ScopeValue, Record<StageKey, string>> = {
  mine: {
    decisions: "Awaiting my decision",
    actions: "Awaiting my action",
    awaiting_committee: "Awaiting committee",
    awaiting_recipient: "Awaiting recipient",
    outcomes: "Awaiting my outcome",
    closed: "Recently decided",
  },
  team: {
    decisions: "Awaiting decision",
    actions: "Awaiting action",
    awaiting_committee: "Awaiting committee",
    awaiting_recipient: "Awaiting recipients",
    outcomes: "Awaiting outcome",
    closed: "Recently decided",
  },
  all_entitled: {
    decisions: "Awaiting decision",
    actions: "Awaiting action",
    awaiting_committee: "Awaiting committee",
    awaiting_recipient: "Awaiting recipients",
    outcomes: "Awaiting outcome",
    closed: "Recently decided",
  },
};

const TREE_STAGE_DOT: Partial<Record<StageKey, "flag" | "amber" | "green" | "muted">> = {
  decisions: "flag",
  actions: "amber",
  awaiting_recipient: "amber",
  outcomes: "muted",
  closed: "green",
};

function InboxTree({
  scope,
  stageParam,
  workflowFilter,
  stageKeys,
  stageCounts,
  workflowsById,
  onScopeChange,
  onStageChange,
  onWorkflowChange,
}: {
  scope: ScopeValue;
  stageParam: StageKey | null;
  workflowFilter: string | undefined;
  stageKeys: StageKey[];
  stageCounts: Record<StageKey, number>;
  workflowsById: Record<string, { name: string; color: string }>;
  onScopeChange: (s: ScopeValue) => void;
  onStageChange: (s: StageKey | null) => void;
  onWorkflowChange: (w: string | null) => void;
}) {
  const workflows = Object.entries(workflowsById);

  return (
    <LeftTree>
      <LeftTree.Search placeholder="Filter queue…" />
      <LeftTree.Body>
        <LeftTree.Section
          title={<HelpTerm term="scope">Scope</HelpTerm>}
        >
          {SCOPE_OPTIONS.map((opt) => (
            <LeftTree.Node
              key={opt.value}
              level={1}
              selected={scope === opt.value}
              onClick={() => onScopeChange(opt.value)}
            >
              {opt.label}
            </LeftTree.Node>
          ))}
        </LeftTree.Section>

        <LeftTree.Section title="Stage">
          {stageKeys.map((key) => (
            <LeftTree.Node
              key={key}
              level={1}
              selected={stageParam === key}
              count={stageCounts[key]}
              dot={TREE_STAGE_DOT[key]}
              onClick={() =>
                onStageChange(stageParam === key ? null : key)
              }
            >
              {TREE_STAGE_LABEL[scope][key]}
            </LeftTree.Node>
          ))}
        </LeftTree.Section>

        {workflows.length > 0 && (
          <LeftTree.Section
            title={<HelpTerm term="workflow">Workflow</HelpTerm>}
          >
            {workflows.map(([id, wf]) => (
              <LeftTree.Node
                key={id}
                level={1}
                selected={workflowFilter === id}
                onClick={() =>
                  onWorkflowChange(workflowFilter === id ? null : id)
                }
              >
                {wf.name}
              </LeftTree.Node>
            ))}
          </LeftTree.Section>
        )}
      </LeftTree.Body>
    </LeftTree>
  );
}

function EmptyInbox({
  scope,
  workflowName,
  onWidenScope,
}: {
  scope: ScopeValue;
  workflowName?: string;
  onWidenScope?: () => void;
}) {
  const eyebrow = workflowName ? workflowName : undefined;

  if (scope === "mine") {
    return (
      <div className="p-6">
        <EmptyState
          eyebrow={eyebrow}
          headline="Inbox clear."
          body={
            <>
              Nothing is currently routed to you. Decisions appear here as
              owners assign them or as new signals match your authority. Widen
              the scope to see what your team is working on.
            </>
          }
          actions={
            <>
              {onWidenScope && (
                <Button variant="ghost" arrow onClick={onWidenScope}>
                  Show team queue
                </Button>
              )}
              <HelpLink topic="inbox/empty-states" label="Why is this empty?" />
            </>
          }
        />
      </div>
    );
  }

  return (
    <div className="p-6">
      <EmptyState
        eyebrow={eyebrow}
        headline="No decisions captured here yet."
        body={
          <>
            Decisions appear when an entitled workflow surfaces a signal — a
            filing deadline, an alert, a governance event, or a manual entry.
            Connect a source on a workflow, or create a decision record yourself.
          </>
        }
        actions={
          <HelpLink topic="inbox/empty-states" label="What does this mean?" />
        }
      />
    </div>
  );
}

function RowMetadata({
  decision,
}: {
  decision: { sla_deadline: string | null; sla_hours: number | null; created_at: string };
}): ReactNode {
  const deadlineLabel = decision.sla_deadline
    ? `Due ${formatDistanceToNow(parseISO(decision.sla_deadline), {
        addSuffix: true,
      })}`
    : decision.sla_hours
      ? `${decision.sla_hours}h SLA`
      : null;
  // Round 2: suppress the "Opened X ago" line when the decision is
  // less than 24h old. Fresh rows don't need a timestamp; older rows
  // benefit from the recency cue.
  const openedAt = parseISO(decision.created_at);
  const ageHours = (Date.now() - openedAt.getTime()) / 36e5;
  const showOpened = ageHours >= 24;
  return (
    <>
      {deadlineLabel && <div>{deadlineLabel}</div>}
      {showOpened && (
        <div className="mt-1 text-ink-faint">
          Opened {formatDistanceToNow(openedAt, { addSuffix: true })}
        </div>
      )}
    </>
  );
}

/**
 * Recently decided rows live below the active queue in their own
 * collapsed section. Default state is collapsed — the count badge
 * surfaces volume without flooding the active list with rows the
 * operator already moved past. Expand inline; no modal, no nav.
 *
 * Reused for the apex "Awaiting board ratification" group with a
 * different ``title`` so the apex Inbox UX surfaces both buckets
 * (awaiting board + recently decided) below the active queue.
 */
export function RecentlyDecidedSection({
  items,
  workflowsById,
  onSelect,
  title = "Recently decided",
}: {
  items: import("@/api/decisions").Decision[];
  workflowsById: Record<string, { name: string; color: string }>;
  onSelect: (d: import("@/api/decisions").Decision) => void;
  title?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="mt-6 border-t border-rule-soft pt-4">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center justify-between gap-2 text-left text-mono-label uppercase text-ink-soft hover:text-ink"
      >
        <span>
          {title}
          <span className="ml-2 rounded bg-rule-faint px-2 py-0.5 font-mono text-[11px] text-ink-faint">
            {items.length}
          </span>
        </span>
        <span aria-hidden className="text-[12px]">
          {expanded ? "▾" : "▸"}
        </span>
      </button>
      {expanded && (
        <div className="mt-3 rounded-md border-[0.5px] border-rule-soft bg-paper">
          {items.map((d, idx) => {
            const wf = workflowsById[d.workflow_id];
            const bodyText = [wf?.name, d.signal_summary]
              .filter(Boolean)
              .join(" · ");
            return (
              <DecisionRow
                key={d.id}
                status={statusToVariant(d.status, d.priority)}
                statusLabel={statusLabel(d.status, d.priority)}
                title={d.title}
                body={bodyText || null}
                decisionId={d.decision_number}
                severity={d.severity}
                rightMetadata={<RowMetadata decision={d} />}
                isLast={idx === items.length - 1}
                onClick={() => onSelect(d)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}

function statusToVariant(
  status: string,
  priority: string,
): StatusVariant {
  if (status === "closed") return "resolved";
  if (status === "deferred") return "deferred";
  if (priority === "critical" || priority === "urgent") return "critical";
  if (priority === "high") return "warning";
  return "info";
}

function statusLabel(status: string, priority: string): string {
  if (status === "closed") return "Closed";
  if (status === "deferred") return "Deferred";
  if (status === "in_progress") return "In progress";
  if (status === "decided") return "Decided";
  if (status === "escalated") return "Escalated";
  if (status === "open") {
    return priority === "critical" || priority === "urgent" ? "Due today" : "New";
  }
  return "Assigned";
}
