// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from "react";

import type { Matter, RecipientResponseInput } from "@/api/matters";
import { Button } from "@/components/ds/Button";

/**
 * Preview commitment modal — Band 5 "Preview" step of the recipient
 * response form. Shows the actual Decision record about to be
 * appended to the federal ledger before submit.
 *
 * The panel is the "safety valve" from
 * docs/demo/external-party-response-scaffolding.md — first-time
 * users see exactly what they're committing to before they do it.
 */
export function PreviewCommitmentModal({
  open,
  onClose,
  matter,
  input,
  onConfirm,
  canConfirm,
}: {
  open: boolean;
  onClose: () => void;
  matter: Matter;
  input: RecipientResponseInput;
  onConfirm: () => void;
  canConfirm: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const { originating_party_name, in_response_to, response_shape } = input;

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
        aria-label="Preview commitment"
        className="fixed left-1/2 top-[8vh] z-50 flex max-h-[84vh] w-[640px] -translate-x-1/2 flex-col rounded-lg border border-rule-soft bg-paper shadow-xl"
      >
        <header className="flex items-center justify-between border-b border-rule-soft px-6 py-4">
          <div>
            <div className="font-mono text-[11px] tracking-[0.16em] text-ink-faint uppercase">
              Commitment preview
            </div>
            <h2 className="mt-1 text-[18px] leading-tight font-semibold tracking-tight text-ink">
              Ledger record about to be written
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
          <section>
            <SectionLabel>Matter context</SectionLabel>
            <KVList>
              <KV k="matter_id" v={matter.id} mono />
              <KV
                k="workflow"
                v={`${matter.program_id.toUpperCase()} · ${matter.awarding_agency}`}
              />
              <KV k="period" v={matter.period_label ?? "—"} />
            </KVList>
          </section>

          <section>
            <SectionLabel>Party attribution</SectionLabel>
            <KVList>
              <KV k="originating_party_name" v={originating_party_name} />
              <KV k="in_response_to" v={in_response_to ?? "—"} mono />
              <KV k="is_commitment" v="true" mono />
            </KVList>
          </section>

          <section>
            <SectionLabel>Response shape</SectionLabel>
            <pre className="overflow-x-auto rounded-md border-[0.5px] border-rule-soft bg-bg-warm p-3 font-mono text-[11px] leading-relaxed text-ink">
              {JSON.stringify(response_shape, null, 2)}
            </pre>
          </section>

          <section className="rounded-md border-[0.5px] border-navy/40 bg-navy-soft/20 px-4 py-3">
            <p className="font-display text-[12px] tracking-wider text-navy uppercase">
              Legal effect
            </p>
            <p className="mt-1 text-[13px] leading-relaxed text-ink">
              On submit, this record lands in the federal decision ledger as
              an append-only, legally-binding commitment. Any subsequent
              change requires a new superseding record — nothing is erased.
            </p>
          </section>
        </div>

        <footer className="flex items-center justify-between border-t border-rule-soft px-6 py-4">
          <Button variant="ghost" onClick={onClose}>
            Go back to edit
          </Button>
          <Button onClick={onConfirm} disabled={!canConfirm}>
            Submit commitment
          </Button>
        </footer>
      </div>
    </>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 font-display text-[11px] font-medium tracking-wider text-ink-soft uppercase">
      {children}
    </div>
  );
}

function KVList({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-1.5">
      {children}
    </div>
  );
}

function KV({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <>
      <span className="font-mono text-[11px] text-ink-faint">{k}</span>
      <span className={mono ? "font-mono text-[12px] text-ink" : "text-ink"}>
        {v}
      </span>
    </>
  );
}
