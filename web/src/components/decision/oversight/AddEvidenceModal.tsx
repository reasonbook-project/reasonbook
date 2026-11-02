// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import type { Decision } from "@/api/decisions";
import type { EvidenceRole } from "@/api/oversight";
import { Button } from "@/components/ds/Button";
import { WorkflowChip } from "@/components/ds/WorkflowChip";
import { useDecisions } from "@/hooks/useDecisions";
import { useCreateApexEvidence } from "@/hooks/useOversight";
import { useWorkflows } from "@/hooks/useWorkflows";
import { OVERSIGHT_WORKFLOW_ID } from "@/lib/oversight";
import { cn } from "@/lib/cn";

/**
 * Apex evidence search modal per apex spec §4.3.
 *
 * Lists operational decisions from the user's entitled workflows (apex
 * itself is filtered out — apex decisions never serve as evidence for
 * other apex decisions). Already-linked decisions are filtered. The
 * staleness threshold (365 days) flags older decisions; the operational
 * status flags decisions that aren't yet decided.
 */

const ROLE_OPTIONS: { id: EvidenceRole; label: string }[] = [
  { id: "primary_evidence", label: "Primary" },
  { id: "supporting_evidence", label: "Supporting" },
  { id: "risk_concentration_evidence", label: "Risk concentration" },
  { id: "regulatory_alignment_evidence", label: "Regulatory alignment" },
  { id: "outcome_evidence", label: "Outcome" },
  { id: "counter_evidence", label: "Counter-evidence" },
];

const STALENESS_DAYS = 365;

function isStale(decidedAt: string | null): boolean {
  if (!decidedAt) return false;
  const ageMs = Date.now() - new Date(decidedAt).getTime();
  return ageMs > STALENESS_DAYS * 24 * 60 * 60 * 1000;
}

export function AddEvidenceModal({
  oversightDecisionId,
  alreadyLinkedOperationalIds,
  onClose,
}: {
  oversightDecisionId: string;
  alreadyLinkedOperationalIds: string[];
  onClose: () => void;
}) {
  const workflowsQuery = useWorkflows();
  // Pull a generous page of decisions; client-side search filters down.
  const decisionsQuery = useDecisions({
    scope: "all_entitled",
    density: "all",
    limit: 200,
    sort: "newest",
  });
  const createEvidence = useCreateApexEvidence();

  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [role, setRole] = useState<EvidenceRole>("primary_evidence");
  const [rationale, setRationale] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const workflowLookup = useMemo(() => {
    const map: Record<string, { name: string; color: string }> = {};
    for (const w of workflowsQuery.data?.workflows ?? []) {
      map[w.id] = { name: w.name, color: w.color ?? "#94a3b8" };
    }
    return map;
  }, [workflowsQuery.data?.workflows]);

  const linkedSet = useMemo(
    () => new Set(alreadyLinkedOperationalIds),
    [alreadyLinkedOperationalIds],
  );

  const candidates = useMemo<Decision[]>(() => {
    const items = decisionsQuery.data?.items ?? [];
    const q = query.trim().toLowerCase();
    return items.filter((d) => {
      if (d.workflow_id === OVERSIGHT_WORKFLOW_ID) return false;
      if (linkedSet.has(d.id)) return false;
      if (!q) return true;
      return (
        d.title.toLowerCase().includes(q) ||
        d.decision_number.toLowerCase().includes(q)
      );
    });
  }, [decisionsQuery.data?.items, linkedSet, query]);

  const selected = useMemo(
    () => candidates.find((d) => d.id === selectedId) ?? null,
    [candidates, selectedId],
  );

  // Esc closes.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  const submit = () => {
    if (!selected) return;
    setSubmitError(null);
    createEvidence.mutate(
      {
        oversightDecisionId,
        body: {
          operational_decision_id: selected.id,
          evidence_role: role,
          rationale: rationale.trim() || undefined,
        },
      },
      {
        onSuccess: () => onClose(),
        onError: (err) => {
          if (err instanceof ApiError) {
            const body = err.body as { error?: string } | null;
            setSubmitError(body?.error ?? `Failed (${err.status})`);
          } else {
            setSubmitError("Failed to link evidence");
          }
        },
      },
    );
  };

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className="fixed inset-0 z-40 bg-ink/30"
      />
      <div
        role="dialog"
        aria-modal
        aria-label="Add evidence"
        className="fixed left-1/2 top-[8vh] z-50 flex max-h-[84vh] w-[640px] -translate-x-1/2 flex-col rounded-lg border border-rule-soft bg-paper shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-rule-soft px-6 py-4">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
              Apex evidence
            </div>
            <h2 className="mt-1 text-[18px] font-semibold leading-tight text-ink tracking-tight">
              Link an operational decision
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-faint hover:text-ink"
          >
            ×
          </button>
        </header>

        <div className="border-b border-rule-soft px-6 py-3">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by title or decision ID…"
            className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
            autoFocus
          />
        </div>

        <div className="flex-1 overflow-y-auto">
          {decisionsQuery.isLoading ? (
            <p className="px-6 py-4 text-body-sm text-ink-muted">
              Loading decisions…
            </p>
          ) : candidates.length === 0 ? (
            <p className="px-6 py-4 text-body-sm italic text-ink-muted">
              {query
                ? "No decisions match that search."
                : "No unlinked operational decisions available."}
            </p>
          ) : (
            <ul className="divide-y-[0.5px] divide-border">
              {candidates.map((d) => (
                <CandidateRow
                  key={d.id}
                  decision={d}
                  workflow={workflowLookup[d.workflow_id]}
                  selected={selectedId === d.id}
                  onSelect={() => setSelectedId(d.id)}
                />
              ))}
            </ul>
          )}
        </div>

        {selected && (
          <div className="border-t border-rule-soft bg-bg-warm/40 px-6 py-4">
            <div className="text-[12px] text-ink-soft">
              Linking{" "}
              <span className="font-mono text-ink">
                {selected.decision_number}
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-4">
              <label className="block">
                <span className="text-[11px] font-medium uppercase tracking-tracked text-ink-soft">
                  Evidence role
                </span>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as EvidenceRole)}
                  className="mt-1 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body-sm focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="text-[11px] font-medium uppercase tracking-tracked text-ink-soft">
                  Rationale (optional)
                </span>
                <input
                  type="text"
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  placeholder="Why this is evidence for this decision…"
                  className="mt-1 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body-sm focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
                />
              </label>
            </div>
            {submitError && (
              <p className="mt-3 text-body-sm text-critical-text">{submitError}</p>
            )}
          </div>
        )}

        <footer className="flex items-center justify-end gap-3 border-t border-rule-soft px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={submit}
            disabled={!selected || createEvidence.isPending}
          >
            {createEvidence.isPending ? "Linking…" : "Link evidence"}
          </Button>
        </footer>
      </div>
    </>
  );
}

function CandidateRow({
  decision,
  workflow,
  selected,
  onSelect,
}: {
  decision: Decision;
  workflow: { name: string; color: string } | undefined;
  selected: boolean;
  onSelect: () => void;
}) {
  const stale = isStale(decision.decided_at);
  const open = decision.status !== "decided" && decision.status !== "closed";
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "block w-full px-6 py-3 text-left transition-colors hover:bg-navy-tint/40",
          selected && "bg-navy-tint/60",
        )}
      >
        <div className="flex items-center gap-2">
          {workflow && <WorkflowChip name={workflow.name} color={workflow.color} />}
          <span className="font-mono text-[11px] text-ink-faint">
            {decision.decision_number}
          </span>
          {open && (
            <span className="rounded-sm bg-amber-50 px-1.5 py-px text-[10px] font-medium uppercase tracking-tracked text-amber-700">
              Open
            </span>
          )}
          {stale && (
            <span className="rounded-sm bg-rule-faint px-1.5 py-px text-[10px] font-medium uppercase tracking-tracked text-ink-faint">
              {">365 days"}
            </span>
          )}
        </div>
        <div className="mt-1 text-body-sm leading-snug text-ink">
          {decision.title}
        </div>
      </button>
    </li>
  );
}
