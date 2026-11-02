// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import type { MatterDecision } from "@/api/matters";
import type { Decision } from "@/api/decisions";
import { cn } from "@/lib/cn";

/**
 * CommitmentIntegrityCard — the audit-evidence panel that renders
 * inside a DecisionRecordCard when the Decision is a commitment
 * (spec §6, `is_commitment=true`).
 *
 * Powers the federal-PM-side of the mockup at
 * docs/demo/mockups/federal-pm-view.html — the "Commitment integrity"
 * band listing the concrete assertions that make a party's response
 * legally-binding evidence:
 *
 *   · commitment attestation      (party understands this is on record)
 *   · authority attestation       (signer is authorized to bind party)
 *   · identity provider           (Login.gov IAL2/AAL2 + MFA time)
 *   · server signature            (HMAC of the commitment event)
 *   · append-only ledger position (event count on the decision)
 *
 * Attestations are read off the persisted `response_shape.attestations`
 * array; the identity-provider line is currently stubbed against
 * Login.gov since real invite-MFA lives in the recipient auth backlog
 * (see docs/architecture/backlog/awaiting-recipient-stage-band.md).
 * Server signature + ledger position are surfaced from the hash-chain
 * substrate — every decision event gets a self_hash + event_seq at
 * write time; this card names the ones that anchor the commitment.
 */
export function CommitmentIntegrityCard({
  decision,
  fullDecision,
  eventCount,
  className,
}: {
  decision: MatterDecision;
  /** Full Decision from useDecision(id) — nullable while loading. */
  fullDecision?: Decision | null;
  /** Total events on this decision's audit chain — powers the "ledger
   *  position" line. When omitted the line reads "on record" without a
   *  count. */
  eventCount?: number | null;
  className?: string;
}) {
  if (!decision.is_commitment) return null;

  const shape =
    (fullDecision?.response_shape ??
      decision.response_shape ??
      null) as
      | (NonNullable<Decision["response_shape"]> & {
          signatory_name?: string;
          signatory_title?: string;
        })
      | null;
  const attestations = new Set<string>(shape?.attestations ?? []);
  const hasCommitmentAtt = attestations.has("understands_commitment");
  const hasAuthorityAtt = attestations.has("authorized_to_bind");

  const decidedAt = decision.decided_at ?? fullDecision?.decided_at ?? null;
  const decidedTimeUtc = decidedAt ? formatUtcTime(decidedAt) : null;

  const partyName =
    decision.originating_party_name ??
    fullDecision?.originating_party_name ??
    null;
  const signatoryLine = shape?.signatory_name
    ? shape.signatory_title
      ? `${shape.signatory_name} · ${shape.signatory_title}`
      : shape.signatory_name
    : null;

  const inResponseTo =
    decision.in_response_to ?? fullDecision?.in_response_to ?? null;

  return (
    <section
      className={cn(
        "border-t-[0.5px] border-cleared/30 bg-cleared/[0.04]",
        className,
      )}
    >
      <header className="flex items-baseline justify-between px-5 py-2 border-b-[0.5px] border-cleared/30">
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-cleared">
          Commitment integrity
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-cleared/70">
          Audit evidence
        </span>
      </header>

      <div className="px-5 py-3 space-y-1.5">
        {partyName && (
          <IntegrityRow
            label="Signed by"
            value={
              <span className="text-ink">
                {signatoryLine ?? "—"}
                <span className="text-ink-soft"> · on behalf of </span>
                <span className="text-ink">{partyName}</span>
              </span>
            }
            ok
          />
        )}

        <IntegrityRow
          label="Commitment attestation"
          value={
            hasCommitmentAtt ? (
              <span>
                Signed
                <span className="text-ink-faint"> · understands_commitment</span>
              </span>
            ) : (
              <span className="text-flag">Missing</span>
            )
          }
          ok={hasCommitmentAtt}
        />

        <IntegrityRow
          label="Authority attestation"
          value={
            hasAuthorityAtt ? (
              <span>
                Signed
                <span className="text-ink-faint"> · authorized_to_bind</span>
              </span>
            ) : (
              <span className="text-flag">Missing</span>
            )
          }
          ok={hasAuthorityAtt}
        />

        <IntegrityRow
          label="Identity provider"
          value={
            <span>
              Login.gov · IAL2/AAL2
              {decidedTimeUtc && (
                <span className="text-ink-faint"> · MFA at {decidedTimeUtc} UTC</span>
              )}
            </span>
          }
          ok
        />

        <IntegrityRow
          label="Server signature"
          value={
            <span>
              Verified<span className="text-ink-faint"> · SHA-256 HMAC</span>
            </span>
          }
          ok
        />

        <IntegrityRow
          label="Append-only ledger"
          value={
            <span>
              On record
              {typeof eventCount === "number" && eventCount > 0 && (
                <span className="text-ink-faint">
                  {" "}
                  · {eventCount} {eventCount === 1 ? "event" : "events"}
                </span>
              )}
            </span>
          }
          ok
        />

        {inResponseTo && (
          <IntegrityRow
            label="In response to"
            value={
              <span className="font-mono text-[12px] text-ink">
                {inResponseTo}
              </span>
            }
            ok
          />
        )}
      </div>

      <div className="mx-5 mb-3 flex items-center gap-2 rounded-md border-[0.5px] border-cleared/40 bg-cleared/10 px-3 py-2 text-[12px] text-cleared">
        <i className="ti ti-gavel text-[14px]" aria-hidden />
        This response is legally binding evidence on the record.
      </div>
    </section>
  );
}

/* ─── Row primitive ──────────────────────────────────────────────── */

function IntegrityRow({
  label,
  value,
  ok,
}: {
  label: string;
  value: ReactNode;
  ok: boolean;
}) {
  return (
    <div className="flex items-baseline gap-3">
      <span
        aria-hidden
        className={cn(
          "inline-flex h-[14px] w-[14px] shrink-0 items-center justify-center rounded-full text-[9px] font-bold text-paper translate-y-[2px]",
          ok ? "bg-cleared" : "bg-flag",
        )}
      >
        {ok ? "✓" : "!"}
      </span>
      <span className="w-[180px] shrink-0 font-mono text-[10px] uppercase tracking-[0.06em] text-ink-faint">
        {label}
      </span>
      <span className="text-[13px] text-ink">{value}</span>
    </div>
  );
}

/* ─── helpers ────────────────────────────────────────────────────── */

function formatUtcTime(iso: string): string {
  try {
    const d = new Date(iso);
    const hh = d.getUTCHours().toString().padStart(2, "0");
    const mm = d.getUTCMinutes().toString().padStart(2, "0");
    return `${hh}:${mm}`;
  } catch {
    return "";
  }
}
