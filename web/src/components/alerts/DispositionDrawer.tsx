// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode, useState } from "react";

import type {
  Alert,
  DismissReason,
  DispositionAction,
} from "@/api/alerts";
import { Button } from "@/components/ds/Button";
import { usePostDisposition } from "@/hooks/useAlerts";

/**
 * DispositionDrawer — records a promote / dismiss / hold decision on
 * a signal. Extracted from /signals so the matter case-file can open
 * the same drawer in place (triage-in-context), preserving the
 * operator's matter frame.
 */

const DISMISS_REASONS: { value: DismissReason; label: string }[] = [
  { value: "false_positive", label: "False positive" },
  { value: "not_actionable", label: "Not actionable" },
  { value: "duplicate", label: "Duplicate" },
  { value: "resolved_elsewhere", label: "Resolved elsewhere" },
];

export function DispositionDrawer({
  alert,
  action,
  onClose,
  onDispositioned,
}: {
  alert: Alert;
  action: DispositionAction;
  onClose: () => void;
  /** Called on successful disposition so the caller can invalidate
   *  parent queries (e.g. matter data) — separate from `onClose` so
   *  the resulting-state summary can render before dismissal. */
  onDispositioned?: () => void;
}) {
  const [rationale, setRationale] = useState("");
  const [reasonCode, setReasonCode] = useState<DismissReason>("false_positive");
  const [holdUntil, setHoldUntil] = useState("");
  const [resultLine, setResultLine] = useState<ReactNode | null>(null);

  const post = usePostDisposition();
  const submitting = post.isPending;
  const rationaleValid = rationale.trim().length >= 8;

  const handleSubmit = () => {
    if (!rationaleValid) return;
    const body = {
      action,
      rationale: rationale.trim(),
      reason_code: action === "dismiss" ? reasonCode : undefined,
      metadata: action === "hold" && holdUntil ? { hold_until: holdUntil } : undefined,
    };
    post.mutate(
      { alertId: alert.id, body },
      {
        onSuccess: (data) => {
          if (action === "promote" && data.resulting_decision) {
            setResultLine(
              <>
                Promoted to case <b className="font-mono">{data.resulting_decision.decision_number}</b> — now in the Inbox.
              </>,
            );
          } else if (action === "dismiss") {
            setResultLine(
              <>
                Dismissed: <b>{reasonCode.replace("_", " ")}</b> · logged to the ledger.
              </>,
            );
          } else if (action === "hold") {
            setResultLine(<>Hold recorded {holdUntil ? `until ${holdUntil}` : ""}.</>);
          }
          onDispositioned?.();
        },
      },
    );
  };

  const actionLabel =
    action === "promote" ? "Promote to review" : action === "dismiss" ? "Dismiss" : "Hold";

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
        aria-hidden
      />
      {/* Drawer */}
      <aside
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l-[0.5px] border-rule bg-paper-warm"
        role="dialog"
        aria-labelledby="disposition-title"
      >
        <header className="border-b-[0.5px] border-rule-soft px-5 py-4">
          <div className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
            {action === "promote" ? "Record promotion" : action === "dismiss" ? "Record dismissal" : "Record hold"}
          </div>
          <h2
            id="disposition-title"
            className="mt-1 text-[18px] font-semibold text-brand-ink"
          >
            {alert.title}
          </h2>
          <p className="mt-1 font-mono text-[11.5px] text-ink-muted">
            AL-{alert.id.slice(0, 8).toUpperCase()} · severity {alert.severity}
          </p>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          {!resultLine && (
            <>
              {action === "dismiss" && (
                <Field label="Reason">
                  <select
                    className="w-full rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body"
                    value={reasonCode}
                    onChange={(e) => setReasonCode(e.target.value as DismissReason)}
                  >
                    {DISMISS_REASONS.map((r) => (
                      <option key={r.value} value={r.value}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {action === "hold" && (
                <Field label="Follow-up date (optional)">
                  <input
                    type="date"
                    className="w-full rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body"
                    value={holdUntil}
                    onChange={(e) => setHoldUntil(e.target.value)}
                  />
                </Field>
              )}
              <Field
                label={
                  action === "promote"
                    ? "Why this is not a false positive (recorded forward into the case)"
                    : action === "dismiss"
                      ? "Reasoning (the auditable record)"
                      : "Why on hold (and what unblocks it)"
                }
              >
                <textarea
                  className="w-full rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body min-h-[140px]"
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  placeholder="Required. Min 8 characters — the audit answer relies on this."
                  autoFocus
                />
                <div className="mt-1 text-[11.5px] text-ink-muted">
                  {rationale.trim().length} characters
                  {!rationaleValid && rationale.length > 0 && (
                    <span className="ml-2 text-flag">— too short</span>
                  )}
                </div>
              </Field>
              {post.isError && (
                <div className="mt-3 rounded-sm border-[0.5px] border-flag/30 bg-flag/5 px-3 py-2 text-body-sm text-flag">
                  {post.error.message || "Could not record disposition."}
                </div>
              )}
            </>
          )}
          {resultLine && (
            <div className="rounded-sm border-[0.5px] border-cleared/30 bg-cleared/5 px-3 py-3 font-mono text-[12.5px] text-ink-soft">
              <span className="text-cleared" aria-hidden>
                ●{" "}
              </span>
              {resultLine}
            </div>
          )}
        </div>

        <footer className="border-t-[0.5px] border-rule-soft px-5 py-4">
          {!resultLine ? (
            <div className="flex gap-2">
              <Button onClick={handleSubmit} disabled={!rationaleValid || submitting}>
                {submitting ? "Recording…" : actionLabel}
              </Button>
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
            </div>
          ) : (
            <Button onClick={onClose}>Done</Button>
          )}
        </footer>
      </aside>
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-4">
      <label className="mb-1 block text-body-sm text-ink-soft">{label}</label>
      {children}
    </div>
  );
}
