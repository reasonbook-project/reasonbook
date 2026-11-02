// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, redirect, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { InspectorBody } from "@/components/matters/InspectorBody";
import { ReassignMatterModal } from "@/components/matters/ReassignMatterModal";
import { Button } from "@/components/ds/Button";
import { VerifyChainButton } from "@/components/integrity/VerifyChainButton";
import { useMatter } from "@/hooks/useMatters";
import { useDecision } from "@/hooks/useDecisions";
import { usePrograms } from "@/hooks/usePrograms";

import { rootRoute } from "./__root";

/**
 * Matter page — unified container for create, review, and existing states.
 *
 * Per docs/architecture/fedRAMP/TENANCY-MODEL.md §11, the matter is the
 * aggregate root that spans federal → state → contractor. This page is the
 * one surface where matter activity happens. Same shell, state-driven
 * content:
 *
 *   DRAFT     → builder cards (form inputs), primary action = Create matter
 *   EXISTING  → cards read-only, primary action = Open originating decision
 *   CLOSED    → ledger-heavy read view, primary action = Export matter
 *
 * For the prototype the real `matters` table doesn't exist yet, so
 * we treat the federal Decision's id AS the matter id (synthetic 1:1).
 * When the real model arrives, this hook swaps to `useMatter(matterId)`
 * and the federal decision is fetched as the matter's root node — the
 * shell remains; only the data source changes.
 */
export const matterDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/awards/$matterId",
  // Legacy /awards/<id> standalone case file. Now redirects to the
  // unified /matters surface in case-file mode. MatterCaseFileBody
  // stays exported because /matters embeds it as the case-file
  // mode body.
  beforeLoad: ({ params }) => {
    throw redirect({
      to: "/matters",
      search: { id: params.matterId, mode: "case-file" },
      replace: true,
    });
  },
  component: MatterDetailRoute,
});

/** Never rendered — beforeLoad fires the redirect. Kept so the route
 *  registration retains a component for the type system. */
function MatterDetailRoute() {
  return null;
}

/**
 * MatterCaseFileBody — the formal 6-section case file for a matter.
 *
 * Two render contexts:
 *  - standalone (default): rendered by /awards/<matterId>; includes
 *    the principle banner, the page header with Export + Verify chain
 *    buttons, and the document body.
 *  - embedded (hideChrome=true): rendered inside the /matters detail
 *    tab strip; the DetailContainer provides title/subtitle/actions,
 *    so we render only the document body and skip the chrome.
 *
 * Same data source, same sections, no behavioral fork. Just chrome.
 */
export function MatterCaseFileBody({
  matterId,
  hideChrome = false,
  expandedDecisionId = null,
  onExpandDecision,
}: {
  matterId: string;
  hideChrome?: boolean;
  /** When set, that decision in § 4 renders as the expanded composite
   *  card; everything else stays collapsed. */
  expandedDecisionId?: string | null;
  /** Called when a decision row is clicked (open) or the expanded
   *  card's close button (collapse — pass null). Consumers respond by
   *  updating the URL search param. */
  onExpandDecision?: (decisionId: string | null) => void;
}) {
  const navigate = useNavigate();

  // Deep-link scroll: when the case file lands with a decision to
  // expand, scroll the row into view. Runs on mount and whenever the
  // param changes. Small delay lets the composite card mount and lay
  // out before we measure.
  useEffect(() => {
    if (!expandedDecisionId) return;
    const timer = window.setTimeout(() => {
      const el = document.getElementById(`dec-${expandedDecisionId}`);
      el?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 60);
    return () => window.clearTimeout(timer);
  }, [expandedDecisionId, matterId]);

  const [reassignOpen, setReassignOpen] = useState(false);

  // Prefer the real matter aggregate when the route param is a matter
  // id. Fall back to the legacy decision-as-matter proxy (used by
  // existing Inbox links that route by Decision.id) when the matter
  // lookup 404s. TanStack Query treats 404 as an error; we don't
  // retry — the fallback uses useDecision directly with the same id.
  const matterQuery = useMatter(matterId);
  const useLegacyProxy = matterQuery.isError;
  const decisionQuery = useDecision(matterId);
  const programsQuery = usePrograms();

  const matter = matterQuery.data;
  const decision = decisionQuery.data;

  if (matterQuery.isLoading || (useLegacyProxy && decisionQuery.isLoading)) {
    return (
      <div className="px-7 py-7 text-body-sm text-ink-muted">Loading matter…</div>
    );
  }
  // Both data sources failed → render an error.
  if (!matter && (!useLegacyProxy || !decision)) {
    return (
      <div className="px-7 py-7">
        <p className="text-body text-critical-text">Couldn't load this matter.</p>
        <button
          type="button"
          onClick={() => void navigate({ to: "/inbox" })}
          className="mt-3 text-body-sm text-brand hover:underline"
        >
          Back to Inbox
        </button>
      </div>
    );
  }

  // Resolve display values from whichever data source is present.
  const programId = matter?.program_id ?? decision?.workflow_id ?? "";
  const programLookup = programsQuery.data?.programs.find((p) => p.id === programId);
  const programLabel =
    programLookup?.display_name ??
    programLookup?.name ??
    humanizeProgramId(programId);

  // Standalone-header title + subtitle. Suppressed when embedded via
  // the DetailContainer (hideChrome=true), which provides its own
  // eyebrow/title/subtitle chrome.
  const headerTitle = matter
    ? `${matter.awarding_agency} · ${programLabel} · ${matter.period_label ?? ""}`
    : `${programLabel} · ${decision?.decision_number ?? ""}`;
  const headerSubtitle = matter
    ? `Matter ${matter.id.slice(0, 8)} · ${matter.federal_archetype} · ${
        matter.amount_obligated
          ? `$${Number(matter.amount_obligated).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
          : "—"
      } obligated`
    : `${programLabel} · ${decision?.decision_number ?? ""}`;

  return (
    <div className={hideChrome ? "" : "min-h-full bg-bg"}>
      {/* PRINCIPLE BANNER — forensic dark, on every state.
          Suppressed when embedded; DetailContainer handles its own
          chrome and the integrity story sits in §0 below. */}
      {!hideChrome && <PrincipleBanner />}

      <div className={hideChrome ? "px-6 py-6" : "px-7 py-6"}>
        {/* Page header. Suppressed when embedded — the DetailContainer's
            title/subtitle/actions provide the equivalent affordances. */}
        {!hideChrome && (
          <header className="mb-5 flex items-start justify-between gap-6">
            <div>
              <p className="mb-1 font-mono text-[10px] uppercase tracking-[0.1em] text-ink-faint">
                Matter case file · formal record of a federal-award matter
              </p>
              <h1 className="text-[26px] font-semibold tracking-[-0.02em] text-brand-ink">
                {headerTitle}
              </h1>
              <p className="mt-1 text-body-sm text-ink-soft">
                {headerSubtitle}
              </p>
            </div>
            <div className="flex items-start gap-3">
              {matter && (
                <Button
                  variant="ghost"
                  onClick={() => setReassignOpen(true)}
                >
                  <i className="ti ti-user-share text-[16px]" />
                  Reassign
                </Button>
              )}
              {matter && (
                <Button
                  variant="ghost"
                  onClick={() =>
                    window.open(
                      `/api/matters/${matter.id}/case-file`,
                      "_blank",
                      "noopener,noreferrer",
                    )
                  }
                >
                  <i className="ti ti-file-export text-[16px]" />
                  Export case file
                </Button>
              )}
              <VerifyChainButton />
            </div>
          </header>
        )}
        {matter && (
          <ReassignMatterModal
            open={reassignOpen}
            onClose={() => setReassignOpen(false)}
            matter={matter}
          />
        )}

        {/* Two-lane Inspector body — see docs/demo/mockups/case-file-option-c.html */}
        {matter && (
          <InspectorBody
            matter={matter}
            expandedDecisionId={expandedDecisionId}
            onExpandDecision={onExpandDecision}
          />
        )}

        {/* Legacy decision-as-matter proxy — minimal copy for old
            inbox links that hit this route by decision id. */}
        {!matter && decision && (
          <div className="px-6 py-6">
            <div className="rounded-md border-[0.5px] border-rule-soft bg-paper p-5">
              <p className="text-body-sm text-ink-soft">
                This decision (
                <span className="font-mono">{decision.decision_number}</span>)
                isn't matter-anchored yet. The full matter case file becomes
                available once it's promoted into an award matter.
              </p>
              <button
                type="button"
                onClick={() =>
                  void navigate({
                    to: "/workflows/$workflowId/decisions/$decisionId",
                    params: {
                      workflowId: decision.workflow_id,
                      decisionId: decision.id,
                    },
                  })
                }
                className="mt-3 inline-flex items-center gap-1.5 rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-1.5 text-body-sm hover:bg-ink/[0.04]"
              >
                Open decision detail →
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


/* ─── Principle banner ──────────────────────────────────────────────────── */

function PrincipleBanner() {
  return (
    <div className="mx-7 mt-6 flex flex-wrap items-center justify-between gap-3 rounded-md border-[0.5px] border-rule-dark bg-forensic px-5 py-3 font-mono text-[12px] text-ink-inv">
      <span>
        <span className="font-medium text-white">PRINCIPLE</span>
        <span className="mx-2 text-ink-inv-2">·</span>
        Accountability follows the dollar.
      </span>
      <span>
        <span className="text-ink-inv-2">↓ dollars flow down the chain</span>
        <span className="mx-2 text-ink-inv-2">·</span>
        <span className="text-cleared">↑ every decision flows back, on the record</span>
      </span>
    </div>
  );
}

/* ─── Helpers ───────────────────────────────────────────────────────────── */

function humanizeProgramId(programId: string): string {
  const parts = programId.split("-");
  return parts
    .map((p, i) => {
      if (p.length <= 3 && /^[a-z]+$/.test(p)) return p.toUpperCase();
      if (/\d/.test(p)) return p.toUpperCase();
      return i === 0 ? p[0].toUpperCase() + p.slice(1) : p;
    })
    .join(" ");
}

