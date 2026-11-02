// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";

import type { Alert } from "@/api/alerts";
import type { MatterSummary } from "@/api/matters";
import { Button } from "@/components/ds/Button";
import { useAttachAlertToMatter } from "@/hooks/useAlerts";
import { useMatters } from "@/hooks/useMatters";
import { cn } from "@/lib/cn";

/**
 * MatchToMatterModal — the /signals matcher's write path.
 *
 * An unattached alert (matter_id IS NULL) is a signal the detector
 * fired without knowing which matter it belongs to. The triager reads
 * the alert body, decides which matter is the right home, and clicks
 * to associate. Once attached, the alert shows up on that matter's
 * case-file where the existing in-place SignalActionCard takes over
 * for disposition.
 *
 * UX: text search (agency / program / recipient name / decision id),
 * narrowed matter list, click-to-attach with the alert body pinned at
 * the top for reference. Deliberately NOT a full matter drilldown —
 * that's what the /matters surface is for. This modal is a matcher,
 * not a matter browser.
 */
export function MatchToMatterModal({
  alert,
  onClose,
  onMatched,
}: {
  alert: Alert;
  onClose: () => void;
  onMatched?: () => void;
}) {
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<MatterSummary | null>(null);
  const mattersQuery = useMatters();
  const attach = useAttachAlertToMatter();

  const items = mattersQuery.data?.items ?? [];
  const filtered = useMemo(() => filterMatters(items, q), [items, q]);

  const submit = () => {
    if (!selected) return;
    attach.mutate(
      { alertId: alert.id, matterId: selected.id },
      {
        onSuccess: () => {
          onMatched?.();
        },
      },
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/30"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="match-modal-title"
        className="relative z-10 flex max-h-[82vh] w-[640px] flex-col rounded-md border-[0.5px] border-rule bg-paper"
      >
        <header className="border-b-[0.5px] border-rule-soft px-5 py-4">
          <div className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
            Match signal to matter
          </div>
          <h2
            id="match-modal-title"
            className="mt-1 text-[16px] font-medium text-brand-ink"
          >
            {alert.title}
          </h2>
          <p className="mt-1 font-mono text-[11.5px] text-ink-muted">
            AL-{alert.id.slice(0, 8).toUpperCase()} · severity {alert.severity}
          </p>
          {alert.body && (
            <p className="mt-2 text-body-sm text-ink-soft">{alert.body}</p>
          )}
        </header>

        <div className="border-b-[0.5px] border-rule-soft px-5 py-3">
          <input
            type="search"
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search matters — agency, program, recipient, decision id…"
            className="w-full rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {mattersQuery.isLoading && (
            <div className="px-5 py-6 text-body-sm text-ink-muted">
              Loading matters…
            </div>
          )}
          {mattersQuery.isSuccess && filtered.length === 0 && (
            <div className="px-5 py-6 text-body-sm text-ink-muted">
              No matters match this filter. Try broadening the search.
            </div>
          )}
          <ul>
            {filtered.slice(0, 40).map((m) => {
              const isSelected = selected?.id === m.id;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(m)}
                    className={cn(
                      "flex w-full items-baseline gap-3 border-b-[0.5px] border-rule-faint px-5 py-2.5 text-left transition-colors",
                      isSelected
                        ? "bg-navy-soft/30 border-l-2 border-l-navy pl-[18px]"
                        : "hover:bg-bg-warm",
                    )}
                  >
                    <span className="font-mono text-[11px] uppercase text-ink-faint">
                      {shortAgency(m.awarding_agency)} · {m.program_id.toUpperCase()}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-body-sm text-ink">
                      {matterLabel(m)}
                    </span>
                    <span className="font-mono text-[11px] text-ink-faint">
                      {formatExposure(m.amount_obligated)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <footer className="flex items-center justify-between border-t-[0.5px] border-rule-soft px-5 py-4">
          <span className="text-body-sm text-ink-muted">
            {selected ? (
              <>
                Attach to{" "}
                <span className="font-medium text-ink">
                  {matterLabel(selected)}
                </span>
                {" — "}
                the signal will show up on that matter's case-file for
                disposition.
              </>
            ) : (
              "Pick a matter to continue."
            )}
          </span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={!selected || attach.isPending}
            >
              {attach.isPending ? "Attaching…" : "Attach"}
            </Button>
          </div>
        </footer>

        {attach.isError && (
          <div className="border-t-[0.5px] border-flag/30 bg-flag/5 px-5 py-2 text-body-sm text-flag">
            {attach.error?.message || "Could not attach the signal."}
          </div>
        )}
      </div>
    </div>
  );
}

function filterMatters(items: MatterSummary[], q: string): MatterSummary[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((m) => {
    const hay = [
      m.awarding_agency,
      m.program_id,
      m.period_label ?? "",
      ...(m.search_labels ?? []),
      ...(m.search_terms ?? []),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(needle);
  });
}

function matterLabel(m: MatterSummary): string {
  const labels = (m.search_labels ?? []).filter(
    (s) => s && s !== m.awarding_agency,
  );
  if (labels.length > 0) return labels[labels.length - 1];
  return m.awarding_agency;
}

function shortAgency(name: string): string {
  const short: Record<string, string> = {
    "Department of Health and Human Services": "HHS",
    "Department of Agriculture": "USDA",
    "Department of Transportation": "DOT",
    "Department of Education": "ED",
    "Department of Defense": "DoD",
    "Department of Housing and Urban Development": "HUD",
  };
  return short[name] ?? name;
}

function formatExposure(v: string | number | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}
