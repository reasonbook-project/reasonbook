// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { format, parseISO } from "date-fns";
import { useMemo } from "react";

import {
  type BoardCycle,
  type OversightFinding,
  cycleDossierUrl,
} from "@/api/oversight";
import { Button } from "@/components/ds/Button";
import {
  Breadcrumb,
  DetailContainer,
} from "@/components/ds/DetailContainer";
import { HelpTerm } from "@/components/ds/HelpTerm";
import { LeftTree } from "@/components/ds/LeftTree";
import { type Mode } from "@/components/ds/ModeTabs";
import { VerifyChainButton } from "@/components/integrity/VerifyChainButton";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import {
  useOversightCycleFindings,
  useOversightCycles,
} from "@/hooks/useOversight";

import { rootRoute } from "./__root";

/**
 * /oversight — the unified oversight surface (Phase 5 of the
 * unified-surface UI work). Sibling to /matters, /inbox, /signals.
 *
 * Tree contains:
 *  - Cycles    — every oversight cycle for the tenant, grouped by
 *                status (active → planned → concluded)
 *  - Filters   — Open / Closed finding shortcuts (stubbed; the real
 *                findings model lands in a follow-up)
 *  - Reports   — Single Audit prep, IG referral log
 *
 * Detail shows the selected cycle; modes flip between Findings,
 * Cycle summary, and Audit chain. (Corporate-board governance indices
 * live in a sibling product; DP's federal-funding oversight uses
 * Single Audit / IG referrals / OIG findings instead.)
 *
 * Oversight-tier gated: non-Enterprise tenants see a soft upsell
 * (no data fetch fires) so we don't paper an honest empty state
 * with cycle scaffolding the user can't use.
 */
type OversightMode = "findings" | "summary" | "audit-chain";
const VALID_MODES: ReadonlyArray<OversightMode> = [
  "findings",
  "summary",
  "audit-chain",
];

export const oversightRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oversight",
  validateSearch: (search: Record<string, unknown>): {
    cycleId?: string;
    mode?: OversightMode;
  } => {
    const cycleId =
      typeof search.cycleId === "string" ? search.cycleId : undefined;
    const m =
      typeof search.mode === "string" &&
      (VALID_MODES as string[]).includes(search.mode)
        ? (search.mode as OversightMode)
        : undefined;
    return { cycleId, mode: m };
  },
  component: OversightPage,
});

function OversightPage() {
  const { cycleId, mode: modeParam } = oversightRoute.useSearch();
  const navigate = useNavigate();
  const mode: OversightMode = modeParam ?? "findings";

  // Oversight is a first-class DP surface — no tier gate. The earlier
  // oversight-entitlement upsell shell was removed when this route was
  // reframed for the single-tenant federal architecture.
  const cyclesQuery = useOversightCycles();
  const cycles = useMemo(
    () => cyclesQuery.data?.items ?? [],
    [cyclesQuery.data?.items],
  );

  const selectedCycle = useMemo(
    () => cycles.find((c) => c.id === cycleId) ?? null,
    [cycles, cycleId],
  );

  const setSelected = (id: string | null, m?: OversightMode) =>
    void navigate({
      to: "/oversight",
      search: {
        cycleId: id ?? undefined,
        mode: m ?? (id ? mode : undefined),
      },
    });
  const setMode = (m: OversightMode) =>
    void navigate({
      to: "/oversight",
      search: { cycleId, mode: m },
    });

  return (
    <AppShellV2>
      <SplitView
        left={
          <OversightTree
            cycles={cycles}
            selectedId={cycleId ?? null}
            onSelect={(id) => setSelected(id)}
          />
        }
      >
        {selectedCycle ? (
          <CycleDetail
            cycle={selectedCycle}
            mode={mode}
            onModeChange={setMode}
            onClearSelection={() => setSelected(null)}
          />
        ) : (
          <OversightOverview
            cycles={cycles}
            onSelectCycle={(id) => setSelected(id)}
          />
        )}
      </SplitView>
    </AppShellV2>
  );
}

/* ─── Tree ────────────────────────────────────────────────────────── */

function OversightTree({
  cycles,
  selectedId,
  onSelect,
}: {
  cycles: BoardCycle[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const active = cycles.filter((c) => c.status === "active");
  const planned = cycles.filter((c) => c.status === "planned");
  const concluded = cycles.filter((c) => c.status === "concluded");

  return (
    <LeftTree>
      <LeftTree.Search placeholder="Search oversight…" />
      <LeftTree.Body>
        <LeftTree.Section title="Cycles">
          {active.map((c) => (
            <LeftTree.Node
              key={c.id}
              level={1}
              selected={c.id === selectedId}
              count={c.decision_count ?? undefined}
              dot="amber"
              onClick={() => onSelect(c.id)}
            >
              {c.name}
            </LeftTree.Node>
          ))}
          {planned.map((c) => (
            <LeftTree.Node
              key={c.id}
              level={1}
              selected={c.id === selectedId}
              count={c.decision_count ?? undefined}
              dot="muted"
              onClick={() => onSelect(c.id)}
            >
              {c.name}
            </LeftTree.Node>
          ))}
          {concluded.map((c) => (
            <LeftTree.Node
              key={c.id}
              level={1}
              selected={c.id === selectedId}
              count={c.decision_count ?? undefined}
              dot="green"
              onClick={() => onSelect(c.id)}
            >
              {c.name}
            </LeftTree.Node>
          ))}
          {cycles.length === 0 && (
            <div className="px-3.5 py-6 text-[12px] text-ink-muted">
              No cycles seeded yet.
            </div>
          )}
        </LeftTree.Section>

        <LeftTree.Section
          title={<HelpTerm term="finding">Filters</HelpTerm>}
        >
          <LeftTree.Node level={1} dot="flag" count={0}>
            Open findings
          </LeftTree.Node>
          <LeftTree.Node level={1} dot="green" count={0}>
            Closed findings
          </LeftTree.Node>
          <LeftTree.Node level={1} count={0}>
            Findings under appeal
          </LeftTree.Node>
        </LeftTree.Section>

        <LeftTree.Section title="Reports">
          <LeftTree.Node level={1}>Single Audit prep</LeftTree.Node>
          <LeftTree.Node level={1}>IG referral log</LeftTree.Node>
        </LeftTree.Section>
      </LeftTree.Body>
    </LeftTree>
  );
}

/* ─── Cycle detail (right pane when a cycle is selected) ──────────── */

function CycleDetail({
  cycle,
  mode,
  onModeChange,
  onClearSelection,
}: {
  cycle: BoardCycle;
  mode: OversightMode;
  onModeChange: (m: OversightMode) => void;
  onClearSelection: () => void;
}) {
  const periodLabel = (() => {
    try {
      return `${format(parseISO(cycle.cycle_start), "MMM d, yyyy")} – ${format(
        parseISO(cycle.cycle_end),
        "MMM d, yyyy",
      )}`;
    } catch {
      return `${cycle.cycle_start} – ${cycle.cycle_end}`;
    }
  })();

  const breadcrumb = (
    <Breadcrumb
      crumbs={[
        { label: "Oversight", onClick: onClearSelection },
        { label: cycle.status, onClick: onClearSelection },
        { label: cycle.name, current: true },
      ]}
    />
  );

  const modes: Mode[] = [
    {
      id: "findings",
      label: <HelpTerm term="finding">Findings</HelpTerm>,
      count: 0,
    },
    { id: "summary", label: "Cycle summary" },
    {
      id: "audit-chain",
      label: <HelpTerm term="hash-chain">Audit chain</HelpTerm>,
    },
  ];

  const actions = (
    <>
      <Button
        variant="ghost"
        compact
        onClick={() =>
          window.open(
            cycleDossierUrl(cycle.id),
            "_blank",
            "noopener,noreferrer",
          )
        }
      >
        <i className="ti ti-file-export text-[14px]" />
        Export cycle report
      </Button>
      <VerifyChainButton />
    </>
  );

  return (
    <DetailContainer
      breadcrumb={breadcrumb}
      title={cycle.name}
      subtitle={`${cycle.cycle_type} · ${periodLabel} · ${cycle.status}`}
      actions={actions}
      modes={modes}
      currentMode={mode}
      onModeChange={(id) => onModeChange(id as OversightMode)}
    >
      {mode === "findings" && <FindingsPane cycle={cycle} />}
      {mode === "summary" && <CycleSummaryPane cycle={cycle} />}
      {mode === "audit-chain" && <AuditChainPane />}
    </DetailContainer>
  );
}

/* ─── Findings pane ─────────────────────────────────────────────────── */

const FINDING_SOURCE_LABEL: Record<string, string> = {
  oig: "OIG",
  gao: "GAO",
  single_audit: "Single Audit",
  internal_audit: "Internal audit",
};

const FINDING_SEVERITY_PALETTE: Record<string, { fg: string; bg: string }> = {
  critical: { fg: "#9c1c1c", bg: "#fee2e2" },
  high: { fg: "#b7791f", bg: "#fef3c7" },
  medium: { fg: "#0d3a6a", bg: "#dbeafe" },
  low: { fg: "#54607a", bg: "#e2e8f0" },
};

const FINDING_STATUS_PALETTE: Record<string, { fg: string; bg: string }> = {
  open: { fg: "#9c1c1c", bg: "#fee2e2" },
  closed: { fg: "#0f5132", bg: "#d1e7dd" },
  under_appeal: { fg: "#7c3aed", bg: "#ede9fe" },
};

function FindingsPane({ cycle }: { cycle: BoardCycle }) {
  const findingsQuery = useOversightCycleFindings(cycle.id);
  const items = findingsQuery.data?.items ?? [];
  const counts = findingsQuery.data?.counts;

  return (
    <div className="px-6 py-6 space-y-6">
      <StatStrip
        cells={[
          { label: "Findings", value: counts?.total ?? 0 },
          { label: "Open", value: counts?.open ?? 0, emphasis: "flag" },
          { label: "Closed", value: counts?.closed ?? 0 },
          {
            label: "Under appeal",
            value: counts?.under_appeal ?? 0,
          },
        ]}
      />

      <SectionCard
        title="Findings list"
        meta={`${cycle.name} · this cycle`}
      >
        {findingsQuery.isLoading && (
          <p className="text-[13px] text-ink-muted">Loading findings…</p>
        )}
        {findingsQuery.isError && (
          <p className="text-[13px] text-flag">
            Couldn't load findings for this cycle.
          </p>
        )}
        {findingsQuery.isSuccess && items.length === 0 && (
          <p className="text-[13px] text-ink-soft">
            No findings on this cycle. New findings are opened when OIG,
            GAO, Single Audit, or internal audit surfaces a written
            observation against a matter in this cycle's window.
          </p>
        )}
        {items.length > 0 && (
          <ul className="space-y-3">
            {items.map((f) => (
              <FindingRow key={f.id} finding={f} />
            ))}
          </ul>
        )}
      </SectionCard>
    </div>
  );
}

function FindingRow({ finding }: { finding: OversightFinding }) {
  const sev = FINDING_SEVERITY_PALETTE[finding.severity] ?? {
    fg: "#54607a",
    bg: "#e2e8f0",
  };
  const status = FINDING_STATUS_PALETTE[finding.status] ?? {
    fg: "#54607a",
    bg: "#e2e8f0",
  };
  return (
    <li className="rounded-md border-[0.5px] border-rule bg-paper px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2 flex-wrap">
            <span className="font-mono text-[11px] text-ink-faint">
              {finding.finding_number}
            </span>
            <span className="text-[14px] font-medium text-ink">
              {finding.title}
            </span>
          </div>
          <div className="mt-0.5 flex items-baseline gap-1.5 flex-wrap font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
            <span>{FINDING_SOURCE_LABEL[finding.source] ?? finding.source}</span>
            <span>·</span>
            <span>opened {finding.opened_at.slice(0, 10)}</span>
            {finding.closed_at && (
              <>
                <span>·</span>
                <span>closed {finding.closed_at.slice(0, 10)}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className="rounded-sm px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.06em]"
            style={{ color: sev.fg, backgroundColor: sev.bg }}
          >
            {finding.severity}
          </span>
          <span
            className="rounded-sm px-1.5 py-[1px] font-mono text-[10px] uppercase tracking-[0.06em]"
            style={{ color: status.fg, backgroundColor: status.bg }}
          >
            {finding.status.replace("_", " ")}
          </span>
        </div>
      </div>
      <p className="mt-2 text-[13px] text-ink-soft leading-relaxed">
        {finding.observation}
      </p>
      {finding.citations.length > 0 && (
        <div className="mt-2 flex items-baseline gap-1.5 flex-wrap">
          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
            Citations
          </span>
          {finding.citations.map((c) => (
            <span
              key={c}
              className="rounded-sm border-[0.5px] border-rule-soft px-1.5 py-[1px] font-mono text-[10.5px] text-ink-soft"
            >
              {c}
            </span>
          ))}
        </div>
      )}
      {finding.cited_matter_ids.length > 0 && (
        <div className="mt-1.5 font-mono text-[10.5px] text-ink-faint">
          Cites {finding.cited_matter_ids.length}{" "}
          {finding.cited_matter_ids.length === 1 ? "matter" : "matters"}
        </div>
      )}
      {finding.disposition && (
        <div className="mt-2 border-t-[0.5px] border-rule-faint pt-2">
          <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
            Disposition
          </span>
          <p className="mt-0.5 text-[12.5px] text-ink-soft leading-relaxed">
            {finding.disposition}
          </p>
        </div>
      )}
    </li>
  );
}

/* ─── Cycle summary pane ──────────────────────────────────────────── */

function CycleSummaryPane({ cycle }: { cycle: BoardCycle }) {
  return (
    <div className="px-6 py-6 space-y-6">
      <SectionCard title="Cycle" meta={cycle.status}>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px]">
          <SummaryField label="Name" value={cycle.name} />
          <SummaryField label="Type" value={cycle.cycle_type} />
          <SummaryField
            label="Committee"
            value={cycle.committee ?? "—"}
          />
          <SummaryField
            label="Period"
            value={`${cycle.cycle_start} → ${cycle.cycle_end}`}
          />
          <SummaryField
            label="Meeting date"
            value={cycle.meeting_date ?? "—"}
          />
          <SummaryField
            label="Decisions"
            value={String(cycle.decision_count ?? 0)}
          />
        </dl>
        {cycle.notes && (
          <p className="mt-4 pt-4 border-t-[0.5px] border-rule-faint text-[13px] text-ink-soft">
            {cycle.notes}
          </p>
        )}
      </SectionCard>
    </div>
  );
}

/* ─── Audit chain pane ────────────────────────────────────────────── */

function AuditChainPane() {
  return (
    <div className="px-6 py-6 space-y-6">
      <SectionCard
        title={<HelpTerm term="hash-chain">Hash chain</HelpTerm>}
        meta="tamper-evident ledger"
      >
        <p className="text-[13px] text-ink-soft mb-3">
          Every event on every decision in this oversight cycle is
          cryptographically chained. Verify the chain to confirm no
          event has been modified after the fact.
        </p>
        <VerifyChainButton />
      </SectionCard>
    </div>
  );
}

/* ─── Overview when no cycle is selected ──────────────────────────── */

function OversightOverview({
  cycles,
  onSelectCycle,
}: {
  cycles: BoardCycle[];
  onSelectCycle: (id: string) => void;
}) {
  const active = cycles.filter((c) => c.status === "active");
  const planned = cycles.filter((c) => c.status === "planned");
  const concluded = cycles.filter((c) => c.status === "concluded");
  return (
    <div className="px-8 py-10 max-w-[720px]">
      <h1 className="text-[22px] font-display font-medium tracking-[-0.01em] text-ink mb-1">
        Oversight
      </h1>
      <p className="text-[14px] text-ink-soft mb-6">
        Pick a cycle from the tree to see its findings, cycle summary,
        and audit chain.
      </p>
      <div className="grid grid-cols-3 gap-0 border-[0.5px] border-rule rounded-md overflow-hidden">
        <OverviewStat label="Active" value={active.length} />
        <OverviewStat label="Planned" value={planned.length} />
        <OverviewStat label="Concluded" value={concluded.length} />
      </div>

      {active.length > 0 && (
        <div className="mt-8">
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint mb-2">
            Active now
          </div>
          <ul className="border-[0.5px] border-rule rounded-md overflow-hidden">
            {active.map((c) => (
              <li
                key={c.id}
                className="border-b-[0.5px] border-rule-faint last:border-b-0"
              >
                <button
                  type="button"
                  onClick={() => onSelectCycle(c.id)}
                  className="w-full text-left px-4 py-3 hover:bg-bg-warm flex items-center justify-between"
                >
                  <span className="text-[13.5px] text-ink">{c.name}</span>
                  <span className="text-[12px] font-mono text-ink-faint">
                    {c.decision_count ?? 0} decisions
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/* ─── Helpers ─────────────────────────────────────────────────────── */

function SectionCard({
  title,
  meta,
  children,
}: {
  title: React.ReactNode;
  meta?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-[0.5px] border-rule rounded-md overflow-hidden">
      <div className="px-4 py-2.5 border-b-[0.5px] border-rule-soft bg-bg-warm flex items-center justify-between">
        <span className="text-[11px] tracking-[0.08em] uppercase font-medium text-ink-soft">
          {title}
        </span>
        {meta && (
          <span className="text-[11px] text-ink-faint">{meta}</span>
        )}
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}

function SummaryField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint mb-1">
        {label}
      </div>
      <div className="text-ink">{value}</div>
    </div>
  );
}

function StatStrip({
  cells,
}: {
  cells: { label: string; value: number | string; emphasis?: "flag" }[];
}) {
  return (
    <div className="grid grid-cols-4 gap-0 border-[0.5px] border-rule rounded-md overflow-hidden">
      {cells.map((c, i) => (
        <div
          key={i}
          className="px-5 py-4 border-r-[0.5px] border-rule-faint last:border-r-0"
        >
          <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint mb-1">
            {c.label}
          </div>
          <div
            className={`text-[22px] font-display font-medium tracking-[-0.01em] ${
              c.emphasis === "flag" ? "text-flag" : "text-ink"
            }`}
          >
            {c.value}
          </div>
        </div>
      ))}
    </div>
  );
}

function OverviewStat({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="px-5 py-4 border-r-[0.5px] border-rule-faint last:border-r-0">
      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint mb-1">
        {label}
      </div>
      <div className="text-[22px] font-display font-medium tracking-[-0.01em] text-ink">
        {value}
      </div>
    </div>
  );
}
