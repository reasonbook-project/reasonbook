// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute } from "@tanstack/react-router";

import { type BoardCycle, cycleDossierUrl } from "@/api/oversight";
import { PageHeader } from "@/components/ds/PageHeader";
import { HelpLink } from "@/components/help/HelpLink";
import { useOversightCycles } from "@/hooks/useOversight";

import { AppShellV2 } from "@/components/shell/AppShellV2";

import { rootRoute } from "./__root";

/**
 * /oversight/cycles — oversight cycle dossier surface.
 *
 * Lists every oversight cycle for the tenant grouped by status
 * (Active → Planned → Concluded). Each row shows the cycle name,
 * dates, decision count, and a download affordance for the dossier
 * PDF when the cycle is concluded (the dossier draft is also
 * downloadable for active cycles, useful for committee-prep dry runs).
 *
 * Cycle creation isn't surfaced here in v1 — cycle planning is light
 * and mostly administrative; the path-of-least-resistance is seed/API
 * for now. Add a creation form later if it becomes a real friction
 * point in pilot conversations.
 *
 * Oversight-tier gated: non-Enterprise tenants don't reach this route
 * from the rail. Backend `_require_oversight` returns 403 if hit
 * directly.
 */
export const apexCyclesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/oversight/cycles",
  component: ApexCyclesPageShell,
});

/** AppShellV2 wrap so this route renders with the unified top nav. */
function ApexCyclesPageShell() {
  return (
    <AppShellV2>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <ApexCyclesPage />
      </div>
    </AppShellV2>
  );
}

export function ApexCyclesPage() {
  const cycles = useOversightCycles();

  return (
    <div className="px-7 py-7">
      <PageHeader
        breadcrumb={<span>Oversight › Cycle dossiers</span>}
        eyebrow={
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
            Agency oversight & committees
          </span>
        }
        title="Oversight cycle dossiers"
        subtitle="Cycle-level summary of every oversight decision resolved in the cycle. Concluded-cycle dossiers are committee-ready PDFs; active-cycle dossiers are drafts updated as decisions resolve."
        right={
          <HelpLink
            topic="apex/board-cycle-dossiers"
            variant="icon"
            ariaLabel="Help: oversight cycle dossiers"
          />
        }
      />

      {cycles.isLoading && (
        <p className="text-body-sm text-ink-muted">Loading…</p>
      )}
      {cycles.isError && (
        <p className="text-body-sm text-critical-text">
          Couldn't load oversight cycles.
        </p>
      )}
      {cycles.isSuccess && cycles.data.items.length === 0 && (
        <div className="rounded-md border-[0.5px] border-rule-soft bg-rule-faint px-4 py-6 text-body-sm text-ink-muted">
          No oversight cycles yet. Cycles seed via the API or the oversight
          back-office tooling — once a cycle exists you'll see it here
          with its dossier download.
        </div>
      )}
      {cycles.isSuccess && cycles.data.items.length > 0 && (
        <CyclesByStatus items={cycles.data.items} />
      )}
    </div>
  );
}

function CyclesByStatus({ items }: { items: BoardCycle[] }) {
  // Group rather than re-query — backend already orders by cycle_start desc;
  // status grouping preserves that within each bucket.
  const active = items.filter((c) => c.status === "active");
  const planned = items.filter((c) => c.status === "planned");
  const concluded = items.filter((c) => c.status === "concluded");

  return (
    <div className="flex flex-col gap-8">
      {active.length > 0 && (
        <CycleGroup title="Active" cycles={active} />
      )}
      {planned.length > 0 && (
        <CycleGroup title="Planned" cycles={planned} />
      )}
      {concluded.length > 0 && (
        <CycleGroup title="Concluded" cycles={concluded} />
      )}
    </div>
  );
}

function CycleGroup({ title, cycles }: { title: string; cycles: BoardCycle[] }) {
  return (
    <section>
      <h3 className="mb-3 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-ink-faint">
        {title} · {cycles.length}
      </h3>
      <ul className="flex flex-col gap-2">
        {cycles.map((c) => (
          <CycleRow key={c.id} cycle={c} />
        ))}
      </ul>
    </section>
  );
}

function CycleRow({ cycle }: { cycle: BoardCycle }) {
  const start = new Date(cycle.cycle_start).toLocaleDateString();
  const end = new Date(cycle.cycle_end).toLocaleDateString();
  const meeting = cycle.meeting_date
    ? new Date(cycle.meeting_date).toLocaleDateString()
    : null;
  const count = cycle.decision_count ?? 0;
  // The dossier is renderable at any cycle status. For 'concluded' we frame
  // it as the committee-ready artifact; for 'active' it's a draft — same
  // PDF either way per dp/oversight/dossier.py, but the label sets
  // expectations.
  const dossierLabel = cycle.status === "concluded" ? "Download dossier" : "Download draft";

  return (
    <li className="rounded-md border-[0.5px] border-rule-soft bg-paper px-5 py-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-baseline gap-3">
            <h4 className="text-[16px] font-medium tracking-tight text-ink">
              {cycle.name}
            </h4>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
              {cycle.cycle_type.replace(/_/g, " ")}
            </span>
            {cycle.committee && (
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-faint">
                · {cycle.committee.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <div className="mt-1 text-body-sm text-ink-soft">
            {start} – {end}
            {meeting && <> · meeting {meeting}</>}
          </div>
          <div className="mt-2 text-body-sm text-ink-muted">
            {count} oversight decision{count === 1 ? "" : "s"} tied to this cycle
          </div>
          {cycle.notes && (
            <p className="mt-3 max-w-prose text-body-sm text-ink-soft">
              {cycle.notes}
            </p>
          )}
        </div>
        <div className="shrink-0">
          <a
            href={cycleDossierUrl(cycle.id)}
            // No `download` attr — the backend already sets
            // Content-Disposition: attachment, so the browser names
            // the file from the response header.
            className="border-hairline border-navy text-navy hover:bg-navy/5 inline-flex items-center justify-center rounded-md border px-4 py-2 text-[13px] font-medium leading-none transition-colors"
          >
            {dossierLabel}
          </a>
        </div>
      </div>
    </li>
  );
}
