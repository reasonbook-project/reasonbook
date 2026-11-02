// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";
import { useState, type ComponentType } from "react";

import type { Decision } from "@/api/decisions";
import { ApiError } from "@/api/client";
import { Button } from "@/components/ds/Button";
import { AnatomyStageSection } from "@/components/ds/AnatomyStageSection";
import { AttachmentsBlock } from "@/components/decision/AttachmentsBlock";
import { CommentsBlock } from "@/components/decision/CommentsBlock";
import { GenericPayloadView } from "@/components/decision/generic/PayloadView";
import { HelpLink } from "@/components/help/HelpLink";
import { usePatchSignal } from "@/hooks/useDecisions";
import { canEditStage } from "@/lib/stageEditability";
import { type PayloadViewProps } from "@/workflows";

/**
 * Stage 1 — the originating signal. Shows when/where the signal was
 * captured, a one-line summary, and the workflow-specific payload (or the
 * generic fallback view).
 *
 * Edit mode (Phase 7.5 Gate 5) lets owners adjust the signal_summary;
 * signal_source is immutable post-creation per the audit-trail rule.
 */
export function SignalSection({
  decision,
  PayloadView,
  isLast,
}: {
  decision: Decision;
  PayloadView?: ComponentType<PayloadViewProps>;
  isLast?: boolean;
}) {
  const PayloadImpl = PayloadView ?? GenericPayloadView;
  const [editing, setEditing] = useState(false);
  const editable = canEditStage("signal", decision.status);

  return (
    <AnatomyStageSection
      stageNumber={1}
      stageName="SIGNAL"
      timestamp={decision.signal_captured_at ? format(parseISO(decision.signal_captured_at), "MMM d, h:mm a") : undefined}
      isLast={isLast}
      headerAccessory={
        editable && !editing ? (
          <EditToggle onClick={() => setEditing(true)} />
        ) : null
      }
    >
      {editing ? (
        <SignalEditForm
          decision={decision}
          onCancel={() => setEditing(false)}
          onSaved={() => setEditing(false)}
        />
      ) : (
        <div className="space-y-4">
          {decision.signal_summary && (
            <p className="text-body text-ink">{decision.signal_summary}</p>
          )}
          {decision.signal_source && (
            <p className="flex items-center gap-2 font-mono text-[11px] text-ink-faint">
              <span>Source: {decision.signal_source}</span>
              <HelpLink
                topic="decisions/manual-vs-engine"
                variant="icon"
                ariaLabel="Help: how signal_source identifies a decision's origin"
              />
            </p>
          )}
          <div className="rounded-md border-[0.5px] border-rule-soft bg-rule-faint px-4 py-3">
            <PayloadImpl decision={decision} />
          </div>
          <AttachmentsBlock decisionId={decision.id} stage="signal" />
          <CommentsBlock decisionId={decision.id} stageContext="signal" />
        </div>
      )}
    </AnatomyStageSection>
  );
}

function SignalEditForm({
  decision,
  onCancel,
  onSaved,
}: {
  decision: Decision;
  onCancel: () => void;
  onSaved: () => void;
}) {
  const patch = usePatchSignal();
  const [summary, setSummary] = useState(decision.signal_summary ?? "");
  const [error, setError] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    patch.mutate(
      {
        decisionId: decision.id,
        body: { signal_summary: summary.trim() || undefined },
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
          Signal summary
        </span>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={3}
          className="mt-2 w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
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

function EditToggle({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-body-sm text-ink-muted hover:text-navy"
    >
      Edit
    </button>
  );
}
