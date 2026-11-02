// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import type { MatterDecision } from "@/api/matters";
import type { Decision } from "@/api/decisions";
import {
  OversightBreadcrumb,
  DecisionDetailHeader,
  FederalBreadcrumb,
  OperationalBreadcrumb,
} from "@/components/ds/DecisionDetailHeader";
import { OversightDecisionHeader } from "@/components/ds/OversightDecisionHeader";
import { EvidenceSection } from "@/components/decision/oversight/EvidenceSection";
import { CommentsBlock } from "@/components/decision/CommentsBlock";
import { DecisionRecordCard } from "@/components/decision/DecisionRecordCard";
import { FinalizeForm } from "@/components/decision/FinalizeForm";
import { ActionSection } from "@/components/decision/stages/ActionSection";
import { CommitteeStage } from "@/components/decision/stages/CommitteeStage";
import { DecisionSection } from "@/components/decision/stages/DecisionSection";
import { OutcomeSection } from "@/components/decision/stages/OutcomeSection";
import { OwnerSection } from "@/components/decision/stages/OwnerSection";
import { SignalSection } from "@/components/decision/stages/SignalSection";
import { ExportButton } from "@/components/ds/ExportButton";
import { HelpLink } from "@/components/help/HelpLink";
import { useArchetypes } from "@/hooks/useArchetypes";
import { useOversightCycles } from "@/hooks/useOversight";
import { usePrograms } from "@/hooks/usePrograms";
import { useUsers } from "@/hooks/useUsers";
import { useDecision } from "@/hooks/useDecisions";
import { useWorkflowConfig, useWorkflows } from "@/hooks/useWorkflows";
import { oversightTagline, isOversightDecision } from "@/lib/oversight";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { useAuthStore } from "@/stores/auth";
import { workflowExtensions } from "@/workflows";

import { MatterTree } from "./matters";
import { rootRoute } from "./__root";

/**
 * Shell wrap so this route renders with the unified top nav + the
 * same left-side MatterTree the /matters case-file view uses. Two
 * entry paths, same chrome — the reader who lands here from a deep
 * link, an inbox click, or a notification gets the same browsing
 * affordances the /matters surface offers.
 *
 * The tree's `selectedId` binds to the decision's matter_id
 * when set; clicking a matter navigates over to /matters with that
 * matter selected. Matter-less decisions (grant-debarment adverse
 * actions etc.) render with the tree present but no selection —
 * the reader can still switch to browsing without leaving the shell.
 */
function DecisionDetailPageShell() {
  const navigate = useNavigate();
  const [treeQ, setTreeQ] = useState("");
  const { decisionId } = decisionDetailRoute.useParams();
  const decisionQuery = useDecision(decisionId);
  const selectedMatterId = decisionQuery.data?.matter_id ?? null;
  // Decisions promoted from a Signal mint `PI-*` decision numbers;
  // regular decisions mint `DEC-*`. Reading that off the loaded
  // Decision lets the rail stay on the tab the reader came from —
  // Signals for a promoted signal, Matters for anything else. (Tab id
  // is `cases` from the pre-rename days; label reads "Signals".)
  const initialTab: "matters" | "cases" =
    decisionQuery.data?.decision_number?.startsWith("PI-")
      ? "cases"
      : "matters";

  // Defer MatterTree mount until the Decision resolves — MatterTree
  // snapshots initialTab on first render (via userTab-null → initialTab
  // fallback), so mounting before the Decision is loaded briefly
  // paints the wrong tab and flickers into place. Skeleton the rail
  // for the ~50ms round-trip instead.
  const treeReady = decisionQuery.isSuccess || decisionQuery.isError;

  return (
    <AppShellV2>
      <SplitView
        left={
          treeReady ? (
            <MatterTree
              selectedId={selectedMatterId}
              onSelect={(id) =>
                void navigate({
                  to: "/matters",
                  search: { id, mode: "case-file" },
                })
              }
              q={treeQ}
              onQChange={setTreeQ}
              initialTab={initialTab}
            />
          ) : (
            <div className="h-full bg-paper" />
          )
        }
      >
        {/* SplitView's right pane is a flex column that clips overflow;
            the scroll container has to live one level inside so the
            composite card + comments block scroll instead of clipping. */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
          <DecisionDetailPage />
        </div>
      </SplitView>
    </AppShellV2>
  );
}

export const decisionDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workflows/$workflowId/decisions/$decisionId",
  component: DecisionDetailPageShell,
});

/**
 * Defensive fallback when the programs API doesn't know an id —
 * deterministic transform of "nih-r01" -> "NIH R01". Real lookups go
 * through `usePrograms()` and prefer the program's `display_name`
 * (or `name`).
 */
function humanizeProgramId(programId: string): string {
  const parts = programId.split("-");
  return parts
    .map((p, i) => {
      // NIH / NSF / etc. — short uppercase agency acronyms stay uppercase.
      if (p.length <= 3 && /^[a-z]+$/.test(p)) return p.toUpperCase();
      // Mixed alphanum tokens (r01, h1b) stay uppercase too.
      if (/\d/.test(p)) return p.toUpperCase();
      return i === 0 ? p[0].toUpperCase() + p.slice(1) : p;
    })
    .join(" ");
}

/**
 * The full Decision shape is a strict superset of MatterDecision minus
 * `is_originating` (a matter-scoped flag that has no meaning when the
 * decision is being viewed outside its matter). Synthesise the
 * MatterDecision the composite card expects.
 */
function toMatterDecisionShape(d: Decision): MatterDecision {
  return {
    id: d.id,
    decision_number: d.decision_number,
    decision_type: d.decision_type,
    status: d.status,
    title: d.title,
    priority: d.priority,
    created_at: d.created_at,
    decided_at: d.decided_at,
    selected_option: d.selected_option,
    outcome_text: d.outcome_text,
    is_originating: false,
    matter_node_id: d.matter_node_id,
    signal_source: d.signal_source,
    // Decision.evidence_refs is typed as unknown[] | null; the card
    // reads {kind, ref} entries and gracefully skips shapes it doesn't
    // recognise, so a cast is safe.
    evidence_refs: (d.evidence_refs as Array<{ kind: string; ref: string }> | null) ?? null,
  };
}

function DecisionDetailPage() {
  const { workflowId, decisionId } = decisionDetailRoute.useParams();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);

  const decisionQuery = useDecision(decisionId);
  const workflowsQuery = useWorkflows();
  const workflowConfigQuery = useWorkflowConfig(workflowId);
  const archetypesQuery = useArchetypes();
  const programsQuery = usePrograms();

  const decision = decisionQuery.data;
  const isOversight = isOversightDecision(decision);
  const archetype = useMemo(() => {
    if (!decision || isOversight) return undefined;
    return (archetypesQuery.data?.archetypes ?? []).find(
      (a) => a.id === decision.decision_type,
    );
  }, [decision, isOversight, archetypesQuery.data?.archetypes]);
  const isFederal = !!archetype;
  const cyclesQuery = useOversightCycles();
  const cyclesEnabled = isOversight;
  const cycle = useMemo(() => {
    if (!cyclesEnabled || !decision?.oversight_cycle_id) return null;
    return (
      cyclesQuery.data?.items.find((c) => c.id === decision.oversight_cycle_id) ?? null
    );
  }, [cyclesEnabled, cyclesQuery.data?.items, decision?.oversight_cycle_id]);

  const workflowSummary = useMemo(
    () => workflowsQuery.data?.workflows.find((w) => w.id === workflowId),
    [workflowId, workflowsQuery.data?.workflows],
  );

  // Owner lookup — the composite card renders the owner name inline and
  // the legacy oversight path still uses it in the Owner section.
  const usersQuery = useUsers({ status: "active" });
  const usersById = useMemo(
    () =>
      new Map((usersQuery.data?.items ?? []).map((u) => [u.id, u])),
    [usersQuery.data?.items],
  );

  const ext = workflowExtensions(workflowId);

  const decisionType = useMemo(() => {
    if (!decision) return undefined;
    return workflowConfigQuery.data?.decision_types.find(
      (t) => t.id === decision.decision_type,
    );
  }, [decision, workflowConfigQuery.data?.decision_types]);

  if (decisionQuery.isLoading) {
    return (
      <div className="px-7 py-7 text-body-sm text-ink-muted">
        Loading decision…
      </div>
    );
  }
  if (decisionQuery.isError || !decision) {
    return (
      <div className="px-7 py-7">
        <p className="text-body text-critical-text">
          Couldn't load this decision.
        </p>
        <button
          type="button"
          onClick={() => void navigate({ to: "/inbox" })}
          className="mt-3 text-body-sm text-navy hover:underline"
        >
          Back to Inbox
        </button>
      </div>
    );
  }

  const status = decision.status;
  const ownerName = decision.owner_id
    ? decision.owner_id === user?.id
      ? user?.name
      : (usersById.get(decision.owner_id)?.name ?? null)
    : null;

  const headerTimestamps = [
    decision.created_at && `Opened ${new Date(decision.created_at).toLocaleDateString()}`,
    decision.sla_deadline &&
      `Due ${new Date(decision.sla_deadline).toLocaleDateString()}`,
  ]
    .filter(Boolean)
    .join(" · ");

  const headerRightSlot = (
    <div className="flex items-center gap-3">
      <ExportButton
        variant={isOversight ? "primary" : "outlined"}
        label={isOversight ? "Export examiner record" : "Export PDF"}
        onClick={() => {
          window.open(
            `/api/decisions/${decision.id}/export`,
            "_blank",
            "noopener,noreferrer",
          );
        }}
      />
      <HelpLink
        topic="decisions/export-record"
        variant="icon"
        ariaLabel="Help: exporting a decision record"
      />
    </div>
  );

  const header = isOversight ? (
    <OversightDecisionHeader
      breadcrumb={<OversightBreadcrumb cycleName={cycle?.name} />}
      title={decision.title}
      italicTagline={oversightTagline(decision, cycle) ?? undefined}
      decisionId={decision.decision_number}
      timestamps={headerTimestamps}
      rightSlot={headerRightSlot}
    />
  ) : isFederal ? (
    <DecisionDetailHeader
      variant="operational"
      breadcrumb={
        <FederalBreadcrumb
          archetypeName={archetype?.name}
          programName={
            programsQuery.data?.programs.find(
              (p) => p.id === decision.workflow_id,
            )?.display_name ??
            programsQuery.data?.programs.find(
              (p) => p.id === decision.workflow_id,
            )?.name ??
            humanizeProgramId(decision.workflow_id)
          }
          matterId={decision.matter_id}
        />
      }
      title={decision.title}
      decisionId={decision.decision_number}
      timestamps={headerTimestamps}
      rightSlot={headerRightSlot}
    />
  ) : (
    <DecisionDetailHeader
      variant="operational"
      breadcrumb={
        workflowSummary ? (
          <OperationalBreadcrumb
            workflowName={workflowSummary.name}
            workflowColor={workflowSummary.color ?? "#94a3b8"}
          />
        ) : (
          <span>Inbox</span>
        )
      }
      title={decision.title}
      decisionId={decision.decision_number}
      timestamps={headerTimestamps}
      rightSlot={headerRightSlot}
    />
  );

  // Oversight decisions keep the legacy stage anatomy for now — they
  // have an extra Committee stage that the composite card doesn't
  // model yet. Everything else (federal + operational) gets the
  // composite card treatment so the visual matches the /matters case
  // file.
  if (isOversight) {
    const isActiveOwner = status === "open" || status === "assigned";
    const isActiveDecision = status === "in_progress";
    const isActiveAction = status === "decided" && !decision.action_completed_at;
    const isActiveOutcome =
      !!decision.action_completed_at && !decision.outcome_recorded_at;
    const dimmedOwner = !decision.owner_id && !isActiveOwner;
    const dimmedDecision = !decision.selected_option && !isActiveDecision;
    const dimmedAction =
      !decision.action_started_at &&
      !decision.action_completed_at &&
      !isActiveAction;
    const dimmedOutcome = !decision.outcome_recorded_at && !isActiveOutcome;

    return (
      <div className="pb-12">
        {header}
        <div className="border-b-[0.5px] border-rule-soft bg-paper">
          <SignalSection decision={decision} PayloadView={ext.PayloadView} />
          <OwnerSection
            decision={decision}
            ownerName={ownerName}
            dimmed={dimmedOwner}
          />
          <DecisionSection
            decision={decision}
            EvidenceView={ext.EvidenceView}
            availableActions={decisionType?.available_actions ?? []}
            finalizeSlot={
              decision.owner_id === user?.id && status === "in_progress" ? (
                <FinalizeForm
                  decision={decision}
                  availableActions={decisionType?.available_actions ?? []}
                />
              ) : null
            }
            dimmed={dimmedDecision}
          />
          <CommitteeStage
            decision={decision}
            dimmed={status === "open" || status === "assigned"}
          />
          <ActionSection decision={decision} dimmed={dimmedAction} />
          <OutcomeSection
            decision={decision}
            dimmed={dimmedOutcome}
            isLast={false}
          />
          <EvidenceSection oversightDecisionId={decision.id} />
        </div>
        <div className="mt-6 px-5">
          <CommentsBlock
            decisionId={decision.id}
            stageContext="general"
            label="Discussion"
          />
        </div>
      </div>
    );
  }

  // Composite-card layout for federal + operational decisions. Matches
  // the /matters case-file rendering so the two entry points look
  // identical.
  const matterShaped = toMatterDecisionShape(decision);

  return (
    <div className="pb-12">
      {header}
      <div className="px-7 py-6">
        <div className="max-w-[880px] lg:max-w-[1080px] 2xl:max-w-[1280px]">
          <DecisionRecordCard
            decision={matterShaped}
            workflowId={workflowId}
            ownerName={ownerName}
            ownerClaimedAt={decision.assigned_at}
          />
          <div className="mt-8">
            <CommentsBlock
              decisionId={decision.id}
              stageContext="general"
              label="Discussion"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
