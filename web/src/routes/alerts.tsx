// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { useMemo, useState } from "react";

import type {
  Alert,
  AlertSeverity,
  AlertSource,
  AlertStatus,
  DispositionAction,
  MatterLinkFilter,
} from "@/api/alerts";
import { MatchToMatterModal } from "@/components/alerts/MatchToMatterModal";
import { DispositionDrawer } from "@/components/alerts/DispositionDrawer";
import { Button } from "@/components/ds/Button";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { HelpTerm } from "@/components/ds/HelpTerm";
import { LeftTree } from "@/components/ds/LeftTree";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { useAlerts } from "@/hooks/useAlerts";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";

/**
 * Signals page — triage with recorded dispositions.
 *
 * Per docs/architecture/fedRAMP/ALERTS-SPEC.md. Detection is not
 * governance: the UI enforces what the schema enforces — no close path
 * without rationale.
 *
 * The dismissed-signals trail is arguably the most valuable audit artifact
 * here (memory: project_dismissed_alerts_audit_value), so dismiss + reason
 * + rationale gets the same UX weight as promote.
 *
 * Surface vocabulary: "Signals". Data-layer vocabulary: "alerts" (DB
 * table, API path, hook name). One concept, two names by layer.
 */
export const alertsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/signals",
  component: AlertsPage,
});

/* ─── Filter shape ────────────────────────────────────────────────── */

type StatusFilter = AlertStatus | "actionable";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "actionable", label: "New" },
  { value: "triaged", label: "Held" },
  { value: "promoted", label: "Promoted" },
  { value: "dismissed", label: "Dismissed" },
];

const SOURCE_OPTIONS: { value: AlertSource; label: string }[] = [
  { value: "fraud_risk_screening", label: "Fraud-risk screening" },
  { value: "flow_graph", label: "Flow graph" },
  { value: "identity", label: "Identity" },
];

const SEVERITY_OPTIONS: { value: AlertSeverity; label: string }[] = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

function passesStatus(a: Alert, status: StatusFilter): boolean {
  if (status === "actionable")
    return a.current_status === "new" || a.current_status === "reopened";
  return a.current_status === status;
}

function AlertsPage() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<StatusFilter>("actionable");
  const [source, setSource] = useState<AlertSource | null>(null);
  const [severity, setSeverity] = useState<AlertSeverity | null>(null);
  const [q, setQ] = useState("");
  // Matcher-first default — unattached alerts are the primary reason
  // to land on this page (nothing else in the app surfaces them). The
  // reader can switch to Attached or All when auditing historically-
  // dispositioned signals.
  const [matterLink, setMatterLink] = useState<MatterLinkFilter | null>(
    "unattached",
  );

  const alertsQuery = useAlerts({
    source: source ? [source] : undefined,
    matter_link: matterLink ?? undefined,
  });

  const counts = alertsQuery.data?.counts;
  const rawItems = useMemo(
    () => alertsQuery.data?.items ?? [],
    [alertsQuery.data?.items],
  );

  // Filter items client-side by status + severity + free-text query.
  // Source already filtered server-side via the query.
  const items = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rawItems.filter((a) => {
      if (!passesStatus(a, status)) return false;
      if (severity !== null && a.severity !== severity) return false;
      if (needle === "") return true;
      return (
        a.title.toLowerCase().includes(needle) ||
        (a.body ?? "").toLowerCase().includes(needle) ||
        a.id.toLowerCase().includes(needle)
      );
    });
  }, [rawItems, status, severity, q]);

  // Counts per tree node. Status counts come from the server payload;
  // source / severity counts derive from the rawItems list under the
  // current status filter (which gives intuitive scoped counts —
  // "Critical alerts in New" vs all-time).
  const statusCount = (s: StatusFilter): number => {
    if (!counts) return 0;
    if (s === "actionable") return counts.actionable;
    return counts[s] ?? 0;
  };
  const sourceCount = (src: AlertSource): number =>
    rawItems.filter((a) => passesStatus(a, status) && a.source === src).length;
  const severityCount = (sev: AlertSeverity): number =>
    rawItems.filter((a) => passesStatus(a, status) && a.severity === sev).length;

  const [dispositionTarget, setDispositionTarget] = useState<{
    alert: Alert;
    action: DispositionAction;
  } | null>(null);
  const [matchTarget, setMatchTarget] = useState<Alert | null>(null);

  // Title changes with the matter-link filter so the surface reads as
  // what it actually is right now — a matcher when Unattached is set,
  // an audit view otherwise. Differentiates from the raw /matters
  // Signals tab which shows promoted-signal Decisions.
  const title =
    matterLink === "unattached"
      ? "Unmatched signals"
      : matterLink === "attached"
        ? "Matched signals"
        : "Signal matcher";

  const subtitle = (() => {
    const total = items.length;
    const statusLabel =
      STATUS_OPTIONS.find((s) => s.value === status)?.label ?? "All";
    // When status is the open/actionable queue, surface the severity
    // breakdown so the user can read the queue's shape at a glance.
    const sevBits: string[] = [];
    for (const sev of SEVERITY_OPTIONS) {
      if (severity !== null && severity !== sev.value) continue;
      const n = items.filter((a) => a.severity === sev.value).length;
      if (n > 0) sevBits.push(`${n} ${sev.label.toLowerCase()}`);
    }
    const head = `${total} ${statusLabel.toLowerCase()}`;
    return sevBits.length > 0 ? `${head} · ${sevBits.join(" · ")}` : head;
  })();

  return (
    <AppShellV2>
      <SplitView
        left={
          <SignalsTree
            status={status}
            source={source}
            severity={severity}
            matterLink={matterLink}
            q={q}
            unattachedCount={counts?.unattached ?? 0}
            statusCount={statusCount}
            sourceCount={sourceCount}
            severityCount={severityCount}
            onStatusChange={setStatus}
            onSourceChange={setSource}
            onSeverityChange={setSeverity}
            onMatterLinkChange={setMatterLink}
            onQChange={setQ}
          />
        }
      >
        <DetailContainer
          title={title}
          subtitle={subtitle}
          actions={null}
        >
          <div className="px-6 py-5">
            <div className="rounded-md border-[0.5px] border-rule-soft bg-paper">
              {alertsQuery.isLoading && (
                <div className="p-6 text-body-sm text-ink-muted">
                  Loading signals…
                </div>
              )}
              {alertsQuery.isSuccess && items.length === 0 && (
                <div className="p-6 text-body-sm text-ink-muted">
                  No signals match this filter. Dismissed and promoted
                  signals stay reconstructable on the ledger.
                </div>
              )}
              {items.map((a, i) => (
                <AlertRow
                  key={a.id}
                  alert={a}
                  isFirst={i === 0}
                  onPromote={() =>
                    setDispositionTarget({ alert: a, action: "promote" })
                  }
                  onDismiss={() =>
                    setDispositionTarget({ alert: a, action: "dismiss" })
                  }
                  onHold={() =>
                    setDispositionTarget({ alert: a, action: "hold" })
                  }
                  onMatch={() => setMatchTarget(a)}
                  onInspectMatter={(id) =>
                    void navigate({ to: "/matters", search: { id } })
                  }
                  onOpenCaseFile={(id) =>
                    void navigate({
                      to: "/matters",
                      search: { id, mode: "case-file" },
                    })
                  }
                />
              ))}
            </div>
          </div>
        </DetailContainer>
      </SplitView>

      {dispositionTarget && (
        <DispositionDrawer
          alert={dispositionTarget.alert}
          action={dispositionTarget.action}
          onClose={() => setDispositionTarget(null)}
        />
      )}

      {matchTarget && (
        <MatchToMatterModal
          alert={matchTarget}
          onClose={() => setMatchTarget(null)}
          onMatched={() => setMatchTarget(null)}
        />
      )}
    </AppShellV2>
  );
}

/* ─── Signals tree ────────────────────────────────────────────────── */

const STATUS_DOT: Partial<
  Record<StatusFilter, "flag" | "amber" | "green" | "muted">
> = {
  actionable: "flag",
  triaged: "amber",
  promoted: "green",
  dismissed: "muted",
};

function SignalsTree({
  status,
  source,
  severity,
  matterLink,
  q,
  unattachedCount,
  statusCount,
  sourceCount,
  severityCount,
  onStatusChange,
  onSourceChange,
  onSeverityChange,
  onMatterLinkChange,
  onQChange,
}: {
  status: StatusFilter;
  source: AlertSource | null;
  severity: AlertSeverity | null;
  matterLink: MatterLinkFilter | null;
  q: string;
  unattachedCount: number;
  statusCount: (s: StatusFilter) => number;
  sourceCount: (s: AlertSource) => number;
  severityCount: (s: AlertSeverity) => number;
  onStatusChange: (s: StatusFilter) => void;
  onSourceChange: (s: AlertSource | null) => void;
  onSeverityChange: (s: AlertSeverity | null) => void;
  onMatterLinkChange: (s: MatterLinkFilter | null) => void;
  onQChange: (v: string) => void;
}) {
  return (
    <LeftTree>
      <LeftTree.Search
        placeholder="Search signals…"
        value={q}
        onChange={onQChange}
      />
      <LeftTree.Body>
        <LeftTree.Section title="Match state">
          <LeftTree.Node
            level={1}
            dot="flag"
            selected={matterLink === "unattached"}
            count={unattachedCount}
            onClick={() =>
              onMatterLinkChange(
                matterLink === "unattached" ? null : "unattached",
              )
            }
          >
            Unmatched
          </LeftTree.Node>
          <LeftTree.Node
            level={1}
            selected={matterLink === "attached"}
            onClick={() =>
              onMatterLinkChange(
                matterLink === "attached" ? null : "attached",
              )
            }
          >
            Matched
          </LeftTree.Node>
        </LeftTree.Section>

        <LeftTree.Section
          title={<HelpTerm term="disposition">Status</HelpTerm>}
        >
          {STATUS_OPTIONS.map((opt) => (
            <LeftTree.Node
              key={opt.value}
              level={1}
              selected={status === opt.value}
              count={statusCount(opt.value)}
              dot={STATUS_DOT[opt.value]}
              onClick={() => onStatusChange(opt.value)}
            >
              {opt.label}
            </LeftTree.Node>
          ))}
        </LeftTree.Section>

        <LeftTree.Section
          title={<HelpTerm term="signal">Source</HelpTerm>}
        >
          {SOURCE_OPTIONS.map((opt) => (
            <LeftTree.Node
              key={opt.value}
              level={1}
              selected={source === opt.value}
              count={sourceCount(opt.value)}
              onClick={() =>
                onSourceChange(source === opt.value ? null : opt.value)
              }
            >
              {opt.label}
            </LeftTree.Node>
          ))}
        </LeftTree.Section>

        <LeftTree.Section title="Severity">
          {SEVERITY_OPTIONS.map((opt) => (
            <LeftTree.Node
              key={opt.value}
              level={1}
              selected={severity === opt.value}
              count={severityCount(opt.value)}
              onClick={() =>
                onSeverityChange(severity === opt.value ? null : opt.value)
              }
            >
              {opt.label}
            </LeftTree.Node>
          ))}
        </LeftTree.Section>
      </LeftTree.Body>
    </LeftTree>
  );
}

/* ─── Row ────────────────────────────────────────────────────────────────── */

function AlertRow({
  alert,
  isFirst,
  onPromote,
  onDismiss,
  onHold,
  onMatch,
  onInspectMatter,
  onOpenCaseFile,
}: {
  alert: Alert;
  isFirst: boolean;
  onPromote: () => void;
  onDismiss: () => void;
  onHold: () => void;
  onMatch: () => void;
  onInspectMatter: (matterId: string) => void;
  onOpenCaseFile: (matterId: string) => void;
}) {
  const isUnattached = !alert.matter_id;
  const severityClass =
    alert.severity === "critical"
      ? "border-l-flag"
      : alert.severity === "high"
        ? "border-l-amber-600"
        : "border-l-slate-400";

  return (
    <div
      className={cn(
        "flex items-start gap-4 border-t-[0.5px] border-rule-faint border-l-[3px] px-4 py-4",
        isFirst && "border-t-0",
        severityClass,
      )}
    >
      <SeverityBadge severity={alert.severity} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2.5 flex-wrap">
          <SourceBadge source={alert.source} />
          <span className="text-body font-medium text-brand-ink">{alert.title}</span>
        </div>
        {alert.body && (
          <p className="mt-1.5 text-body-sm text-ink-soft">{alert.body}</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11.5px] text-ink-muted">
          <span>AL-{alert.id.slice(0, 8).toUpperCase()}</span>
          <span aria-hidden>·</span>
          <span>{timeSince(alert.detected_at)}</span>
          {alert.matter_id && (
            <>
              <span aria-hidden>·</span>
              {/* Read-only deep-links to the matter this signal lives on.
                  The inspector lets the triager scan tiers + decisions
                  alongside the signal; the case file is the export-ready
                  formal record for hand-off. Disposition stays the last
                  step in the row — read first, act second. */}
              <button
                type="button"
                onClick={() => onInspectMatter(alert.matter_id!)}
                className="text-brand hover:underline"
              >
                Inspect matter →
              </button>
              <button
                type="button"
                onClick={() => onOpenCaseFile(alert.matter_id!)}
                className="text-brand hover:underline"
              >
                Open case file →
              </button>
            </>
          )}
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-stretch gap-2 sm:flex-row">
        {isUnattached ? (
          <Button compact onClick={onMatch}>
            Match to matter
          </Button>
        ) : (
          <>
            <Button compact onClick={onPromote}>
              Promote to review
            </Button>
            <Button compact variant="ghost" onClick={onDismiss}>
              Dismiss
            </Button>
            <Button compact variant="ghost" onClick={onHold}>
              Hold
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function SeverityBadge({ severity }: { severity: Alert["severity"] }) {
  const map: Record<Alert["severity"], { label: string; cls: string }> = {
    critical: { label: "CRITICAL", cls: "bg-flag/10 text-flag" },
    high: { label: "HIGH", cls: "bg-amber-100 text-amber-800" },
    medium: { label: "MEDIUM", cls: "bg-slate-200 text-slate-700" },
    low: { label: "LOW", cls: "bg-slate-100 text-slate-600" },
  };
  const { label, cls } = map[severity];
  return (
    <span
      className={cn(
        "mt-0.5 shrink-0 rounded-sm px-2 py-0.5 font-mono text-[11px] font-semibold",
        cls,
      )}
    >
      {label}
    </span>
  );
}

function SourceBadge({ source }: { source: AlertSource }) {
  const map: Record<AlertSource, { label: string; cls: string }> = {
    fraud_risk_screening: { label: "Fraud-risk screening", cls: "bg-tier-federal/10 text-tier-federal" },
    flow_graph: { label: "Flow graph", cls: "bg-tier-contractor/10 text-tier-contractor" },
    identity: { label: "Identity", cls: "bg-tier-state/10 text-tier-state" },
  };
  const { label, cls } = map[source];
  return (
    <span className={cn("rounded-sm px-2 py-0.5 font-mono text-[11px]", cls)}>
      {label}
    </span>
  );
}

/* ─── Helpers ────────────────────────────────────────────────────────────── */

function timeSince(iso: string): string {
  try {
    return `${formatDistanceToNow(parseISO(iso))} ago`;
  } catch {
    return iso;
  }
}
