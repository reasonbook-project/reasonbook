// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";

import { ApiError } from "@/api/client";
import type { BoardAction } from "@/api/oversight";
import { Button } from "@/components/ds/Button";
import { useRecordBoardAction } from "@/hooks/useOversight";

type Choice = {
  id: BoardAction;
  label: string;
  description: string;
};

// Three primary committee actions per the oversight spec §6.2. The
// `_by_board` action ids are historical (carried forward from DG); new
// rows write the same ids so the audit trail stays interpretable.
// `ratified_by_committee` is reserved for a committee-chair-specific
// path; surfacing it alongside Ratify would clutter the matrix.
const CHOICES: Choice[] = [
  {
    id: "ratified_by_board",
    label: "Ratify",
    description: "Committee has reviewed the evidence and formally approves.",
  },
  {
    id: "noted_by_board",
    label: "Note",
    description:
      "Committee has reviewed the evidence; informational acknowledgement.",
  },
  {
    id: "deferred_to_next_cycle",
    label: "Defer to next cycle",
    description:
      "Wait. Reasons for deferral are recorded with the action.",
  },
];

/**
 * Matrix of committee actions an oversight persona can record against
 * an oversight decision. Posts via the oversight board-action endpoint;
 * the resulting `decision_events` row drives the populated state of
 * CommitteeStage.
 *
 * Authority is enforced server-side (403 → surfaced inline). The form
 * only renders for users with
 * `oversight_capabilities.can_record_committee_action`; see CommitteeStage.
 */
export function CommitteeActionForm({ decisionId }: { decisionId: string }) {
  const mutation = useRecordBoardAction(decisionId);
  const [selected, setSelected] = useState<BoardAction | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!selected) {
      setError("Pick an action.");
      return;
    }
    mutation.mutate(
      { action: selected, note: note.trim() || undefined },
      {
        onSuccess: () => {
          setSelected(null);
          setNote("");
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            const body = err.body as { error?: string } | null;
            setError(
              err.status === 403
                ? "You don't have authority to record a committee action."
                : body?.error ?? `Failed (${err.status})`,
            );
          } else {
            setError("Failed to record");
          }
        },
      },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <div>
        <div className="text-tracked uppercase text-ink-soft">
          Record committee action
        </div>
        <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
          {CHOICES.map((choice) => {
            const active = selected === choice.id;
            return (
              <button
                key={choice.id}
                type="button"
                onClick={() => setSelected(choice.id)}
                aria-pressed={active}
                className={[
                  "rounded-md border-[0.5px] px-3 py-3 text-left transition-colors",
                  active
                    ? "border-navy bg-navy-tint"
                    : "border-rule-soft bg-paper hover:border-rule",
                ].join(" ")}
              >
                <div className="text-body font-medium text-ink">
                  {choice.label}
                </div>
                <p className="mt-1 text-body-sm leading-[1.45] text-ink-soft">
                  {choice.description}
                </p>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label
          htmlFor="committee-action-note"
          className="text-tracked uppercase text-ink-soft"
        >
          Rationale
        </label>
        <textarea
          id="committee-action-note"
          rows={3}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className="mt-2 w-full rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body leading-[1.55] text-ink placeholder:text-ink-faint focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
          placeholder="Optional. Recorded with the action, named and dated."
        />
      </div>

      {error && (
        <p role="alert" className="text-body-sm text-critical-text">
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <Button type="submit" disabled={mutation.isPending || !selected}>
          {mutation.isPending ? "Recording…" : "Record action"}
        </Button>
      </div>
    </form>
  );
}
