// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useLocation, useNavigate } from "@tanstack/react-router";
import { format, parseISO } from "date-fns";
import { useMemo } from "react";

import type {
  MatterInboxBand,
  MatterInboxHorizon,
  MatterInboxRow,
  MatterInboxScope,
} from "@/api/matters";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { EmptyState } from "@/components/ds/EmptyState";
import { LeftTree } from "@/components/ds/LeftTree";
import { SkeletonRows } from "@/components/ds/Skeleton";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { useMattersInbox } from "@/hooks/useMatters";
import { useWorkflows } from "@/hooks/useWorkflows";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";

/**
 * Matters-first Inbox (MVP-BUILD-QUEUE P1). One row per Matter,
 * grouped into three bands: Incoming (calendar-forward), Inflight
 * (active work), At risk (structural gaps + adverse signals +
 * SLA breaches). At-risk wins ties.
 *
 * Bands + counts come from the server-side classifier at
 * /api/matters/inbox — same rules feed the band tiles + rail
 * Program counts so nothing drifts.
 *
 * The pre-P1 Decision-based Inbox is still reachable at
 * /inbox/decisions for the audit path (see inboxDecisions.tsx).
 */
export const inboxRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/inbox",
  component: InboxPage,
});

const SCOPE_OPTIONS: { value: MatterInboxScope; label: string }[] = [
  { value: "mine", label: "Mine" },
  { value: "team", label: "Team" },
  { value: "all_agency", label: "All agency" },
];

const HORIZON_OPTIONS: { value: MatterInboxHorizon; label: string }[] = [
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "fy", label: "FY" },
];

// Band render order — In-Flight and At Risk are the operator's
// priorities (active work + flags); Incoming is future work and
// tails the list.
const BAND_ORDER: MatterInboxBand[] = ["inflight", "at_risk", "incoming"];

const BAND_LABEL: Record<MatterInboxBand, string> = {
  incoming: "Incoming",
  inflight: "Inflight",
  at_risk: "At risk",
};

const BAND_HELP: Record<MatterInboxBand, string> = {
  incoming: "Planned disbursements arriving in the horizon",
  inflight: "Matters with active decisions",
  at_risk: "Adverse signals, structural gaps, or overdue decisions",
};

function InboxPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  const scope = (params.get("scope") as MatterInboxScope) || "mine";
  const horizon = (params.get("horizon") as MatterInboxHorizon) || "90d";
  const program = params.get("program") || undefined;

  const updateSearch = (updates: Record<string, string | undefined>) => {
    void navigate({
      to: "/inbox",
      search: (prev) => {
        const next: Record<string, string> = { ...(prev as object) } as Record<
          string,
          string
        >;
        for (const [k, v] of Object.entries(updates)) {
          if (v === undefined || v === "") delete next[k];
          else next[k] = v;
        }
        return next;
      },
    });
  };

  const inboxQuery = useMattersInbox({ scope, horizon, program });
  const { data: workflowsData } = useWorkflows();
  const workflowsById = useMemo(() => {
    const map: Record<string, { name: string }> = {};
    for (const w of workflowsData?.workflows ?? []) {
      map[w.id] = { name: w.name };
    }
    return map;
  }, [workflowsData?.workflows]);

  const bandCounts = inboxQuery.data?.band_counts ?? {
    incoming: 0,
    inflight: 0,
    at_risk: 0,
  };
  const programCounts = inboxQuery.data?.program_counts ?? {};
  const totalMatters =
    bandCounts.incoming + bandCounts.inflight + bandCounts.at_risk;

  const scopeLabel =
    scope === "mine"
      ? "your queue"
      : scope === "team"
        ? "team queue"
        : "all entitled";
  const subtitle = `${totalMatters} ${totalMatters === 1 ? "matter" : "matters"} · ${scopeLabel}`;

  const openMatter = (matterId: string) =>
    void navigate({
      to: "/matters",
      search: { id: matterId, mode: "case-file" },
    });

  return (
    <AppShellV2>
      <SplitView
        left={
          <InboxTree
            scope={scope}
            program={program}
            bandCounts={bandCounts}
            programCounts={programCounts}
            workflowsById={workflowsById}
            onScopeChange={(s) => updateSearch({ scope: s })}
            onProgramChange={(p) => updateSearch({ program: p ?? undefined })}
          />
        }
      >
        <DetailContainer
          title="Inbox"
          subtitle={subtitle}
          actions={
            <HorizonToggle
              value={horizon}
              onChange={(h) => updateSearch({ horizon: h })}
            />
          }
        >
          <div className="px-6 py-6">
            {inboxQuery.isLoading && <SkeletonRows />}
            {inboxQuery.isError && (
              <EmptyState
                headline="We couldn't load the inbox."
                body={
                  <>The matters-inbox query failed. Refresh to try again.</>
                }
              />
            )}
            {inboxQuery.isSuccess && totalMatters === 0 && (
              <EmptyInbox scope={scope} />
            )}
            {inboxQuery.isSuccess && totalMatters > 0 && (
              <div className="space-y-8">
                {BAND_ORDER.map((band) => (
                  <Band
                    key={band}
                    band={band}
                    count={bandCounts[band]}
                    rows={inboxQuery.data?.bands[band] ?? []}
                    onOpen={openMatter}
                  />
                ))}
              </div>
            )}
          </div>
        </DetailContainer>
      </SplitView>
    </AppShellV2>
  );
}

/* ─── Rail (LeftTree) ───────────────────────────────────────────────── */

function InboxTree({
  scope,
  program,
  bandCounts,
  programCounts,
  workflowsById,
  onScopeChange,
  onProgramChange,
}: {
  scope: MatterInboxScope;
  program: string | undefined;
  bandCounts: Record<MatterInboxBand, number>;
  programCounts: Record<string, number>;
  workflowsById: Record<string, { name: string }>;
  onScopeChange: (s: MatterInboxScope) => void;
  onProgramChange: (p: string | null) => void;
}) {
  const programEntries = Object.entries(programCounts).sort(
    ([, a], [, b]) => b - a,
  );
  return (
    <LeftTree>
      <LeftTree.Search placeholder="Filter matters…" />
      <LeftTree.Body>
        <LeftTree.Section title="Scope">
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

        {/* Band counts sit in the rail as a workload dashboard, not a
            filter (all three bands render in the main list at once).
            Zero-count bands stay visible per the "rail is a dashboard"
            calibration. Order mirrors the main list: priorities first
            (Inflight, At risk), Incoming trails. */}
        <LeftTree.Section title="State">
          <LeftTree.Node level={1} count={bandCounts.inflight}>
            Inflight
          </LeftTree.Node>
          <LeftTree.Node level={1} count={bandCounts.at_risk} dot="flag">
            At risk
          </LeftTree.Node>
          <LeftTree.Node level={1} count={bandCounts.incoming}>
            Incoming
          </LeftTree.Node>
        </LeftTree.Section>

        {programEntries.length > 0 && (
          <LeftTree.Section title="Program">
            {programEntries.map(([id, n]) => (
              <LeftTree.Node
                key={id}
                level={1}
                selected={program === id}
                count={n}
                onClick={() => onProgramChange(program === id ? null : id)}
              >
                {workflowsById[id]?.name ?? id}
              </LeftTree.Node>
            ))}
          </LeftTree.Section>
        )}
      </LeftTree.Body>
    </LeftTree>
  );
}

/* ─── Horizon toggle ─────────────────────────────────────────────────── */

function HorizonToggle({
  value,
  onChange,
}: {
  value: MatterInboxHorizon;
  onChange: (v: MatterInboxHorizon) => void;
}) {
  return (
    <div className="inline-flex items-center overflow-hidden rounded-md border-[0.5px] border-rule">
      {HORIZON_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "px-3 py-1 text-[12px]",
            value === opt.value
              ? "bg-navy text-white"
              : "bg-transparent text-ink-soft hover:text-ink",
          )}
          aria-pressed={value === opt.value}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Band ──────────────────────────────────────────────────────────── */

function Band({
  band,
  count,
  rows,
  onOpen,
}: {
  band: MatterInboxBand;
  count: number;
  rows: MatterInboxRow[];
  onOpen: (matterId: string) => void;
}) {
  const bandColor: Record<MatterInboxBand, string> = {
    incoming: "text-navy",
    inflight: "text-amber",
    at_risk: "text-flag",
  };
  const countPhrase: Record<MatterInboxBand, string> = {
    incoming: "on the calendar",
    inflight: "being worked",
    at_risk: "needs attention",
  };
  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between border-b-[0.5px] border-rule-soft pb-2">
        <div className="flex items-baseline gap-3">
          <span
            className={cn(
              "font-display text-[14px] font-medium",
              bandColor[band],
            )}
          >
            {BAND_LABEL[band]}
          </span>
          <span className="font-mono text-[11px] text-ink-faint">
            {count} · {countPhrase[band]}
          </span>
        </div>
        <span className="text-[12px] text-ink-muted">{BAND_HELP[band]}</span>
      </div>
      {rows.length === 0 && (
        <p className="text-[13px] text-ink-muted italic">
          {band === "incoming" &&
            "No matters are scheduled in this horizon."}
          {band === "inflight" && "No matters are being worked."}
          {band === "at_risk" && "Nothing at risk."}
        </p>
      )}
      <div className="space-y-2">
        {rows.map((row) => (
          <MatterCard key={row.id} row={row} onOpen={onOpen} />
        ))}
      </div>
    </section>
  );
}

/* ─── Card variants ─────────────────────────────────────────────────── */

function MatterCard({
  row,
  onOpen,
}: {
  row: MatterInboxRow;
  onOpen: (matterId: string) => void;
}) {
  if (row.band === "incoming") return <IncomingCard row={row} onOpen={onOpen} />;
  if (row.band === "inflight") return <InflightCard row={row} onOpen={onOpen} />;
  return <AtRiskCard row={row} onOpen={onOpen} />;
}

function CardShell({
  children,
  onOpen,
  matterId,
  extraClass,
}: {
  children: React.ReactNode;
  onOpen: (matterId: string) => void;
  matterId: string;
  extraClass?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(matterId)}
      className={cn(
        "flex w-full items-center gap-5 rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3 text-left",
        "hover:border-rule",
        extraClass,
      )}
    >
      {children}
    </button>
  );
}

function IncomingCard({
  row,
  onOpen,
}: {
  row: MatterInboxRow;
  onOpen: (matterId: string) => void;
}) {
  const date = row.planned_disbursement_at
    ? parseISO(row.planned_disbursement_at)
    : null;
  return (
    <CardShell matterId={row.id} onOpen={onOpen}>
      {date && (
        <div className="flex h-14 w-14 shrink-0 flex-col overflow-hidden rounded border-[0.5px] border-rule-soft text-center">
          <div className="bg-navy py-0.5 font-display text-[10px] font-medium tracking-wider text-white uppercase">
            {format(date, "MMM")}
          </div>
          <div className="pt-1 font-display text-[22px] font-medium leading-none text-ink">
            {format(date, "d")}
          </div>
          <div className="font-mono text-[9px] text-ink-faint">
            {format(date, "yyyy")}
          </div>
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="font-display text-[14px] font-medium text-ink">
          {matterTitle(row)}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-ink-soft">
          {row.period_label && <span>{row.period_label}</span>}
          <span className="text-ink-faint">·</span>
          <span>{row.awarding_agency}</span>
          {row.readiness && (
            <>
              <span className="text-ink-faint">·</span>
              <ReadinessPill readiness={row.readiness} />
            </>
          )}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-[13px] text-ink">
          {formatAmount(row.amount_obligated)}
        </div>
        <div className="font-display text-[10px] tracking-wider text-ink-faint uppercase">
          Obligated
        </div>
      </div>
    </CardShell>
  );
}

function InflightCard({
  row,
  onOpen,
}: {
  row: MatterInboxRow;
  onOpen: (matterId: string) => void;
}) {
  return (
    <CardShell matterId={row.id} onOpen={onOpen}>
      <div className="shrink-0">
        <StagePill stage={row.stage ?? "decision"} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-display text-[14px] font-medium text-ink">
          {matterTitle(row)}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-ink-soft">
          {row.period_label && <span>{row.period_label}</span>}
          <span className="text-ink-faint">·</span>
          <span>{row.awarding_agency}</span>
          {row.lead_decision_title && (
            <>
              <span className="text-ink-faint">·</span>
              <span className="text-ink-faint">{row.lead_decision_title}</span>
            </>
          )}
        </div>
      </div>
      <div className="shrink-0 text-right text-[12px]">
        {row.owner_name && <div className="text-ink">{row.owner_name}</div>}
        {row.oldest_open_age_days !== undefined && (
          <div className="font-mono text-[11px] text-ink-faint">
            {ageLabel(row.oldest_open_age_days)} · open
          </div>
        )}
      </div>
    </CardShell>
  );
}

function AtRiskCard({
  row,
  onOpen,
}: {
  row: MatterInboxRow;
  onOpen: (matterId: string) => void;
}) {
  return (
    <CardShell
      matterId={row.id}
      onOpen={onOpen}
      extraClass="border-l-[4px] border-l-flag pl-3"
    >
      <div className="shrink-0">
        <i
          className="ti ti-alert-triangle text-[20px] text-flag"
          aria-hidden
        />
      </div>
      <div className="min-w-0 flex-1">
        <div className="font-display text-[14px] font-medium text-ink">
          {matterTitle(row)}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-ink-soft">
          <span>{row.awarding_agency}</span>
          {row.period_label && (
            <>
              <span className="text-ink-faint">·</span>
              <span>{row.period_label}</span>
            </>
          )}
        </div>
        {row.risk_reason && (
          <div className="mt-1 flex items-center gap-1.5 font-display text-[12px] text-flag">
            <i className="ti ti-alert-circle text-[13px]" aria-hidden />
            <span>{row.risk_reason.text}</span>
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        <div className="font-mono text-[13px] text-ink">
          {formatAmount(row.amount_obligated)}
        </div>
        {row.risk_age_days !== undefined && (
          <div className="font-mono text-[11px] text-ink-soft">
            Open {row.risk_age_days}d
          </div>
        )}
      </div>
    </CardShell>
  );
}

/* ─── Pills + helpers ───────────────────────────────────────────────── */

function ReadinessPill({
  readiness,
}: {
  readiness: NonNullable<MatterInboxRow["readiness"]>;
}) {
  if (readiness.state === "ready") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border-[0.5px] border-ok/40 bg-ok-soft px-2 py-0.5 font-display text-[11px] text-ok">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
        Ready
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border-[0.5px] border-amber/40 bg-amber-soft px-2 py-0.5 font-display text-[11px] text-amber">
      <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
      {readiness.pending_count > 1
        ? `${readiness.pending_count} pre-payment controls pending`
        : "Pre-payment controls pending"}
    </span>
  );
}

function StagePill({ stage }: { stage: "decision" | "action" | "outcome" }) {
  const label = stage === "decision" ? "Decision" : stage === "action" ? "Action" : "Outcome";
  const cls =
    stage === "decision"
      ? "bg-navy-soft/20 text-navy border-navy/30"
      : stage === "action"
        ? "bg-amber-soft text-amber border-amber/30"
        : "bg-ok-soft text-ok border-ok/30";
  const dot =
    stage === "decision" ? "bg-navy" : stage === "action" ? "bg-amber" : "bg-ok";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border-[0.5px] px-2.5 py-0.5 font-display text-[11px] font-medium",
        cls,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", dot)} aria-hidden />
      {label}
    </span>
  );
}

function matterTitle(row: MatterInboxRow): string {
  // Prefer the recipient (leaf) org name when the path preview has it;
  // otherwise fall back to the awarding agency + program label.
  const recipient = row.path_preview.find((p) => p.tier === "recipient");
  if (recipient) {
    return `${recipient.label} · ${row.program_id.toUpperCase()}`;
  }
  return `${row.awarding_agency} · ${row.program_id.toUpperCase()}`;
}

function formatAmount(raw: string | null): string {
  if (!raw) return "—";
  const n = Number(raw);
  if (!Number.isFinite(n)) return raw;
  if (n >= 1_000_000_000) return `$${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n).toLocaleString()}`;
}

function ageLabel(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "1d ago";
  return `${days}d ago`;
}

function EmptyInbox({ scope }: { scope: MatterInboxScope }) {
  if (scope === "mine") {
    return (
      <EmptyState
        headline="Inbox clear."
        body={
          <>
            Nothing is currently routed to you. Matters appear here when
            you own an open decision, when a disbursement is scheduled, or
            when a signal flags one at risk.
          </>
        }
      />
    );
  }
  return (
    <EmptyState
      headline="No matters yet."
      body={
        <>
          Matters appear here when they enter the calendar, start active
          work, or a signal flags them at risk.
        </>
      }
    />
  );
}
