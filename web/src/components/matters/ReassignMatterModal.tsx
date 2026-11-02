// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";

import type { Matter } from "@/api/matters";
import { Button } from "@/components/ds/Button";
import { useClaimMatter } from "@/hooks/useMatters";

/**
 * Reassign confirm modal — bulk-claims every workable Decision on a
 * matter (open / assigned / in_progress, not commitments) as the caller.
 *
 * The confirm step exists because "reassign" transfers ownership from
 * whoever currently holds decisions in progress — a legitimate action,
 * but not something to fire on a stray click. The result surface names
 * exactly what changed so the user can see the batch shape before
 * closing.
 */
export function ReassignMatterModal({
  open,
  onClose,
  matter,
}: {
  open: boolean;
  onClose: () => void;
  matter: Matter;
}) {
  const claim = useClaimMatter(matter.id);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Reset mutation state each time the modal reopens so a subsequent
  // take-over pass renders from a clean confirm state.
  useEffect(() => {
    if (open) claim.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  // Workable set the endpoint will actually touch — mirrors the
  // backend's filter so the confirm screen is honest. Commitments,
  // terminal statuses excluded.
  const workable = matter.decisions.filter(
    (d) =>
      !d.is_commitment &&
      ["open", "assigned", "in_progress"].includes(d.status),
  );

  const result = claim.data;
  const hasResult = !!result;

  return (
    <>
      <div
        aria-hidden
        onClick={onClose}
        className="fixed inset-0 z-40 bg-ink/30"
      />
      <div
        role="dialog"
        aria-modal
        aria-label="Reassign matter"
        className="fixed left-1/2 top-[10vh] z-50 flex max-h-[80vh] w-[560px] -translate-x-1/2 flex-col rounded-lg border border-rule-soft bg-paper shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-rule-soft px-6 py-4">
          <div>
            <div className="font-mono text-[11px] tracking-[0.16em] text-ink-faint uppercase">
              Matter action
            </div>
            <h2 className="mt-1 text-[18px] leading-tight font-semibold tracking-tight text-ink">
              {hasResult ? "Reassign complete" : "Reassign this matter"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-ink-faint hover:text-ink"
          >
            <i className="ti ti-x text-[18px]" aria-hidden />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5 text-[13px]">
          {!hasResult && (
            <>
              <p className="text-ink">
                You'll be assigned as owner on every workable Decision on
                this matter. Terminal decisions (decided, closed) and party
                commitments are left untouched.
              </p>
              <section>
                <div className="mb-2 font-display text-[11px] font-medium tracking-wider text-ink-soft uppercase">
                  Workable decisions ({workable.length})
                </div>
                {workable.length === 0 ? (
                  <p className="text-ink-faint italic">
                    Nothing to claim — every operational decision is
                    already in a terminal state or none exist yet.
                  </p>
                ) : (
                  <ul className="rounded-md border-[0.5px] border-rule-soft">
                    {workable.map((d, i) => (
                      <li
                        key={d.id}
                        className={
                          i === 0
                            ? "flex items-center justify-between px-3 py-2 text-[12px]"
                            : "flex items-center justify-between border-t-[0.5px] border-rule-soft px-3 py-2 text-[12px]"
                        }
                      >
                        <span>
                          <span className="font-mono text-[11px] text-ink-faint">
                            {d.decision_number}
                          </span>
                          <span className="ml-2 text-ink">{d.title}</span>
                        </span>
                        <span className="font-mono text-[10px] tracking-wider text-ink-faint uppercase">
                          {d.status.replace(/_/g, " ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <p className="rounded-md border-[0.5px] border-amber/40 bg-amber-soft px-3 py-2 text-[12px] text-amber">
                Decisions currently owned by someone else are transferred —
                the ownership change is recorded in the audit trail with an
                <span className="mx-1 font-mono">ownership_transferred</span>
                event.
              </p>
            </>
          )}

          {hasResult && (
            <div className="space-y-3">
              <ResultRow
                label="Claimed"
                count={result.claimed.length}
                items={result.claimed}
                tone="ok"
              />
              <ResultRow
                label="Transferred"
                count={result.transferred.length}
                items={result.transferred}
                tone="amber"
              />
              <ResultRow
                label="Already mine (skipped)"
                count={result.skipped_already_mine.length}
                items={result.skipped_already_mine}
                tone="muted"
              />
              <p className="pt-2 text-[12px] text-ink-muted">
                All events logged with bulk operation id{" "}
                <code className="font-mono text-[11px] text-ink">
                  {result.bulk_operation_id.slice(0, 8)}…
                </code>
              </p>
            </div>
          )}

          {claim.isError && (
            <p className="rounded-md border-[0.5px] border-flag bg-flag-soft px-3 py-2 text-[12px] text-flag">
              Reassign failed. Try again or contact support.
            </p>
          )}
        </div>

        <footer className="flex items-center justify-between border-t border-rule-soft px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            {hasResult ? "Close" : "Cancel"}
          </Button>
          {!hasResult && (
            <Button
              onClick={() => claim.mutate()}
              disabled={workable.length === 0 || claim.isPending}
            >
              {claim.isPending
                ? "Taking over…"
                : `Reassign ${workable.length} decision${workable.length === 1 ? "" : "s"}`}
            </Button>
          )}
        </footer>
      </div>
    </>
  );
}

function ResultRow({
  label,
  count,
  items,
  tone,
}: {
  label: string;
  count: number;
  items: string[];
  tone: "ok" | "amber" | "muted";
}) {
  const toneClass =
    tone === "ok"
      ? "bg-ok-soft text-ok border-ok/40"
      : tone === "amber"
        ? "bg-amber-soft text-amber border-amber/40"
        : "bg-bg-warm text-ink-faint border-rule-soft";
  return (
    <div className={`rounded-md border-[0.5px] px-3 py-2 ${toneClass}`}>
      <div className="flex items-baseline justify-between">
        <span className="font-display text-[12px] font-medium tracking-wider uppercase">
          {label}
        </span>
        <span className="font-mono text-[12px]">{count}</span>
      </div>
      {items.length > 0 && (
        <div className="mt-1 font-mono text-[10px] text-ink-soft">
          {items.join(" · ")}
        </div>
      )}
    </div>
  );
}
