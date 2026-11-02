// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { format, formatDistanceToNow, parseISO } from "date-fns";
import { useState } from "react";

import type {
  AtRiskBreakdownEntry,
  DailyOpenPoint,
  DashboardApex,
  DashboardApexOpenDecision,
  DashboardRecentOutcome,
  DashboardTotals,
  DashboardWorkflowSummary,
  WeeklyOpenedPoint,
} from "@/api/dashboard";
import type { Alert } from "@/api/alerts";
import type { QueueCategory, QueueStatus } from "@/api/decisionQueue";
import { TopRail } from "@/components/dashboard";
import { DecisionQueueDrawer } from "@/components/dashboard/DecisionQueueDrawer";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { ramps } from "@/design/tokens";
import { useAlerts } from "@/hooks/useAlerts";
import { useMatterMeta } from "@/hooks/useMatters";
import { useDashboard } from "@/hooks/useDashboard";
import { useDrawer } from "@/hooks/useDrawer";
import { useRegistryCases } from "@/hooks/useRegistry";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";

// Search-param shape for the dashboard's queue-drawer URL sync.
// `queue` opens the drawer; `category` narrows it. Both are optional, both
// stripped from the URL when the drawer closes.
type DashboardSearch = {
  queue?: QueueStatus;
  category?: QueueCategory;
};

const QUEUE_STATUSES: readonly QueueStatus[] = ["at_risk", "open"];
const QUEUE_CATEGORIES: readonly QueueCategory[] = ["credit", "compliance", "ops"];

/**
 * Executive dashboard — cross-workflow institutional readout.
 *
 * Lives at /dashboard rather than nested under /apex because every
 * tenant needs an executive view (lower-tier as well as Enterprise).
 * Composition top-to-bottom:
 *
 *   1. Operational summary — three totals (open / decided / at-risk)
 *      plus a per-workflow grid so a CRO/CCO can see where attention is
 *      going.
 *   2. Apex section — for Enterprise, the open-strategic-decision count
 *      plus the current board cycle's deadline. For non-Enterprise, an
 *      informational card describing what Apex unlocks. No clickable
 *      CTAs in the upsell — the Enterprise sales motion is handled
 *      through account managers, not in-app upgrade buttons.
 *   3. Governance summary — small footer card showing the institution's
 *      governance score; we leave it understated until the category
 *      claim has earned more prominence in the market.
 */
export const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/dashboard",
  validateSearch: (search: Record<string, unknown>): DashboardSearch => {
    const queue =
      typeof search.queue === "string" &&
      QUEUE_STATUSES.includes(search.queue as QueueStatus)
        ? (search.queue as QueueStatus)
        : undefined;
    const category =
      typeof search.category === "string" &&
      QUEUE_CATEGORIES.includes(search.category as QueueCategory)
        ? (search.category as QueueCategory)
        : undefined;
    // category only meaningful when queue is set; drop it otherwise so the
    // URL doesn't carry stale state.
    return queue ? { queue, category } : {};
  },
  component: DashboardPage,
});

function DashboardPage() {
  const navigate = useNavigate();
  const query = useDashboard();
  const matterMetaQuery = useMatterMeta();
  const casesQuery = useRegistryCases();
  const openAlertsQuery = useAlerts({ status: ["new", "reopened"] });
  // P17: the at-risk + per-category interaction now opens the queue
  // drawer (with URL sync), superseding the round-3 local workflow-grid
  // filter. Workflow tiles still navigate to /inbox?workflow=X as their
  // own affordance — they no longer act as a queue filter.
  const drawer = useDrawer();

  if (query.isLoading) {
    return (
      <div className="px-7 py-7 text-body-sm text-ink-muted">
        Loading dashboard…
      </div>
    );
  }

  if (query.isError || !query.data) {
    return (
      <div className="px-7 py-7">
        <p className="text-body text-critical-text">
          Couldn't load the dashboard.
        </p>
      </div>
    );
  }

  const { tenant, operational, apex, recent_outcomes } = query.data;
  const { totals } = operational;

  const handleReviewAtRisk = () => {
    if (totals.at_risk > 0) drawer.open({ status: "at_risk" });
  };
  const handleFilterCategory = (category: QueueCategory) => {
    if (totals.at_risk > 0) drawer.open({ status: "at_risk", category });
  };

  // Top-3 open alerts surfaced on the dashboard's program-integrity
  // strip — severity-first, then most recent. Light filter so a director
  // never sees more than they can act on without the dedicated Signals
  // queue.
  const SEVERITY_ORDER: Record<string, number> = {
    critical: 0,
    high: 1,
    medium: 2,
    low: 3,
  };
  const topAlerts = (openAlertsQuery.data?.items ?? [])
    .slice()
    .sort((a, b) => {
      const sa = SEVERITY_ORDER[a.severity] ?? 9;
      const sb = SEVERITY_ORDER[b.severity] ?? 9;
      if (sa !== sb) return sa - sb;
      return b.detected_at.localeCompare(a.detected_at);
    })
    .slice(0, 3);

  return (
    <AppShellV2>
      <div className="flex-1 min-h-0 overflow-y-auto px-7 py-7">
      <ProgramIntegritySection
        matters={matterMetaQuery.data?.matters ?? null}
        exposure={matterMetaQuery.data?.exposure ?? null}
        openSignals={matterMetaQuery.data?.signals ?? null}
        casesOnRecord={casesQuery.data?.total ?? null}
        topAlerts={topAlerts}
        onOpenRegister={() => void navigate({ to: "/matters" })}
        onOpenAlerts={() => void navigate({ to: "/signals" })}
        onOpenAlertMatter={(matterId) =>
          void navigate({
            to: "/matters",
            search: { id: matterId, mode: "case-file" },
          })
        }
      />

      <DecisionsInFlightSection
        agencyName={tenant.name || "Executive dashboard"}
        agencySubtitle="Cross-workflow agency posture"
        totals={totals}
        openTrend={operational.open_trend}
        workflows={operational.by_workflow}
        onReviewAtRisk={handleReviewAtRisk}
        onFilterCategory={handleFilterCategory}
        onOpenWorkflow={(workflowId) =>
          void navigate({
            to: "/inbox",
            search: { scope: "all_entitled", workflow: workflowId },
          })
        }
      />

      <section className="mb-8">
        <h2 className="mb-3 text-tracked uppercase text-ink-soft">
          Agency oversight & committees
        </h2>
        <ApexSection
          apex={apex}
          onSelectApexDecision={(decisionId) =>
            void navigate({
              to: "/workflows/$workflowId/decisions/$decisionId",
              params: { workflowId: "10-oversight", decisionId },
            })
          }
          onOpenApexCycles={() => void navigate({ to: "/oversight/cycles" })}
        />
      </section>

      {recent_outcomes.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-tracked uppercase text-ink-soft">
            Recently closed · trailing 30 days
          </h2>
          <RecentOutcomes
            items={recent_outcomes}
            onSelect={(o) =>
              void navigate({
                to: "/workflows/$workflowId/decisions/$decisionId",
                params: {
                  workflowId: o.workflow_id,
                  decisionId: o.decision_id,
                },
              })
            }
          />
        </section>
      )}

      <DecisionQueueDrawer
        open={drawer.isOpen}
        filter={drawer.filter}
        onClose={drawer.close}
        onChangeFilter={drawer.setFilter}
      />
      </div>
    </AppShellV2>
  );
}

/**
 * Decisions-in-flight section: top totals row + per-workflow grid.
 *
 * Round 3 wires the at-risk total as an interactive filter that
 * narrows the grid to domains where at_risk > 0. The grid itself
 * sorts by at-risk count (DESC, then open DESC, then original API
 * order as tiebreak) so the loudest workflows surface first.
 */
/**
 * Sort the workflow grid by at-risk count, then open count, then the
 * original API order as tiebreak (stable). Pure function — exported
 * so the sort contract is testable in isolation.
 */
/**
 * Convert the backend's `at_risk_breakdown` array (one entry per
 * non-zero category) into TopRail's `{credit, compliance, ops}`
 * object shape with zero-defaults for missing keys.
 *
 * Defensive against:
 * - `null` / `undefined` (e.g. partial responses) → returns
 *   `{credit: 0, compliance: 0, ops: 0}`
 * - empty array → same zero-defaults
 * - unknown category labels (e.g. a future "vendor" bucket the UI
 *   doesn't yet display) → preserved on the object but ignored by
 *   the typed consumer
 *
 * Exported so the contract can be tested in isolation (verification
 * 5.8 — `at_risk_breakdown` null/missing handling). Pure function.
 */
export function buildAtRiskBreakdown(
  entries: AtRiskBreakdownEntry[] | null | undefined,
): { credit: number; compliance: number; ops: number } {
  return {
    credit: 0,
    compliance: 0,
    ops: 0,
    ...Object.fromEntries((entries ?? []).map((e) => [e.label, e.count])),
  };
}

export function sortWorkflowsByAtRisk(
  workflows: DashboardWorkflowSummary[],
): DashboardWorkflowSummary[] {
  return [...workflows]
    .map((w, idx) => ({ w, idx }))
    .sort((a, b) => {
      if (a.w.at_risk_count !== b.w.at_risk_count) {
        return b.w.at_risk_count - a.w.at_risk_count;
      }
      if (a.w.open_count !== b.w.open_count) {
        return b.w.open_count - a.w.open_count;
      }
      return a.idx - b.idx;
    })
    .map((entry) => entry.w);
}

/**
 * Program-integrity headline — the federal-program-fraud read of the
 * tenant's posture. Four headline cells (matters · exposure · open
 * signals · cases on record) above a Top-3 open-signals list. This is
 * the surface a CCO or congressional staffer looks at first; the
 * decisions-in-flight grid below is the operational layer.
 */
function ProgramIntegritySection({
  matters,
  exposure,
  openSignals,
  casesOnRecord,
  topAlerts,
  onOpenRegister,
  onOpenAlerts,
  onOpenAlertMatter,
}: {
  matters: number | null;
  exposure: string | null;
  openSignals: number | null;
  casesOnRecord: number | null;
  topAlerts: Alert[];
  onOpenRegister: () => void;
  onOpenAlerts: () => void;
  onOpenAlertMatter: (matterId: string) => void;
}) {
  return (
    <section className="mb-8">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 className="text-tracked uppercase text-ink-soft">
          Program integrity · federal awards
        </h2>
        <button
          type="button"
          onClick={onOpenRegister}
          className="text-[12px] text-brand hover:underline"
        >
          Open Register →
        </button>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-px overflow-hidden rounded-md border-[0.5px] border-rule-soft bg-rule-soft sm:grid-cols-4">
        <IntegrityCell
          label="Matters of record"
          value={matters !== null ? matters.toLocaleString() : "—"}
        />
        <IntegrityCell
          label="Exposure tracked"
          value={formatDashboardExposure(exposure)}
        />
        <IntegrityCell
          label={`Open signal${openSignals === 1 ? "" : "s"}`}
          value={openSignals !== null ? openSignals.toLocaleString() : "—"}
          tone={openSignals && openSignals > 0 ? "alert" : undefined}
        />
        <IntegrityCell
          label={`Review${casesOnRecord === 1 ? "" : "s"} on record`}
          value={casesOnRecord !== null ? casesOnRecord.toLocaleString() : "—"}
          hint="promoted from signals"
        />
      </div>

      <div className="rounded-md border-[0.5px] border-rule-soft bg-paper">
        <div className="flex items-baseline justify-between border-b-[0.5px] border-rule-soft px-4 py-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
            Top open signals
          </span>
          <button
            type="button"
            onClick={onOpenAlerts}
            className="text-[12px] text-brand hover:underline"
          >
            Signals queue →
          </button>
        </div>
        {topAlerts.length === 0 ? (
          <div className="px-4 py-5 text-body-sm text-ink-muted">
            No open signals — the queue is clear.
          </div>
        ) : (
          <ul>
            {topAlerts.map((a) => (
              <li
                key={a.id}
                className="border-t-[0.5px] border-rule-faint first:border-t-0"
              >
                <button
                  type="button"
                  onClick={() => a.matter_id && onOpenAlertMatter(a.matter_id)}
                  disabled={!a.matter_id}
                  className={cn(
                    "grid w-full grid-cols-[auto_auto_1fr_auto] items-baseline gap-3 px-4 py-2.5 text-left",
                    a.matter_id
                      ? "hover:bg-ink/[0.03]"
                      : "cursor-default",
                  )}
                >
                  <SeverityDot severity={a.severity} />
                  <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
                    {a.source}
                  </span>
                  <span className="truncate text-body-sm text-ink">
                    {a.title}
                  </span>
                  <span className="font-mono text-[11px] text-ink-faint">
                    {a.matter_id ? "open case file →" : "no matter"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function IntegrityCell({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone?: "alert";
  hint?: string;
}) {
  return (
    <div className="bg-paper px-4 py-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
        {label}
      </div>
      <div
        className={cn(
          "mt-0.5 font-display text-[24px] font-semibold tabular-nums tracking-[-0.02em]",
          tone === "alert" ? "text-critical-text" : "text-brand-ink",
        )}
      >
        {value}
      </div>
      {hint && (
        <div className="mt-0.5 text-[11px] italic text-ink-faint">{hint}</div>
      )}
    </div>
  );
}

function SeverityDot({ severity }: { severity: Alert["severity"] }) {
  const color =
    severity === "critical"
      ? "#dc2626"
      : severity === "high"
        ? "#b7791f"
        : severity === "medium"
          ? "#54607a"
          : "#9a9a9a";
  return (
    <span
      aria-label={`severity ${severity}`}
      className="inline-block h-2 w-2 rounded-full"
      style={{ background: color }}
    />
  );
}

function formatDashboardExposure(v: string | null): string {
  if (v === null) return "—";
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return "$0";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function DecisionsInFlightSection({
  agencyName,
  agencySubtitle,
  totals,
  openTrend,
  workflows,
  onReviewAtRisk,
  onFilterCategory,
  onOpenWorkflow,
}: {
  agencyName: string;
  agencySubtitle: string;
  totals: DashboardTotals;
  openTrend: DailyOpenPoint[];
  workflows: DashboardWorkflowSummary[];
  /** "Review now ↗" on the posture headline → opens the queue drawer
   *  with {status: at_risk, category: undefined}. */
  onReviewAtRisk: () => void;
  /** Per-category pill click on the At Risk card → opens the drawer
   *  with {status: at_risk, category}. Replaces the old local grid
   *  filter (D4: a per spec). */
  onFilterCategory: (category: QueueCategory) => void;
  onOpenWorkflow: (workflowId: string) => void;
}) {
  // Grid still sorts by at-risk count so loud workflows lead, but no
  // longer filters — the drawer owns the at-risk-narrowing UX now.
  const sortedWorkflows = sortWorkflowsByAtRisk(workflows);
  // Backend ships `at_risk_breakdown` as an array of {label, count}; TopRail
  // wants {credit, compliance, ops} with zero-defaults for missing keys.
  // See `buildAtRiskBreakdown` JSDoc for the defensive contract.
  const breakdownObject = buildAtRiskBreakdown(totals.at_risk_breakdown);
  return (
    <section className="mb-8">
      <TopRail
        agencyName={agencyName}
        agencySubtitle={agencySubtitle}
        posture={{
          open: { value: totals.open, delta: totals.open_delta_24h },
          decidedToday: {
            value: totals.decided,
            delta: totals.decided_delta_24h,
            avgCycleDays: totals.decided_avg_cycle_days,
          },
          atRisk: {
            value: totals.at_risk,
            deltaSinceYesterday: totals.at_risk_delta_24h,
            slaWindow: "24h",
            breakdown: breakdownObject,
          },
        }}
        openExtra={openTrend.length > 0 ? <TopRailSparkline points={openTrend} /> : undefined}
        onReviewAtRisk={onReviewAtRisk}
        onFilterCategory={onFilterCategory}
      />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {sortedWorkflows.map((w) => (
          <WorkflowTile
            key={w.workflow_id}
            w={w}
            onClick={() => onOpenWorkflow(w.workflow_id)}
          />
        ))}
      </div>
    </section>
  );
}

/**
 * Tiny 7-day open-count sparkline for the OPEN tile. Wider than the
 * per-workflow 4-week version and label-free — the tile already names
 * what it is; the line just shows direction.
 */
function TopRailSparkline({ points }: { points: DailyOpenPoint[] }) {
  // Match the placeholder's footprint (100% width, 20px height, viewBox
  // 0..120 / 0..20) so the slot reads consistently whether the line is
  // real data or the dashed "no data" placeholder.
  const width = 120;
  const height = 20;
  // Anchor min/max to the actual data range (not 0..N) so small variation
  // around a large absolute value renders as a visible line, not a flat
  // smear at the top of the SVG. With a 0-min anchor and counts like
  // 49-58, the line collapsed into the top 3px and read as missing.
  const values = points.map((p) => p.open_count);
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = Math.max(1, max - min);
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  // Inset the path 2px from top/bottom so the line never hugs the edge
  // of the SVG; gives a small margin where shape can read.
  const pad = 2;
  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = height - pad - ((p.open_count - min) / range) * (height - 2 * pad);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg
      className="mt-[6px] block"
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden
    >
      <path
        d={path}
        fill="none"
        stroke={ramps.gray[400]}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

function WorkflowTile({
  w,
  onClick,
}: {
  w: DashboardWorkflowSummary;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      // focus-visible (vs focus) so mouse-clicks don't leave a persistent
      // navy ring after navigation — that ring was reading as a "selected"
      // state on whichever card was last clicked. Keyboard focus still
      // surfaces a ring for a11y.
      className="rounded-md border-[0.5px] border-rule-soft bg-paper p-4 text-left transition-colors hover:border-navy hover:bg-navy-tint/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-navy/40 focus-visible:ring-offset-1"
    >
      <div className="flex items-center gap-2">
        {w.color && (
          <span
            aria-hidden
            className="h-[6px] w-[6px] rounded-full"
            style={{ backgroundColor: w.color }}
          />
        )}
        <span className="font-mono text-[11px] text-ink-faint">
          {w.workflow_id}
        </span>
      </div>
      <div className="mt-1 text-body font-medium text-ink">
        {w.workflow_name}
      </div>
      {/* Round 3: tight-pack — non-zero metrics flow left with no
          reserved spacers. Order stays Open → Decided → At-risk.
          Card width/height are fixed by the parent grid; the sparkline
          + 4-week trend below stay bottom-right regardless of count. */}
      <div className="mt-3 flex gap-6 text-body-sm">
        <Stat label="Open" value={w.open_count} alwaysShow />
        <Stat label="Decided" value={w.decided_count} />
        <Stat
          label="At risk"
          value={w.at_risk_count}
          tone={w.at_risk_count > 0 ? "warn" : "neutral"}
        />
      </div>
      {w.trend.length > 0 && <Sparkline points={w.trend} color={w.color} />}
    </button>
  );
}

/**
 * Tiny inline-SVG sparkline for the trailing 4 weeks of opened
 * decisions. Deliberately not a chart-library component — 4 data points
 * doesn't need axes or interactivity, and a 60×16 SVG path keeps the
 * dashboard tile compact. The bottom-right caption gives the latest
 * week's count so the visual doesn't have to encode the absolute scale.
 */
export function Sparkline({
  points,
  color,
}: {
  points: WeeklyOpenedPoint[];
  color: string | null;
}) {
  const width = 60;
  const height = 16;
  const max = Math.max(1, ...points.map((p) => p.opened_count));
  // Project N points across [0, width], y inverted so larger = higher.
  const stepX = points.length > 1 ? width / (points.length - 1) : 0;
  const path = points
    .map((p, i) => {
      const x = i * stepX;
      const y = height - (p.opened_count / max) * height;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const stroke = color ?? "var(--color-foreground-secondary, #6B7280)";
  const last = points[points.length - 1];
  return (
    <div className="mt-3 flex items-end justify-between">
      <span className="font-mono text-[10px] uppercase tracking-tracked text-ink-faint">
        4-week trend
      </span>
      <div className="flex items-center gap-2">
        <svg
          width={width}
          height={height}
          viewBox={`0 0 ${width} ${height}`}
          aria-hidden
        >
          <path
            d={path}
            fill="none"
            stroke={stroke}
            strokeWidth={1.25}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
        <span className="font-mono text-[10px] tabular-nums text-ink-faint">
          {last.opened_count} this wk
        </span>
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  tone = "neutral",
  alwaysShow = false,
}: {
  label: string;
  value: number;
  tone?: "neutral" | "warn";
  /** If true, render even at value=0 (Open always shows). */
  alwaysShow?: boolean;
}) {
  // Round 3: tight-pack — suppressed metrics return null so non-zero
  // metrics flow left with no gap. Open passes alwaysShow=true so it
  // anchors the row at value=0.
  if (!alwaysShow && value === 0) {
    return null;
  }
  const elevated = tone === "warn" && value > 0;
  return (
    <div>
      <div
        className={cn(
          "font-mono text-[18px] tabular-nums",
          elevated ? "text-red-600" : "text-ink",
        )}
      >
        {value}
      </div>
      <div
        className={cn(
          "text-[10px] uppercase tracking-tracked",
          elevated ? "text-red-600" : "text-ink-faint",
        )}
      >
        {label}
      </div>
    </div>
  );
}

function ApexSection({
  apex,
  onSelectApexDecision,
  onOpenApexCycles,
}: {
  apex: DashboardApex;
  onSelectApexDecision: (decisionId: string) => void;
  onOpenApexCycles: () => void;
}) {
  return (
    <ApexEnterprise
      apex={apex}
      onSelectApexDecision={onSelectApexDecision}
      onOpenApexCycles={onOpenApexCycles}
    />
  );
}

function ApexEnterprise({
  apex,
  onSelectApexDecision,
  onOpenApexCycles,
}: {
  apex: DashboardApex;
  onSelectApexDecision: (decisionId: string) => void;
  onOpenApexCycles: () => void;
}) {
  const cycle = apex.current_cycle;
  // Cycle metadata leads; the oversight-decision count drops to a
  // secondary line below — they read as one institutional artifact,
  // not two competing summary cards. The card inlines the first N
  // in-flight decision titles + owners so the answer to "which ones?"
  // sits next to the answer to "how many?".
  const apexCount = apex.open_decisions_count;
  const apexCountLine = `${apexCount} ${apexCount === 1 ? "oversight decision" : "oversight decisions"} in flight across all domains.`;
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-md border-[0.5px] border-rule-soft bg-paper p-4">
        <div className="text-tracked uppercase text-ink-soft">
          Current oversight cycle
        </div>
        {cycle ? (
          <>
            <div className="mt-2 text-body font-medium text-ink">
              {cycle.name}
            </div>
            <p className="mt-1 text-body-sm text-ink-soft">
              {cycle.open_count}{" "}
              {cycle.open_count === 1 ? "decision" : "decisions"} in flight.
              {cycle.cycle_end &&
                ` Closes ${formatDistanceToNow(parseISO(cycle.cycle_end), {
                  addSuffix: true,
                })} (${format(parseISO(cycle.cycle_end), "MMM d")}).`}
            </p>
            {cycle.open_decisions.length > 0 && (
              <CycleOpenDecisions
                decisions={cycle.open_decisions}
                moreCount={cycle.open_decisions_more}
                onSelect={onSelectApexDecision}
                onShowAll={onOpenApexCycles}
              />
            )}
            <p className="mt-3 text-body-sm text-ink-muted">
              {apexCountLine}
            </p>
          </>
        ) : (
          <>
            <p className="mt-2 text-body-sm text-ink-muted">
              No active cycle. The next one is scheduled by the agency
              head or the audit-committee chair.
            </p>
            <p className="mt-2 text-body-sm text-ink-muted">
              {apexCountLine}
            </p>
          </>
        )}
      </div>

      {apex.open_by_domain.length > 0 && (
        <ApexDomainBreakdown domains={apex.open_by_domain} />
      )}
    </div>
  );
}

/**
 * Inline list of in-flight apex decisions for the current cycle.
 *
 * Renders under the cycle metadata line so the answer to "which ones?"
 * sits next to the answer to "how many?". Each row clicks through to
 * the decision detail. When the cycle holds more decisions than the
 * server-side cap inlines, a "+N more" link routes to /oversight/cycles
 * where the full list lives.
 */
export function CycleOpenDecisions({
  decisions,
  moreCount,
  onSelect,
  onShowAll,
}: {
  decisions: DashboardApexOpenDecision[];
  moreCount: number;
  onSelect: (decisionId: string) => void;
  onShowAll: () => void;
}) {
  return (
    <ul className="mt-3 flex flex-col gap-1 border-t-[0.5px] border-rule-soft pt-3">
      {decisions.map((d) => (
        <li key={d.decision_id}>
          <button
            type="button"
            onClick={() => onSelect(d.decision_id)}
            className="flex w-full items-baseline gap-3 rounded-sm px-1 py-1 text-left hover:bg-navy-tint/30 focus:outline-none focus-visible:bg-navy-tint/30"
          >
            <span className="font-mono text-[10px] text-ink-faint shrink-0">
              {d.decision_number}
            </span>
            <span className="min-w-0 flex-1 truncate text-body-sm text-ink">
              {d.title}
            </span>
            {d.owner_name && (
              <span className="hidden shrink-0 text-body-sm text-ink-soft md:inline">
                {d.owner_name}
              </span>
            )}
          </button>
        </li>
      ))}
      {moreCount > 0 && (
        <li>
          <button
            type="button"
            onClick={onShowAll}
            className="mt-1 text-body-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
          >
            + {moreCount} more in this cycle
          </button>
        </li>
      )}
    </ul>
  );
}

/**
 * Per-domain breakdown of open apex decisions.
 *
 * Default view collapses zero-count domains so the eye lands on what's
 * in flight. A "Show all 8 domains" link expands to the full eight
 * declared domains (apex spec §3.3) in YAML order — useful when an
 * exec scanning the dashboard wants to confirm absence of activity
 * across the strategic surface, not just presence.
 */
export function ApexDomainBreakdown({
  domains,
}: {
  domains: DashboardApex["open_by_domain"];
}) {
  const [expanded, setExpanded] = useState(false);
  const nonZero = domains.filter((d) => d.open_count > 0);
  const hiddenCount = domains.length - nonZero.length;
  const visible = expanded ? domains : nonZero;
  return (
    <div className="rounded-md border-[0.5px] border-rule-soft bg-paper p-4">
      <div className="text-tracked uppercase text-ink-soft">
        Open by oversight domain
      </div>
      {visible.length === 0 ? (
        <p className="mt-3 text-body-sm text-ink-muted">
          No open oversight decisions.
        </p>
      ) : (
        <ul className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-4">
          {visible.map((d) => (
            <li
              key={d.domain_id}
              className="flex items-baseline gap-3 border-b-[0.5px] border-rule-soft pb-2 last:border-b-0 lg:border-b-0"
            >
              <span
                className={cn(
                  "w-6 shrink-0 text-right font-mono text-[16px] tabular-nums",
                  d.open_count > 0 ? "text-ink" : "text-ink-faint",
                )}
              >
                {d.open_count}
              </span>
              <div className="min-w-0">
                <div className="truncate text-body-sm text-ink">
                  {d.name}
                </div>
                {d.primary_owner_role && (
                  <div className="text-[10px] uppercase tracking-tracked text-ink-faint">
                    {d.primary_owner_role}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {hiddenCount > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-3 text-body-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {expanded ? "Show fewer" : `Show all ${domains.length} domains`}
        </button>
      )}
    </div>
  );
}

const RECENT_OUTCOMES_DEFAULT_LIMIT = 5;

/**
 * "Recently closed" panel — top decisions whose outcome was recorded in
 * the trailing 30 days. Surfaces institutional throughput on the same
 * surface that surfaces what's still open. Each row links to the
 * decision detail.
 *
 * Default render shows the top 5; an inline "Show N more" / "Show less"
 * link expands to the full list. No pagination, no modal — the list is
 * trailing-30-day-bounded so it's small enough to inline.
 */
export function RecentOutcomes({
  items,
  onSelect,
}: {
  items: DashboardRecentOutcome[];
  onSelect: (o: DashboardRecentOutcome) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible =
    expanded || items.length <= RECENT_OUTCOMES_DEFAULT_LIMIT
      ? items
      : items.slice(0, RECENT_OUTCOMES_DEFAULT_LIMIT);
  const remaining = items.length - RECENT_OUTCOMES_DEFAULT_LIMIT;
  return (
    <>
      <ul className="rounded-md border-[0.5px] border-rule-soft bg-paper">
        {visible.map((o, idx) => (
          <li
            key={o.decision_id}
            className={cn(
              idx === 0 ? "" : "border-t-[0.5px] border-rule-soft",
            )}
          >
            <button
              type="button"
              onClick={() => onSelect(o)}
              className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-navy-tint/30 focus:outline-none focus-visible:bg-navy-tint/30"
            >
              {o.workflow_color && (
                <span
                  aria-hidden
                  className="h-[6px] w-[6px] shrink-0 rounded-full"
                  style={{ backgroundColor: o.workflow_color }}
                />
              )}
              <span className="font-mono text-[11px] text-ink-faint shrink-0">
                {o.decision_number}
              </span>
              <span className="min-w-0 flex-1 truncate text-body-sm text-ink">
                {o.title}
              </span>
              <span className="hidden shrink-0 text-[11px] uppercase tracking-tracked text-ink-faint md:inline">
                {o.workflow_name}
              </span>
              <span className="shrink-0 font-mono text-[11px] text-ink-faint">
                {o.outcome_recorded_at
                  ? formatDistanceToNow(parseISO(o.outcome_recorded_at), {
                      addSuffix: true,
                    })
                  : "—"}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {remaining > 0 && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-body-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          {expanded ? "Show less" : `Show ${remaining} more`}
        </button>
      )}
    </>
  );
}

