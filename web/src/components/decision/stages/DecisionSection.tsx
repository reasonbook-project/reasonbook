// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";
import { useState, type ComponentType } from "react";

import type { Decision } from "@/api/decisions";
import type { WorkflowAction } from "@/api/workflows";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ds/Button";
import { AnatomyStageSection } from "@/components/ds/AnatomyStageSection";
import { AttachmentsBlock } from "@/components/decision/AttachmentsBlock";
import { CommentsBlock } from "@/components/decision/CommentsBlock";
import { GenericEvidenceView } from "@/components/decision/generic/EvidenceView";
import { HelpLink } from "@/components/help/HelpLink";
import { usePatchDecisionStage } from "@/hooks/useDecisions";
import { canEditStage } from "@/lib/stageEditability";
import { type EvidenceViewProps } from "@/workflows";

/**
 * Stage 3 — the Decision itself. Shows the chosen action, the rationale,
 * and the evidence that backs it. Workflow-specific EvidenceView slots in
 * here; the generic view is the fallback.
 *
 * Edit mode (Phase 7.5 Gate 5) covers selected_option / rationale; the
 * FinalizeForm handles the in_progress→decided transition itself.
 */
export function DecisionSection({
  decision,
  EvidenceView,
  finalizeSlot,
  availableActions,
  dimmed,
  isLast,
}: {
  decision: Decision;
  EvidenceView?: ComponentType<EvidenceViewProps>;
  /** Rendered when the decision is still in progress — the FinalizeForm. */
  finalizeSlot?: React.ReactNode;
  /** Workflow YAML's available_actions for this decision_type — used to
   *  resolve selected_option's id (e.g. 'file_sar') to the human-readable
   *  display name ('File SAR') when rendering the recorded decision. */
  availableActions?: WorkflowAction[];
  dimmed?: boolean;
  isLast?: boolean;
}) {
  const EvidenceImpl = EvidenceView ?? GenericEvidenceView;
  const decided = decision.decided_at
    ? format(parseISO(decision.decided_at), "MMM d, h:mm a")
    : null;
  const showFinalize = decision.status === "in_progress" && Boolean(finalizeSlot);

  const [editing, setEditing] = useState(false);
  const editable =
    canEditStage("decision", decision.status) && Boolean(decision.selected_option);

  return (
    <AnatomyStageSection
      stageNumber={3}
      stageName="DECISION"
      timestamp={decided ?? undefined}
      dimmed={dimmed}
      isLast={isLast}
      headerAccessory={
        editable && !editing ? (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="text-body-sm text-ink-muted hover:text-navy"
            >
              Edit
            </button>
            <HelpLink
              topic="decisions/edit-after-claim"
              variant="icon"
              ariaLabel="Help: editing a decision after claim"
            />
          </div>
        ) : null
      }
    >
      {editing ? (
        <DecisionEditForm
          decision={decision}
          onCancel={() => setEditing(false)}
          onSaved={() => setEditing(false)}
        />
      ) : decision.selected_option ? (
        <div className="space-y-4">
          <div>
            <div className="text-tracked uppercase text-ink-soft">
              Selected option
            </div>
            <div className="mt-1 text-body font-medium">
              {availableActions?.find((a) => a.id === decision.selected_option)
                ?.name ?? decision.selected_option}
            </div>
          </div>
          {decision.rationale && (
            <div>
              <div className="text-tracked uppercase text-ink-soft">
                Rationale
              </div>
              <p className="mt-1 text-body-sm leading-[1.55] text-ink">
                {decision.rationale}
              </p>
            </div>
          )}
          <div>
            <div className="text-tracked uppercase text-ink-soft">
              Evidence
            </div>
            <div className="mt-2">
              <EvidenceImpl decision={decision} />
            </div>
          </div>
          <AttachmentsBlock
            decisionId={decision.id}
            stage="evidence"
            label="Evidence files"
          />
          <CommentsBlock decisionId={decision.id} stageContext="decision" />
        </div>
      ) : showFinalize ? (
        <div className="space-y-4">
          {finalizeSlot}
          <AttachmentsBlock
            decisionId={decision.id}
            stage="evidence"
            label="Evidence files"
          />
          <CommentsBlock decisionId={decision.id} stageContext="decision" />
        </div>
      ) : (
        <p className="text-body-sm text-ink-muted">
          No decision recorded yet.
        </p>
      )}
    </AnatomyStageSection>
  );
}

function DecisionEditForm({
  decision,
  onCancel,
  onSaved,
}: {
  decision: Decision;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const patch = usePatchDecisionStage();
  const [selectedOption, setSelectedOption] = useState(
    decision.selected_option ?? "",
  );
  const [rationale, setRationale] = useState(decision.rationale ?? "");
  const [error, setError] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    patch.mutate(
      {
        decisionId: decision.id,
        body: {
          selected_option: selectedOption.trim(),
          rationale: rationale.trim(),
        },
      },
      {
        onSuccess: () => onSaved(),
        onError: (err) => {
          if (err instanceof ApiError) {
            const body = err.body as { error?: string } | null;
            setError(body?.error ?? `Failed (${err.status})`);
          } else {
            setError("Failed to save");
          }
        },
      },
    );
  };

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Selected option
        </span>
        <input
          type="text"
          value={selectedOption}
          onChange={(e) => setSelectedOption(e.target.value)}
          className="mt-2 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        />
      </label>
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Rationale
        </span>
        <textarea
          value={rationale}
          onChange={(e) => setRationale(e.target.value)}
          rows={5}
          className="mt-2 w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body leading-relaxed focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        />
      </label>
      {error && (
        <div role="alert" className="text-body-sm text-critical-text">
          {error}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button type="submit" compact disabled={patch.isPending}>
          {patch.isPending ? "Saving…" : "Save"}
        </Button>
        <Button type="button" variant="ghost" compact onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
