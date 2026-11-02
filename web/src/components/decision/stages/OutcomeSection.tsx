// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";
import { useState } from "react";

import type { Decision } from "@/api/decisions";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ds/Button";
import { AnatomyStageSection } from "@/components/ds/AnatomyStageSection";
import { AttachmentsBlock } from "@/components/decision/AttachmentsBlock";
import { CommentsBlock } from "@/components/decision/CommentsBlock";
import { useRecordOutcome, usePatchOutcome } from "@/hooks/useDecisions";
import { canEditStage } from "@/lib/stageEditability";

const IMPACT_OPTIONS = [
  { value: "", label: "(none)" },
  { value: "positive", label: "Positive" },
  { value: "neutral", label: "Neutral" },
  { value: "negative", label: "Negative" },
] as const;

type Impact = "positive" | "neutral" | "negative";

/**
 * Stage 5 — Outcome. Closes the loop: what happened after the action?
 * outcome_text is the narrative; outcome_impact tags the result; metrics
 * carry numeric follow-up where the workflow defines them.
 *
 * First-time outcome capture (status='decided') uses POST /outcome to also
 * close the decision; post-hoc edits on a closed decision use PATCH.
 */
export function OutcomeSection({
  decision,
  dimmed,
  isLast,
}: {
  decision: Decision;
  dimmed?: boolean;
  isLast?: boolean;
}) {
  const recorded = decision.outcome_recorded_at
    ? format(parseISO(decision.outcome_recorded_at), "MMM d, h:mm a")
    : undefined;
  return (
    <AnatomyStageSection
      stageNumber={5}
      stageName="OUTCOME"
      timestamp={recorded}
      dimmed={dimmed}
      isLast={isLast}
    >
      <OutcomeStageBody decision={decision} />
    </AnatomyStageSection>
  );
}

/**
 * Body-only variant of stage 5 — no AnatomyStageSection wrapper.
 * Used by DecisionRecordCard. The Edit / Record affordance lives
 * inline at the top of the body so both consumers render the same
 * content.
 */
export function OutcomeStageBody({ decision }: { decision: Decision }) {
  const hasOutcome = Boolean(decision.outcome_text || decision.outcome_impact);

  const [editing, setEditing] = useState(false);
  const canRecord = decision.status === "decided" && !hasOutcome;
  const canEdit = canEditStage("outcome", decision.status) && hasOutcome;
  const editable = canRecord || canEdit;

  if (editing) {
    return (
      <OutcomeEditForm
        decision={decision}
        mode={hasOutcome ? "patch" : "record"}
        onCancel={() => setEditing(false)}
        onSaved={() => setEditing(false)}
      />
    );
  }

  const editTrigger =
    editable && !editing ? (
      <div className="flex justify-end">
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="text-body-sm text-ink-muted hover:text-navy"
        >
          {hasOutcome ? "Edit" : "Record"}
        </button>
      </div>
    ) : null;

  if (!hasOutcome) {
    return (
      <div className="space-y-3">
        {editTrigger}
        <p className="text-body-sm text-ink-muted">
          Outcome not yet captured.
        </p>
        {decision.status === "closed" && (
          <>
            <AttachmentsBlock decisionId={decision.id} stage="outcome" />
            <CommentsBlock decisionId={decision.id} stageContext="outcome" />
          </>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {editTrigger}
      {decision.outcome_impact && (
        <div className="flex items-center gap-2">
          <span
            className={
              decision.outcome_impact === "positive"
                ? "rounded-sm bg-resolved-bg px-2 py-px text-[11px] font-medium uppercase tracking-tracked text-resolved-text"
                : decision.outcome_impact === "negative"
                  ? "rounded-sm bg-critical-bg px-2 py-px text-[11px] font-medium uppercase tracking-tracked text-critical-text"
                  : "rounded-sm bg-rule-faint px-2 py-px text-[11px] font-medium uppercase tracking-tracked text-ink-soft"
            }
          >
            {decision.outcome_impact}
          </span>
        </div>
      )}
      {decision.outcome_text && (
        <p className="text-body-sm leading-[1.55] text-ink">
          {decision.outcome_text}
        </p>
      )}
      {decision.outcome_metrics &&
        Object.keys(decision.outcome_metrics).length > 0 && (
          <dl className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-2 text-body-sm">
            {Object.entries(decision.outcome_metrics).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-tracked uppercase text-ink-soft">
                  {k}
                </dt>
                <dd className="font-mono text-ink">
                  {typeof v === "number" || typeof v === "string"
                    ? String(v)
                    : JSON.stringify(v)}
                </dd>
              </div>
            ))}
          </dl>
        )}
      <AttachmentsBlock decisionId={decision.id} stage="outcome" />
      <CommentsBlock decisionId={decision.id} stageContext="outcome" />
    </div>
  );
}

function OutcomeEditForm({
  decision,
  mode,
  onCancel,
  onSaved,
}: {
  decision: Decision;
  /** "record" = first capture (POST, transitions to closed); "patch" = edit. */
  mode: "record" | "patch";
  onCancel: () => void;
  onSaved: () => void;
}) {
  const recordMutation = useRecordOutcome();
  const patchMutation = usePatchOutcome();
  const mutation = mode === "record" ? recordMutation : patchMutation;

  const [text, setText] = useState(decision.outcome_text ?? "");
  const [impact, setImpact] = useState<Impact | "">(
    (decision.outcome_impact as Impact) ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const onError = (err: unknown) => {
      if (err instanceof ApiError) {
        const body = err.body as { error?: string } | null;
        setError(body?.error ?? `Failed (${err.status})`);
      } else {
        setError("Failed to save");
      }
    };
    if (mode === "record") {
      if (!text.trim()) {
        setError("Outcome text is required.");
        return;
      }
      recordMutation.mutate(
        {
          decisionId: decision.id,
          body: {
            outcome_text: text.trim(),
            outcome_impact: impact || undefined,
          },
        },
        { onSuccess: () => onSaved(), onError },
      );
    } else {
      patchMutation.mutate(
        {
          decisionId: decision.id,
          body: {
            outcome_text: text.trim(),
            outcome_impact: impact || undefined,
          },
        },
        { onSuccess: () => onSaved(), onError },
      );
    }
  };

  return (
    <form onSubmit={handleSave} className="space-y-3">
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Outcome
        </span>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          required={mode === "record"}
          placeholder="What happened after the action ran?"
          className="mt-2 w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body leading-relaxed focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        />
      </label>
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Impact
        </span>
        <select
          value={impact}
          onChange={(e) => setImpact(e.target.value as Impact | "")}
          className="mt-2 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        >
          {IMPACT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      {error && (
        <div role="alert" className="text-body-sm text-critical-text">
          {error}
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button type="submit" compact disabled={mutation.isPending}>
          {mutation.isPending
            ? "Saving…"
            : mode === "record"
              ? "Record outcome"
              : "Save"}
        </Button>
        <Button type="button" variant="ghost" compact onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
