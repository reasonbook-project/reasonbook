// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute } from "@tanstack/react-router";
import { type ReactNode, useState } from "react";

import {
  type Connector,
  type ConnectorRun,
  type ConnectorStatus,
} from "@/api/connectors";
import { Button } from "@/components/ds/Button";
import { Drawer } from "@/components/ds/Drawer";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import {
  useConnectorRuns,
  useConnectors,
  useSyncConnector,
} from "@/hooks/useConnectors";

import { rootRoute } from "../__root";

/**
 * /settings/connectors — global connector registry.
 *
 * Per ADR (project_usaspending_connector_reference.md memo), connectors
 * are shared infrastructure, not per-workflow config. USASpending feeds
 * multiple workflows (CDBG, NIH-R01, Treasury); configure it once here
 * rather than duplicate across every workflow that consumes it.
 *
 * Backed by /api/connectors, which reads from the Postgres
 * `connectors` table (migration 0045). The standalone collector's
 * ingest_cursor + ingest_runs projections feed the same shape here
 * (Run sync / Configure / View runs wire in a follow-up commit).
 */
export const settingsConnectorsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/connectors",
  component: ConnectorsPage,
});

function ConnectorsPage() {
  const connectorsQuery = useConnectors();
  const items = connectorsQuery.data?.items ?? [];

  const subtitle = connectorsQuery.isLoading
    ? "loading…"
    : `${items.length} configured · federal-system data sources`;

  return (
    <SettingsLayout title="Connectors" subtitle={subtitle}>
      <p className="text-[13px] text-ink-soft mb-6 max-w-[640px]">
        Connectors are the federal-system data sources DP ingests
        from. Each is configured once and feeds whichever workflows
        consume its data. No manual upload — every record arrives
        through a connector with a hash-chained provenance trail.
      </p>

      {connectorsQuery.isLoading && (
        <p className="text-[13px] text-ink-muted">Loading connectors…</p>
      )}
      {connectorsQuery.isError && (
        <p className="text-[13px] text-flag">
          Couldn't load the connector registry.
        </p>
      )}
      {connectorsQuery.isSuccess && items.length === 0 && (
        <p className="text-[13px] text-ink-muted">
          No connectors configured yet.
        </p>
      )}

      <div className="space-y-4">
        {items.map((c) => (
          <ConnectorCard key={c.id} connector={c} />
        ))}
      </div>

    </SettingsLayout>
  );
}

/* ─── Card ────────────────────────────────────────────────────────── */

function ConnectorCard({ connector }: { connector: Connector }) {
  const sync = useSyncConnector();
  const [runsOpen, setRunsOpen] = useState(false);

  const runSync = () => {
    sync.mutate(connector.id);
  };

  return (
    <section className="border-[0.5px] border-rule rounded-md overflow-hidden bg-paper">
      <header className="px-5 py-4 border-b-[0.5px] border-rule-soft flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-[15px] font-display font-medium tracking-[-0.01em] text-ink mb-1">
            {connector.name}
          </h3>
          <p className="text-[12.5px] text-ink-soft">{connector.source}</p>
        </div>
        <StatusBadge status={connector.status} />
      </header>

      <dl className="px-5 py-4 grid grid-cols-[140px_1fr] gap-x-4 gap-y-2.5 text-[13px]">
        <Field
          label="Last sync"
          value={
            connector.last_sync_at ? (
              <>
                {fmtDateTime(connector.last_sync_at)}
                {connector.last_sync_record_count !== null && (
                  <>
                    {" · "}
                    <span className="font-mono">
                      {connector.last_sync_record_count.toLocaleString()}
                    </span>{" "}
                    records ingested
                  </>
                )}
              </>
            ) : (
              "—"
            )
          }
        />
        <Field
          label="Window"
          value={
            connector.window_start && connector.window_end
              ? `${fmtDate(connector.window_start)} → ${fmtDate(connector.window_end)}`
              : "—"
          }
        />
        <Field
          label="Filter"
          value={connector.filter_label ?? <Muted>none</Muted>}
        />
        <Field
          label="Next sync"
          value={
            connector.next_sync_at ? (
              <>
                {fmtRelative(connector.next_sync_at)}
                {connector.schedule_label && (
                  <span className="text-ink-faint">
                    {" · "}
                    {connector.schedule_label}
                  </span>
                )}
              </>
            ) : (
              <Muted>not scheduled</Muted>
            )
          }
        />
        <Field
          label="Integrity"
          value={
            connector.integrity_verified ? (
              <span className="text-cleared">
                ✓ Hash chain verified
                {connector.integrity_verified_at && (
                  <span className="text-ink-faint">
                    {" · "}
                    {fmtTimeOnly(connector.integrity_verified_at)}
                  </span>
                )}
              </span>
            ) : (
              <span className="text-flag">Chain not verified</span>
            )
          }
        />
        <Field
          label="Feeds"
          value={
            connector.feeds_workflow_ids.length > 0 ? (
              <span>
                {connector.feeds_workflow_ids
                  .map(humanizeWorkflowId)
                  .join(", ")}
              </span>
            ) : (
              <Muted>no workflows</Muted>
            )
          }
        />
      </dl>

      <footer className="px-5 py-3 border-t-[0.5px] border-rule-soft bg-bg-warm flex items-center gap-2">
        <Button
          compact
          variant="primary"
          onClick={runSync}
          disabled={sync.isPending}
        >
          {sync.isPending ? "Syncing…" : "Run sync now"}
        </Button>
        <Button compact variant="ghost" disabled>
          Configure
        </Button>
        <Button
          compact
          variant="ghost"
          onClick={() => setRunsOpen(true)}
        >
          View runs
        </Button>
        {sync.isError && (
          <span className="ml-2 text-[11px] text-flag">Sync failed</span>
        )}
      </footer>

      <RunsDrawer
        open={runsOpen}
        onClose={() => setRunsOpen(false)}
        connector={connector}
      />
    </section>
  );
}

/* ─── Runs drawer ────────────────────────────────────────────────── */

function RunsDrawer({
  open,
  onClose,
  connector,
}: {
  open: boolean;
  onClose: () => void;
  connector: Connector;
}) {
  const runsQuery = useConnectorRuns(connector.id, { enabled: open });
  const items = runsQuery.data?.items ?? [];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      ariaLabel={`${connector.name} ingest runs`}
      width={540}
    >
      <div className="px-5 py-4 border-b-[0.5px] border-rule-soft flex items-center justify-between">
        <div className="min-w-0">
          <h2 className="text-[15px] font-display font-medium tracking-[-0.01em] text-ink">
            {connector.name}
          </h2>
          <p className="text-[11px] text-ink-faint tracking-[0.06em] uppercase">
            Ingest runs
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="text-[13px] text-ink-soft hover:text-ink"
        >
          Close
        </button>
      </div>
      <div className="px-5 py-4">
        <p className="text-[12.5px] text-ink-soft mb-4">
          Most recent ingest runs for this connector. Each row is a
          single invocation (collect, sync-agencies, verify, signals).
        </p>

        {runsQuery.isLoading && (
          <p className="text-[13px] text-ink-muted">Loading runs…</p>
        )}
        {runsQuery.isError && (
          <p className="text-[13px] text-flag">Couldn't load runs.</p>
        )}
        {runsQuery.isSuccess && items.length === 0 && (
          <p className="text-[13px] text-ink-muted">
            No runs recorded yet. Click "Run sync now" to record the
            first one.
          </p>
        )}

        {items.length > 0 && (
          <ul className="border-[0.5px] border-rule rounded-md overflow-hidden">
            {items.map((r) => (
              <RunRow key={r.id} run={r} />
            ))}
          </ul>
        )}
      </div>
    </Drawer>
  );
}

function RunRow({ run }: { run: ConnectorRun }) {
  return (
    <li className="border-b-[0.5px] border-rule-faint last:border-b-0 px-4 py-3 grid grid-cols-[90px_1fr_auto_auto] items-center gap-3 text-[12.5px]">
      <span className="font-mono text-[11px] text-ink-soft">
        {run.run_type}
      </span>
      <div className="flex flex-col">
        <span className="whitespace-nowrap text-ink">
          {fmtDateTime(run.started_at)}
        </span>
        {run.window_start && run.window_end && (
          <span className="whitespace-nowrap text-[11.5px] text-ink-muted">
            data window · {fmtDate(run.window_start)} → {fmtDate(run.window_end)}
          </span>
        )}
      </div>
      <span className="whitespace-nowrap font-mono text-ink">
        {run.record_count !== null
          ? `${run.record_count.toLocaleString()} records`
          : "—"}
      </span>
      <RunStatusBadge status={run.status} />
    </li>
  );
}

function RunStatusBadge({ status }: { status: ConnectorRun["status"] }) {
  const cfg = {
    success: { dot: "bg-cleared", label: "Success", text: "text-cleared" },
    failure: { dot: "bg-flag", label: "Failure", text: "text-flag" },
    in_progress: {
      dot: "bg-accent-warning",
      label: "In progress",
      text: "text-accent-warning",
    },
  }[status];
  return (
    <span className="inline-flex items-center gap-1.5 text-[10px] font-medium tracking-[0.06em] uppercase">
      <span aria-hidden className={`w-2 h-2 rounded-full ${cfg.dot}`} />
      <span className={cfg.text}>{cfg.label}</span>
    </span>
  );
}

/* ─── Sub-components ──────────────────────────────────────────────── */

function StatusBadge({ status }: { status: ConnectorStatus }) {
  const config = {
    connected: { dot: "bg-cleared", label: "Connected", text: "text-cleared" },
    degraded: { dot: "bg-accent-warning", label: "Degraded", text: "text-accent-warning" },
    disconnected: { dot: "bg-flag", label: "Disconnected", text: "text-flag" },
  }[status];
  return (
    <span className="shrink-0 inline-flex items-center gap-1.5 text-[11px] font-medium tracking-[0.06em] uppercase">
      <span
        aria-hidden
        className={`w-2 h-2 rounded-full ${config.dot}`}
      />
      <span className={config.text}>{config.label}</span>
    </span>
  );
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt className="text-[10px] tracking-[0.08em] uppercase text-ink-faint font-medium pt-0.5">
        {label}
      </dt>
      <dd className="text-ink">{value}</dd>
    </>
  );
}

function Muted({ children }: { children: ReactNode }) {
  return <span className="text-ink-faint">{children}</span>;
}

/* ─── Formatting helpers ──────────────────────────────────────────── */

function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtTimeOnly(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtRelative(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  const hours = Math.round(ms / 3_600_000);
  if (Math.abs(hours) < 1) return "less than an hour";
  if (hours > 0 && hours < 24) return `in ${hours}h`;
  if (hours < 0 && hours > -24) return `${-hours}h ago`;
  const days = Math.round(hours / 24);
  if (days > 0) return `in ${days}d`;
  return `${-days}d ago`;
}

function humanizeWorkflowId(id: string): string {
  const overrides: Record<string, string> = {
    cdbg: "CDBG",
    "nih-r01": "NIH-R01",
    "treasury-disbursement": "Treasury-disbursement",
  };
  return overrides[id] ?? id;
}
