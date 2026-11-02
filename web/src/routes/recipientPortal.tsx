// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { formatDistanceToNow, parseISO } from "date-fns";
import { useMemo } from "react";

import type { MatterSummary } from "@/api/matters";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { EmptyState } from "@/components/ds/EmptyState";
import { LeftTree } from "@/components/ds/LeftTree";
import { SkeletonRows } from "@/components/ds/Skeleton";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { useMatters, useRfrs } from "@/hooks/useMatters";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";

/**
 * Recipient portal — first-class work surface for external-party
 * response state (mockup: docs/demo/mockups/recipient-response-form.html,
 * spec §7.2). Two audiences share the same route:
 *
 *   · Federal officers monitor the pending-response workload — what's
 *     out with parties and when responses are due.
 *   · External-party users (Phase B, once real auth lands) see only
 *     matters entitled to their party, and respond via the form.
 *
 * Rail copy is written neutrally ("Awaiting responses") so both
 * audiences read cleanly. Party scoping is a session-level filter
 * applied server-side in Phase B — A0 is unscoped.
 *
 * A0 workarounds (see backlog/awaiting-recipient-stage-band.md):
 *   · Rendered inside AppShellV2 (real RecipientPortalShell in B.3).
 *   · "Awaiting" synthesized from is_commitment=false; real filtering
 *     comes from the requests_for_response table (B.1).
 *   · No party scope on the caller — every logged-in user sees every
 *     matter; B.3 adds PartyEntitlement scope.
 */
export const recipientPortalRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/recipient",
  component: RecipientPortalPage,
});

function RecipientPortalPage() {
  const navigate = useNavigate();
  const mattersQuery = useMatters();
  // Real filter: a matter is "awaiting" iff it has an open RFR. A0's
  // synthesized version (no-commitment-yet) stays as fallback for the
  // window between B.1 landing and demo data catching up.
  const rfrsQuery = useRfrs({ status: "open" });

  const { awaiting, submitted } = useMemo(() => {
    const items = mattersQuery.data?.items ?? [];
    const rfrItems = rfrsQuery.data?.items ?? [];
    const mattersWithOpenRfr = new Set(rfrItems.map((r) => r.matter_id));
    const s: MatterSummary[] = [];
    const a: MatterSummary[] = [];
    for (const m of items) {
      if ((m.commitment_count ?? 0) > 0) s.push(m);
      if (mattersWithOpenRfr.has(m.id)) a.push(m);
    }
    return { awaiting: a, submitted: s };
  }, [mattersQuery.data?.items, rfrsQuery.data?.items]);

  return (
    <AppShellV2>
      <SplitView
        left={
          <LeftTree>
            <LeftTree.Search placeholder="Filter matters…" />
            <LeftTree.Body>
              <LeftTree.Section title="Party responses">
                <LeftTree.Node level={1} count={awaiting.length} dot="amber">
                  Awaiting responses
                </LeftTree.Node>
                <LeftTree.Node
                  level={1}
                  count={submitted.length}
                  dot="green"
                >
                  Recently submitted
                </LeftTree.Node>
                <LeftTree.Node level={1} count={0} dot="muted">
                  Superseded
                </LeftTree.Node>
              </LeftTree.Section>
            </LeftTree.Body>
          </LeftTree>
        }
      >
        <DetailContainer
          title="Recipient portal"
          subtitle="Party responses · what's pending across matters"
        >
          <div className="space-y-8 px-6 py-6">
            {mattersQuery.isLoading && <SkeletonRows />}
            {mattersQuery.isError && (
              <EmptyState
                headline="We couldn't load matters."
                body={<>Refresh to try again.</>}
              />
            )}
            {mattersQuery.isSuccess && (
              <>
                <WatchlistBand
                  label="Awaiting responses"
                  help="Matters with an open Request-For-Response"
                  count={awaiting.length}
                  rows={awaiting}
                  onSelect={(m) =>
                    void navigate({
                      to: "/matters/$matterId/response",
                      params: { matterId: m.id },
                    })
                  }
                  emptyText="Nothing awaiting a response."
                  variant="awaiting"
                />
                <WatchlistBand
                  label="Recently submitted"
                  help="Commitments already recorded in the federal ledger"
                  count={submitted.length}
                  rows={submitted}
                  onSelect={(m) =>
                    void navigate({
                      to: "/matters",
                      search: { id: m.id, mode: "case-file" },
                    })
                  }
                  emptyText="No commitments submitted yet."
                  variant="submitted"
                />
              </>
            )}
          </div>
        </DetailContainer>
      </SplitView>
    </AppShellV2>
  );
}

function WatchlistBand({
  label,
  help,
  count,
  rows,
  onSelect,
  emptyText,
  variant,
}: {
  label: string;
  help: string;
  count: number;
  rows: MatterSummary[];
  onSelect: (m: MatterSummary) => void;
  emptyText: string;
  variant: "awaiting" | "submitted";
}) {
  const accent =
    variant === "awaiting" ? "text-amber" : "text-ok";
  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between border-b-[0.5px] border-rule-soft pb-2">
        <div className="flex items-baseline gap-3">
          <span
            className={cn(
              "font-display text-[14px] font-medium",
              accent,
            )}
          >
            {label}
          </span>
          <span className="font-mono text-[11px] text-ink-faint">
            {count}
          </span>
        </div>
        <span className="text-[12px] text-ink-muted">{help}</span>
      </div>
      {rows.length === 0 && (
        <p className="text-[13px] text-ink-muted italic">{emptyText}</p>
      )}
      <div className="space-y-2">
        {rows.map((m) => (
          <WatchlistRow
            key={m.id}
            matter={m}
            onSelect={() => onSelect(m)}
            variant={variant}
          />
        ))}
      </div>
    </section>
  );
}

function WatchlistRow({
  matter,
  onSelect,
  variant,
}: {
  matter: MatterSummary;
  onSelect: () => void;
  variant: "awaiting" | "submitted";
}) {
  // "Who owes the response" — deepest named node in the fund flow.
  // Prefer the recipient tier from path_preview; fall back to
  // search_labels (which carries every recipient display_name on the
  // matter) for direct-federal-to-recipient rows where the backend's
  // path preview bails without a state tier.
  const recipientFromPath = matter.path_preview.find(
    (p) => p.tier === "recipient",
  );
  const recipientFromLabels =
    (matter.search_labels ?? [])
      .filter((s) => s && s !== matter.awarding_agency)
      .slice(-1)[0] ?? null;
  const responder =
    recipientFromPath?.label ?? recipientFromLabels ?? null;
  const title = responder
    ? `${responder} · ${matter.program_id.toUpperCase()}`
    : `${matter.program_id.toUpperCase()} · no named recipient yet`;

  // Fund-flow trail — federal › state › recipient. Shown as small
  // meta below the title so it's clear WHERE the response lives.
  const trail = matter.path_preview.map((p) => p.label);
  // If a search_labels recipient wasn't in path_preview, append it
  // so the trail reads federal → recipient for direct-payment rows.
  if (recipientFromLabels && !trail.includes(recipientFromLabels)) {
    trail.push(recipientFromLabels);
  }

  const submittedAgo =
    matter.created_at &&
    variant === "submitted" &&
    formatDistanceToNow(parseISO(matter.created_at), { addSuffix: true });
  return (
    <button
      type="button"
      onClick={onSelect}
      className="flex w-full items-center gap-4 rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3 text-left hover:border-rule"
    >
      <div className="min-w-0 flex-1">
        <div className="font-display text-[14px] font-medium text-ink">
          {title}
        </div>
        {trail.length > 0 && (
          <div className="mt-0.5 flex flex-wrap items-center gap-1 text-[12px]">
            {trail.map((label, i) => (
              <span key={`${label}-${i}`} className="flex items-center gap-1">
                {i > 0 && (
                  <span aria-hidden className="text-ink-faint">
                    ›
                  </span>
                )}
                <span
                  className={cn(
                    i === trail.length - 1 ? "text-ink" : "text-ink-soft",
                  )}
                >
                  {label}
                </span>
              </span>
            ))}
          </div>
        )}
        {matter.period_label && (
          <div className="mt-1 font-mono text-[11px] text-ink-faint uppercase tracking-wider">
            {matter.period_label}
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        {variant === "awaiting" && (
          <span className="inline-flex items-center gap-1.5 rounded-full border-[0.5px] border-amber/40 bg-amber-soft px-2.5 py-0.5 font-display text-[11px] font-medium text-amber">
            <i className="ti ti-arrow-right text-[12px]" aria-hidden />
            Respond
          </span>
        )}
        {variant === "submitted" && (
          <div className="text-[12px]">
            <span className="inline-flex items-center gap-1.5 rounded-full border-[0.5px] border-ok/40 bg-ok-soft px-2.5 py-0.5 font-display text-[11px] font-medium text-ok">
              <i className="ti ti-check text-[12px]" aria-hidden />
              {matter.commitment_count} on record
            </span>
            {submittedAgo && (
              <div className="mt-1 font-mono text-[11px] text-ink-faint">
                {submittedAgo}
              </div>
            )}
          </div>
        )}
      </div>
    </button>
  );
}
