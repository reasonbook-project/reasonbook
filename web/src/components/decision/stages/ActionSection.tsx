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
import { usePatchAction } from "@/hooks/useDecisions";
import { canEditStage } from "@/lib/stageEditability";

/**
 * Stage 4 — Action. Records the operational follow-through: when the action
 * started, when it completed, what artifacts attach (signed PDF, FinCEN
 * receipt, etc.).
 *
 * Edit mode (Phase 7.5 Gate 5) lets owners record or correct the started/
 * completed timestamps via PATCH; artifact mutation is workflow-shaped and
 * stays out of v1 inline edit.
 */
export function ActionSection({
  decision,
  dimmed,
  isLast,
}: {
  decision: Decision;
  dimmed?: boolean;
  isLast?: boolean;
}) {
  const timestamp = decision.action_completed_at ?? decision.action_started_at;
  const stamp = timestamp
    ? format(parseISO(timestamp), "MMM d, h:mm a")
    : undefined;
  return (
    <AnatomyStageSection
      stageNumber={4}
      stageName="ACTION"
      timestamp={stamp}
      dimmed={dimmed}
      isLast={isLast}
    >
      <ActionStageBody decision={decision} />
    </AnatomyStageSection>
  );
}

/**
 * Body-only variant of stage 4 — no AnatomyStageSection wrapper.
 * Used by DecisionRecordCard, which supplies its own stage-header
 * chrome. The Edit / Record affordance lives inline at the top of
 * the body rather than in the section header so both consumers
 * render the same content.
 */
export function ActionStageBody({ decision }: { decision: Decision }) {
  const started = decision.action_started_at
    ? format(parseISO(decision.action_started_at), "MMM d, h:mm a")
    : null;
  const completed = decision.action_completed_at
    ? format(parseISO(decision.action_completed_at), "MMM d, h:mm a")
    : null;

  const [editing, setEditing] = useState(false);
  const editable = canEditStage("action", decision.status);

  if (editing) {
    return (
      <ActionEditForm
        decision={decision}
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
          {started || completed ? "Edit" : "Record"}
        </button>
      </div>
    ) : null;

  if (!started && !completed) {
    return (
      <div className="space-y-3">
        {editTrigger}
        <p className="text-body-sm text-ink-muted">
          Action not yet started.
        </p>
        {editable && (
          <AttachmentsBlock decisionId={decision.id} stage="action" />
        )}
        {editable && (
          <CommentsBlock decisionId={decision.id} stageContext="action" />
        )}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      {editTrigger}
      {started && (
        <div className="flex gap-3 text-body-sm">
          <span className="w-[160px] text-tracked uppercase text-ink-soft">
            Started
          </span>
          <span className="font-mono text-ink">{started}</span>
        </div>
      )}
      {completed && (
        <div className="flex gap-3 text-body-sm">
          <span className="w-[160px] text-tracked uppercase text-ink-soft">
            Completed
          </span>
          <span className="font-mono text-ink">{completed}</span>
        </div>
      )}
      {Array.isArray(decision.action_artifacts) &&
        decision.action_artifacts.length > 0 && (
          <div>
            <div className="text-tracked uppercase text-ink-soft">
              Artifacts
            </div>
            <ul className="mt-2 space-y-1 text-body-sm">
              {decision.action_artifacts.map((artifact, idx) => (
                <li
                  key={idx}
                  className="font-mono text-[11px] text-ink"
                >
                  {JSON.stringify(artifact)}
                </li>
              ))}
            </ul>
          </div>
        )}
      <AttachmentsBlock decisionId={decision.id} stage="action" />
      <CommentsBlock decisionId={decision.id} stageContext="action" />
    </div>
  );
}

function toLocalInputValue(iso: string | null): string {
  // <input type="datetime-local"> needs YYYY-MM-DDTHH:mm in local time —
  // not ISO with a Z. We slice the ISO of a local Date.
  if (!iso) return "";
  const d = parseISO(iso);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function fromLocalInputValue(value: string): string | undefined {
  if (!value) return undefined;
  // Date constructor reads the local-time string and we get an ISO with TZ.
  return new Date(value).toISOString();
}

function ActionEditForm({
  decision,
  onCancel,
  onSaved,
}: {
  decision: Decision;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const patch = usePatchAction();
  const [started, setStarted] = useState(toLocalInputValue(decision.action_started_at));
  const [completed, setCompleted] = useState(
    toLocalInputValue(decision.action_completed_at),
  );
  const [error, setError] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    patch.mutate(
      {
        decisionId: decision.id,
        body: {
          action_started_at: fromLocalInputValue(started),
          action_completed_at: fromLocalInputValue(completed),
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
    <form onSubmit={handleSave} className="space-y-3">
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Started
        </span>
        <input
          type="datetime-local"
          value={started}
          onChange={(e) => setStarted(e.target.value)}
          className="mt-2 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
        />
      </label>
      <label className="block">
        <span className="text-tracked uppercase text-ink-soft">
          Completed
        </span>
        <input
          type="datetime-local"
          value={completed}
          onChange={(e) => setCompleted(e.target.value)}
          className="mt-2 w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
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
