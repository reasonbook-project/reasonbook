// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import type { DecisionPriority } from "@/api/decisions";
import { Button } from "@/components/ds/Button";
import { HelpLink } from "@/components/help/HelpLink";
import { useCreateDecision } from "@/hooks/useDecisions";
import { useWorkflowConfig, useWorkflows } from "@/hooks/useWorkflows";
import { cn } from "@/lib/cn";

type Props = {
  open: boolean;
  onClose: () => void;
};

const PRIORITIES: DecisionPriority[] = [
  "low",
  "medium",
  "high",
  "urgent",
  "critical",
];

/**
 * Manual decision creation drawer per Phase 7.5 Gate 4 / amendment §4 task 6.
 *
 * Filters decision types to those marked `manually_creatable: true` in the
 * workflow YAML. Authority enforcement happens server-side; the drawer
 * surfaces 403s as inline errors rather than gating the button (the user
 * may have authority on some workflows but not the one they pick).
 */
export function CreateDecisionDrawer({ open, onClose }: Props) {
  const navigate = useNavigate();
  const workflowsQuery = useWorkflows();
  const create = useCreateDecision();

  const [workflowId, setWorkflowId] = useState<string>("");
  const [decisionType, setDecisionType] = useState<string>("");
  const [title, setTitle] = useState("");
  const [signalSummary, setSignalSummary] = useState("");
  const [priority, setPriority] = useState<DecisionPriority>("medium");
  const [submitError, setSubmitError] = useState<string | null>(null);

  const titleRef = useRef<HTMLInputElement>(null);

  // Reset form on close so reopening starts fresh.
  useEffect(() => {
    if (!open) {
      setWorkflowId("");
      setDecisionType("");
      setTitle("");
      setSignalSummary("");
      setPriority("medium");
      setSubmitError(null);
      create.reset();
    }
  }, [open, create]);

  // Esc closes the drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Fetch the selected workflow's config so we can filter decision types.
  const configQuery = useWorkflowConfig(workflowId || undefined);
  const creatableTypes = useMemo(() => {
    const types = configQuery.data?.decision_types ?? [];
    return types.filter((t) => t.manually_creatable);
  }, [configQuery.data?.decision_types]);

  // Reset decision type when workflow changes.
  useEffect(() => {
    setDecisionType("");
  }, [workflowId]);

  const canSubmit =
    !!workflowId && !!decisionType && title.trim().length > 0 && !create.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitError(null);
    create.mutate(
      {
        workflow_id: workflowId,
        decision_type: decisionType,
        title: title.trim(),
        priority,
        signal_summary: signalSummary.trim() || undefined,
      },
      {
        onSuccess: (decision) => {
          onClose();
          void navigate({
            to: "/workflows/$workflowId/decisions/$decisionId",
            params: { workflowId: decision.workflow_id, decisionId: decision.id },
          });
        },
        onError: (err) => {
          if (err instanceof ApiError) {
            const body = err.body as { error?: string } | null;
            setSubmitError(body?.error ?? `Failed (${err.status})`);
          } else {
            setSubmitError("Failed to create decision");
          }
        },
      },
    );
  };

  return (
    <>
      {/* Backdrop */}
      <div
        aria-hidden
        onClick={onClose}
        className={cn(
          "fixed inset-0 z-40 bg-ink/30 transition-opacity duration-150",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      {/* Drawer panel */}
      <aside
        role="dialog"
        aria-modal
        aria-label="Add decision record"
        className={cn(
          "fixed right-0 top-0 z-50 flex h-full w-full max-w-[480px] flex-col border-l-[0.5px] border-rule bg-paper transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-rule-soft px-6 py-5">
          <div>
            <div className="font-mono text-[11px] tracking-[0.16em] text-ink-faint uppercase">
              New decision
            </div>
            <div className="mt-1 flex items-center gap-2">
              <h2 className="text-[20px] font-semibold leading-tight text-ink tracking-tight">
                Create a decision record
              </h2>
              <HelpLink
                topic="inbox/create-decision-manually"
                variant="popover"
                ariaLabel="Help: creating a decision record manually"
                onLaunchFullArticle={onClose}
              />
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-faint hover:text-ink"
          >
            ×
          </button>
        </header>

        <form
          onSubmit={handleSubmit}
          className="flex flex-1 flex-col overflow-hidden"
        >
          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
            {/* Workflow */}
            <Field label="Workflow" htmlFor="cd-workflow" required>
              <select
                id="cd-workflow"
                value={workflowId}
                onChange={(e) => setWorkflowId(e.target.value)}
                required
                className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
              >
                <option value="" disabled>
                  Select a workflow…
                </option>
                {(workflowsQuery.data?.workflows ?? []).map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </Field>

            {/* Decision type */}
            <Field label="Decision type" htmlFor="cd-type" required>
              <select
                id="cd-type"
                value={decisionType}
                onChange={(e) => setDecisionType(e.target.value)}
                required
                disabled={!workflowId || configQuery.isLoading}
                className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft disabled:bg-rule-faint"
              >
                <option value="" disabled>
                  {!workflowId
                    ? "Pick a workflow first"
                    : configQuery.isLoading
                      ? "Loading types…"
                      : creatableTypes.length === 0
                        ? "No manually-creatable types"
                        : "Select a type…"}
                </option>
                {creatableTypes.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              {workflowId &&
                !configQuery.isLoading &&
                creatableTypes.length === 0 && (
                  <p className="mt-1 text-body-sm text-ink-muted">
                    This workflow's decision types are auto-only — they
                    originate from monitoring, not human entry.
                  </p>
                )}
            </Field>

            {/* Title */}
            <Field label="Title" htmlFor="cd-title" required>
              <input
                id="cd-title"
                ref={titleRef}
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                maxLength={200}
                placeholder="One-line summary of the decision"
                className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
              />
            </Field>

            {/* Signal summary */}
            <Field
              label="Signal summary"
              htmlFor="cd-summary"
              hint="What surfaced this decision? Optional but recommended."
            >
              <textarea
                id="cd-summary"
                value={signalSummary}
                onChange={(e) => setSignalSummary(e.target.value)}
                rows={4}
                placeholder="e.g. Pattern of structured deposits across three related accounts, total $36,400 over five business days."
                className="w-full resize-y rounded-md border border-rule bg-paper px-3 py-2 text-body leading-relaxed focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
              />
            </Field>

            {/* Priority */}
            <Field label="Priority" htmlFor="cd-priority">
              <select
                id="cd-priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value as DecisionPriority)}
                className="w-full rounded-md border border-rule bg-paper px-3 py-2 text-body focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
              >
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </Field>

            {submitError && (
              <div
                role="alert"
                className="rounded-md border border-critical-text/30 bg-critical-bg px-3 py-2 text-body-sm text-critical-text"
              >
                {submitError}
              </div>
            )}
          </div>

          <footer className="flex items-center justify-end gap-3 border-t border-rule-soft bg-rule-faint px-6 py-4">
            <Button variant="ghost" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!canSubmit}
              aria-busy={create.isPending}
            >
              {create.isPending ? "Adding…" : "Add record"}
            </Button>
          </footer>
        </form>
      </aside>
    </>
  );
}

function Field({
  label,
  htmlFor,
  required,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label
        htmlFor={htmlFor}
        className="mb-1 flex items-center gap-1 text-body-sm font-medium text-ink"
      >
        {label}
        {required && (
          <span aria-hidden className="text-critical-text">
            *
          </span>
        )}
      </label>
      {children}
      {hint && (
        <p className="mt-1 text-body-sm text-ink-muted">{hint}</p>
      )}
    </div>
  );
}
