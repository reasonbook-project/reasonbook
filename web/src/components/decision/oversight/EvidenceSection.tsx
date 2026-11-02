// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";

import type { ApexEvidenceLink, EvidenceRole } from "@/api/oversight";
import { Button } from "@/components/ds/Button";
import { WorkflowChip } from "@/components/ds/WorkflowChip";
import { useOversightEvidence, useSupersedeApexEvidence } from "@/hooks/useOversight";
import { useWorkflows } from "@/hooks/useWorkflows";
import { cn } from "@/lib/cn";

import { AddEvidenceModal } from "./AddEvidenceModal";

/**
 * Apex Decision Detail — Evidence section per apex spec §4.3 + §8.1.
 *
 * Renders below the five-stage anatomy on apex decisions only. Linked
 * operational decisions group by role; each row shows the workflow chip,
 * decision ID, title, decided date, and the executive's rationale. The
 * "Mark superseded" button writes a supersede event without losing the
 * audit trail (apex spec §4.1).
 */

const ROLE_ORDER: { id: EvidenceRole; label: string; description: string }[] = [
  {
    id: "primary_evidence",
    label: "Primary",
    description: "Central data point supporting the apex decision.",
  },
  {
    id: "supporting_evidence",
    label: "Supporting",
    description: "Corroborates or expands on the primary evidence.",
  },
  {
    id: "risk_concentration_evidence",
    label: "Risk concentration",
    description: "Documents a risk pattern relevant to the apex decision.",
  },
  {
    id: "regulatory_alignment_evidence",
    label: "Regulatory alignment",
    description: "Documents regulatory positioning relevant to the apex decision.",
  },
  {
    id: "outcome_evidence",
    label: "Outcome",
    description: "Realized outcome of an earlier strategic direction.",
  },
  {
    id: "counter_evidence",
    label: "Counter-evidence",
    description: "Data that complicates or qualifies the apex decision.",
  },
];

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function EvidenceSection({
  oversightDecisionId,
}: {
  oversightDecisionId: string;
}) {
  const evidenceQuery = useOversightEvidence(oversightDecisionId);
  const workflowsQuery = useWorkflows();
  const [adding, setAdding] = useState(false);

  const workflowLookup = useMemo(() => {
    const map: Record<string, { name: string; color: string }> = {};
    for (const w of workflowsQuery.data?.workflows ?? []) {
      map[w.id] = { name: w.name, color: w.color ?? "#94a3b8" };
    }
    return map;
  }, [workflowsQuery.data?.workflows]);

  const grouped = useMemo(() => {
    const buckets: Record<EvidenceRole, ApexEvidenceLink[]> = {
      primary_evidence: [],
      supporting_evidence: [],
      risk_concentration_evidence: [],
      regulatory_alignment_evidence: [],
      outcome_evidence: [],
      counter_evidence: [],
    };
    for (const link of evidenceQuery.data?.items ?? []) {
      buckets[link.evidence_role]?.push(link);
    }
    return buckets;
  }, [evidenceQuery.data?.items]);

  const totalCount = evidenceQuery.data?.items.length ?? 0;
  const linkedOperationalIds = useMemo(
    () =>
      (evidenceQuery.data?.items ?? [])
        .map((l) => l.operational_decision_id),
    [evidenceQuery.data?.items],
  );

  return (
    <section className="border-b-[0.5px] border-rule-soft bg-paper px-5 py-[18px]">
      <header className="flex items-center gap-3">
        <span className="text-tracked font-medium uppercase text-ink-soft">
          Evidence
        </span>
        <span aria-hidden className="h-px flex-1 bg-rule-soft" />
        <span className="text-[11px] text-ink-faint">
          {totalCount} linked
        </span>
        <Button
          variant="ghost"
          compact
          onClick={() => setAdding(true)}
          aria-label="Add evidence"
        >
          + Add evidence
        </Button>
      </header>

      {evidenceQuery.isLoading ? (
        <p className="mt-3 text-body-sm text-ink-muted">Loading evidence…</p>
      ) : totalCount === 0 ? (
        <p className="mt-3 text-body-sm italic text-ink-muted">
          No operational evidence linked yet. Strong apex decisions cite
          decisions across at least two operational workflows.
        </p>
      ) : (
        <div className="mt-4 space-y-5">
          {ROLE_ORDER.map((role) => {
            const links = grouped[role.id] ?? [];
            if (links.length === 0) return null;
            return (
              <div key={role.id}>
                <div className="flex items-baseline justify-between">
                  <h4 className="text-[13px] font-medium text-ink">
                    {role.label}
                  </h4>
                  <span className="text-[11px] text-ink-faint">
                    {links.length} {links.length === 1 ? "link" : "links"}
                  </span>
                </div>
                <ul className="mt-2 divide-y-[0.5px] divide-border">
                  {links.map((link) => (
                    <EvidenceRow
                      key={link.id}
                      link={link}
                      oversightDecisionId={oversightDecisionId}
                      workflow={
                        link.operational
                          ? workflowLookup[link.operational.workflow_id]
                          : undefined
                      }
                    />
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      {adding && (
        <AddEvidenceModal
          oversightDecisionId={oversightDecisionId}
          alreadyLinkedOperationalIds={linkedOperationalIds}
          onClose={() => setAdding(false)}
        />
      )}
    </section>
  );
}

function EvidenceRow({
  link,
  oversightDecisionId,
  workflow,
}: {
  link: ApexEvidenceLink;
  oversightDecisionId: string;
  workflow: { name: string; color: string } | undefined;
}) {
  const supersede = useSupersedeApexEvidence(oversightDecisionId);
  const op = link.operational;
  const isOpen = op?.status && op.status !== "decided" && op.status !== "closed";

  return (
    <li className="py-3">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {workflow && <WorkflowChip name={workflow.name} color={workflow.color} />}
            {op?.decision_number && (
              <span className="font-mono text-[11px] text-ink-faint">
                {op.decision_number}
              </span>
            )}
            {isOpen && (
              <span
                className="rounded-sm bg-amber-50 px-1.5 py-px text-[10px] font-medium uppercase tracking-tracked text-amber-700"
                title="Operational decision is not yet decided; evidence may shift."
              >
                Open
              </span>
            )}
          </div>
          <div
            className={cn(
              "mt-1 text-body-sm leading-snug text-ink",
              !op && "italic text-ink-faint",
            )}
          >
            {op?.title ?? "Operational decision unavailable"}
          </div>
          {op?.decided_at && (
            <div className="mt-0.5 text-[11px] text-ink-faint">
              Decided {formatDate(op.decided_at)}
            </div>
          )}
          {link.link_rationale && (
            <p className="mt-1.5 text-body-sm italic text-ink-soft">
              "{link.link_rationale}"
            </p>
          )}
        </div>
        <div className="shrink-0">
          <Button
            variant="ghost"
            compact
            disabled={supersede.isPending}
            onClick={() => {
              if (
                !window.confirm(
                  "Mark this evidence link superseded? The audit trail is preserved.",
                )
              ) {
                return;
              }
              supersede.mutate({ linkId: link.id });
            }}
          >
            {supersede.isPending ? "…" : "Mark superseded"}
          </Button>
        </div>
      </div>
    </li>
  );
}
