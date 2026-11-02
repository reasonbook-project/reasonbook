// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import type { Dispute, DisputeResolution } from "@/api/registry";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { Button } from "@/components/ds/Button";
import { useDispute, useResolveDispute } from "@/hooks/useRegistry";
import { cn } from "@/lib/cn";

import { MatterTree } from "./matters";
import { rootRoute } from "./__root";

/**
 * /disputes/<id> — identity-resolution dispute detail.
 *
 * Two candidate identities side-by-side, evidence provenance, and
 * three resolution actions (same / different / manual override). MVP:
 * the resolve buttons are visual only; wiring them to a POST endpoint
 * is a follow-up. Reading the record + seeing the evidence trail is
 * the demo priority.
 */
export const disputeDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/disputes/$disputeId",
  component: DisputeDetailShell,
});

function DisputeDetailShell() {
  const navigate = useNavigate();
  const [treeQ, setTreeQ] = useState("");
  return (
    <AppShellV2>
      <SplitView
        left={
          <MatterTree
            selectedId={null}
            onSelect={(id) =>
              void navigate({
                to: "/matters",
                search: { id, mode: "case-file" },
              })
            }
            q={treeQ}
            onQChange={setTreeQ}
            initialTab="disputes"
          />
        }
      >
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
          <DisputeDetailPage />
        </div>
      </SplitView>
    </AppShellV2>
  );
}

function DisputeDetailPage() {
  const { disputeId } = disputeDetailRoute.useParams();
  const navigate = useNavigate();
  const disputeQuery = useDispute(disputeId);

  if (disputeQuery.isLoading || !disputeQuery.data) {
    return (
      <div className="px-7 py-7 text-body-sm text-ink-muted">
        Loading dispute…
      </div>
    );
  }
  if (disputeQuery.isError) {
    return (
      <div className="px-7 py-7">
        <p className="text-body text-critical-text">
          Couldn't load this dispute.
        </p>
        <button
          type="button"
          onClick={() => void navigate({ to: "/matters" })}
          className="mt-3 text-body-sm text-navy hover:underline"
        >
          Back
        </button>
      </div>
    );
  }

  const d = disputeQuery.data;
  const isOpen = d.status === "open";

  return (
    <div className="px-7 py-6">
      <div className="max-w-[880px] lg:max-w-[1080px] 2xl:max-w-[1280px]">
        {/* ── Header ──────────────────────────────────────────────── */}
        <div className="mb-2 font-mono text-[11px] uppercase tracking-[0.08em] text-ink-faint">
          <button
            type="button"
            onClick={() => void navigate({ to: "/matters" })}
            className="hover:underline text-brand"
          >
            Register
          </button>
          <span className="mx-1.5">›</span>
          <span>Disputes</span>
          <span className="mx-1.5">›</span>
          <span className="normal-case tracking-normal text-ink-soft">
            {d.subject_name}
          </span>
        </div>
        <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-brand-ink">
          {d.subject_name}
        </h1>
        <div className="mt-1 flex flex-wrap items-baseline gap-x-3 text-body-sm text-ink-soft">
          <StatusBadge status={d.status} />
          {d.opened_at && (
            <span>opened {formatDate(d.opened_at)}</span>
          )}
          {d.resolved_at && (
            <span>resolved {formatDate(d.resolved_at)}</span>
          )}
        </div>

        {/* ── The question ───────────────────────────────────────── */}
        <div className="mt-6 rounded-md bg-navy-soft px-4 py-3 font-display text-[15px] font-medium text-navy-deep">
          Are these two records the same entity?
        </div>

        {/* ── Candidates side-by-side ────────────────────────────── */}
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
          <CandidateCard label="Candidate A" record={d.candidate_a} />
          <CandidateCard label="Candidate B" record={d.candidate_b} />
        </div>

        {/* ── Notes ──────────────────────────────────────────────── */}
        {d.notes && (
          <div className="mt-6">
            <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
              Analyst notes
            </div>
            <p className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3 text-body-sm text-ink">
              {d.notes}
            </p>
          </div>
        )}

        {/* ── Resolution ─────────────────────────────────────────── */}
        {isOpen ? (
          <ResolveForm disputeId={d.id} />
        ) : (
          d.resolution_rationale && (
            <div className="mt-6 rounded-md border-[0.5px] border-cleared bg-cleared/10 px-4 py-3">
              <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.08em] text-cleared">
                Resolution
              </div>
              <p className="text-body-sm text-ink">
                {d.resolution_rationale}
              </p>
            </div>
          )
        )}
      </div>
    </div>
  );
}

/**
 * Resolve form — three action buttons + a rationale textarea. Clicking
 * one of the buttons mints a decided Decision on the server (via
 * /resolve) with selected_option set to the chosen resolution, then
 * navigates the reader to that Decision so the analyst sees the
 * record they just created walk into the case-file view.
 */
function ResolveForm({ disputeId }: { disputeId: string }) {
  const navigate = useNavigate();
  const [rationale, setRationale] = useState("");
  const [pending, setPending] = useState<DisputeResolution | null>(null);
  const resolve = useResolveDispute();

  const submit = (resolution: DisputeResolution) => {
    setPending(resolution);
    resolve.mutate(
      { disputeId, resolution, rationale },
      {
        onSuccess: (data) => {
          setPending(null);
          // If the dispute was linked to a matter, land on the matter's
          // case-file with the new Decision expanded in §4. Otherwise
          // fall through to the standalone decision route so the record
          // still has a home.
          if (data.decision_matter_id) {
            void navigate({
              to: "/matters",
              search: {
                id: data.decision_matter_id,
                mode: "case-file",
                decision: data.decision_id,
              },
            });
            return;
          }
          void navigate({
            to: "/workflows/$workflowId/decisions/$decisionId",
            params: {
              workflowId: data.decision_workflow_id,
              decisionId: data.decision_id,
            },
          });
        },
        onError: () => setPending(null),
      },
    );
  };

  return (
    <div className="mt-6">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
        Rationale — brief note on the record
      </div>
      <textarea
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
        rows={3}
        placeholder="Why this call? What evidence pins it down?"
        className={cn(
          "w-full rounded-md border-[0.5px] border-rule bg-paper",
          "px-3 py-2 text-body leading-[1.55] text-ink",
          "placeholder:text-ink-faint",
          "focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft",
        )}
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          onClick={() => submit("same_entity")}
          disabled={resolve.isPending}
        >
          {pending === "same_entity" ? "Recording…" : "Same entity"}
        </Button>
        <Button
          variant="ghost"
          onClick={() => submit("different_entities")}
          disabled={resolve.isPending}
        >
          {pending === "different_entities"
            ? "Recording…"
            : "Different entities"}
        </Button>
        <Button
          variant="ghost"
          onClick={() => submit("manual_override")}
          disabled={resolve.isPending}
        >
          {pending === "manual_override" ? "Recording…" : "Manual override"}
        </Button>
      </div>
      {resolve.isError && (
        <p className="mt-2 text-body-sm text-critical-text">
          Couldn't record the decision. Try again.
        </p>
      )}
      <p className="mt-2 text-[11.5px] italic text-ink-muted">
        Answering this records a Decision on the identity-review
        workflow. The Dispute closes and links back to the Decision;
        you'll land on the composite card next.
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: Dispute["status"] }) {
  const palette: Record<Dispute["status"], string> = {
    open: "bg-accent-warning/15 text-accent-warning border-accent-warning/30",
    resolved_same: "bg-cleared/10 text-cleared border-cleared/30",
    resolved_different: "bg-cleared/10 text-cleared border-cleared/30",
    manual_override: "bg-navy-soft text-navy-deep border-navy/30",
    withdrawn: "bg-bg-warm text-ink-soft border-rule-soft",
  };
  const label: Record<Dispute["status"], string> = {
    open: "OPEN",
    resolved_same: "RESOLVED · SAME",
    resolved_different: "RESOLVED · DIFFERENT",
    manual_override: "MANUAL OVERRIDE",
    withdrawn: "WITHDRAWN",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm border-[0.5px] px-2 py-0.5",
        "font-mono text-[10px] uppercase tracking-[0.08em] font-medium",
        palette[status],
      )}
    >
      {label[status]}
    </span>
  );
}

function CandidateCard({
  label,
  record,
}: {
  label: string;
  record: Record<string, unknown>;
}) {
  const source = (record["source"] as string | undefined) ?? "unknown";
  const entries = Object.entries(record).filter(([k]) => k !== "source");
  return (
    <div className="rounded-md border-[0.5px] border-rule bg-paper">
      <header className="flex items-baseline justify-between border-b-[0.5px] border-rule-soft px-4 py-2.5 bg-paper-warm/60">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] font-medium text-ink-soft">
          {label}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.06em] text-navy-deep">
          {source}
        </span>
      </header>
      <dl className="grid grid-cols-[130px_1fr] gap-x-4 gap-y-2 px-4 py-3 text-body-sm">
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
              {k.replace(/_/g, " ")}
            </dt>
            <dd className="text-ink">
              {typeof v === "string" || typeof v === "number" || typeof v === "boolean"
                ? String(v)
                : JSON.stringify(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}
