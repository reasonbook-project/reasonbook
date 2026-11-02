// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useState } from "react";

import { Drawer } from "@/components/ds/Drawer";
import type { MatterChainResponse } from "@/api/matters";
import { useMatterChain } from "@/hooks/useMatters";
import { cn } from "@/lib/cn";
import { RAIL_WIDTH_PX } from "@/components/matters/InspectorRail";

type VerifyState =
  | { kind: "idle" }
  | { kind: "verifying" }
  | { kind: "ok"; result: MatterChainResponse }
  | { kind: "broken"; result: MatterChainResponse }
  | { kind: "error"; message: string };

/**
 * Right-side integrity drawer — hash-chain evidence for a matter.
 *
 * Renders:
 *   - Verified banner + this matter's event count
 *   - Chain state block: head / prev / genesis hashes (matter-scoped —
 *     head is the hash of this matter's most recent event)
 *   - Verify chain button: refetches the matter chain endpoint. The
 *     backend re-walks the GLOBAL chain (tamper-evidence is intrinsically
 *     global — see hash_chain.py) and returns the matter's slice
 *     alongside the global verified status. Every rendered number and
 *     hash reads from the same MatterChainResponse — no divergence
 *     between the banner, chain-state block, and verify-result pill.
 *   - Recent chain: this matter's events with hash ← prev_hash pointers
 *
 * Same endpoint as ActivityDrawer, different framing.
 */
export function IntegrityDrawer({
  matterId,
  open,
  onClose,
}: {
  matterId: string;
  open: boolean;
  onClose: () => void;
}) {
  const chain = useMatterChain(open ? matterId : undefined);
  const [verify, setVerify] = useState<VerifyState>({ kind: "idle" });

  const events = chain.data?.events ?? [];
  const isVerifying = verify.kind === "verifying";

  async function verifyChain() {
    setVerify({ kind: "verifying" });
    try {
      const { data: result } = await chain.refetch({ throwOnError: true });
      if (!result) {
        throw new Error("no chain response");
      }
      setVerify({ kind: result.verified ? "ok" : "broken", result });
    } catch (err) {
      setVerify({
        kind: "error",
        message: err instanceof Error ? err.message : "unknown error",
      });
    }
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={420}
      rightOffset={RAIL_WIDTH_PX}
      ariaLabel="Integrity"
    >
      <header className="flex items-center justify-between border-b-[0.5px] border-rule-soft px-4 py-3">
        <span className="inline-flex items-center gap-2 font-display text-[14px] font-medium text-ink">
          <i className="ti ti-shield-check text-[16px] text-cleared" />
          Integrity
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close integrity"
          className="rounded-md p-1 text-ink-faint hover:bg-bg-warm hover:text-ink"
        >
          <i className="ti ti-x text-[15px]" />
        </button>
      </header>

      {chain.isLoading && (
        <p className="px-4 py-6 text-body-sm text-ink-muted">Loading chain…</p>
      )}
      {chain.isError && (
        <p className="px-4 py-6 text-body-sm text-flag">
          Couldn't load chain state.
        </p>
      )}

      {chain.data && (
        <>
          <div
            className={cn(
              "border-b-[0.5px] px-4 py-3 text-[12.5px]",
              chain.data.verified
                ? "border-cleared/40 bg-cleared/10 text-cleared"
                : "border-flag/40 bg-flag/10 text-flag",
            )}
          >
            <div className="flex items-center gap-2">
              <i
                className={cn(
                  "text-[16px]",
                  chain.data.verified
                    ? "ti ti-check text-cleared"
                    : "ti ti-alert-triangle text-flag",
                )}
              />
              <span>
                <strong className="font-medium">
                  {chain.data.verified
                    ? "Chain verified end-to-end."
                    : "Chain break detected."}
                </strong>
              </span>
              <span className="ml-auto font-mono text-[11px]">
                {chain.data.event_count} event
                {chain.data.event_count === 1 ? "" : "s"} on this matter
              </span>
            </div>
            {chain.data.verified && (
              <p className="mt-1 pl-6 text-[11.5px] text-ink-soft">
                Confirms the ledger is intact. Signals report patterns{" "}
                <em>within</em> it.
              </p>
            )}
          </div>

          <div className="border-b-[0.5px] border-rule-soft px-4 py-3">
            <div className="mb-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
              Chain state
            </div>
            <HashRow k="Head" v={chain.data.head_hash} />
            <HashRow k="Prev" v={chain.data.prev_hash} />
            <HashRow k="Genesis" v={chain.data.genesis_hash} />
          </div>

          <div className="border-b-[0.5px] border-rule-soft px-4 py-3">
            <button
              type="button"
              onClick={verifyChain}
              disabled={isVerifying}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-navy px-3 py-2 font-display text-[12.5px] font-medium text-paper hover:bg-navy-deep disabled:opacity-60"
            >
              <i className="ti ti-shield-check text-[13px]" />
              {isVerifying ? "Verifying…" : "Verify chain"}
            </button>
            {(verify.kind === "ok" || verify.kind === "broken") && (
              <VerifyResultPill state={verify} />
            )}
            {verify.kind === "error" && (
              <p className="mt-2 text-[11.5px] text-critical-text">
                Verify failed: {verify.message}
              </p>
            )}
          </div>

          <div className="px-4 pt-3 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
            Recent chain
          </div>
          <div className="flex-1 overflow-y-auto pb-3">
            {events.length === 0 && (
              <p className="px-4 py-3 text-body-sm text-ink-muted">
                No events on this matter yet.
              </p>
            )}
            {events
              .slice()
              .reverse()
              .map((e) => (
                <div
                  key={e.event_id}
                  className="grid grid-cols-[60px_1fr] gap-2 px-4 py-2 text-[12px] hover:bg-bg-warm"
                >
                  <span className="pt-0.5 font-mono text-[10.5px] text-ink-faint">
                    {e.ts ? formatTs(e.ts) : "—"}
                  </span>
                  <div className="leading-tight text-ink">
                    <div>
                      {e.summary}
                      {e.decision_number && (
                        <span className="ml-1 font-mono text-[11px] text-ink-faint">
                          · {e.decision_number}
                        </span>
                      )}
                      {e.actor_name && (
                        <span className="ml-1 text-ink-soft">
                          · {e.actor_name}
                        </span>
                      )}
                    </div>
                    <div className="mt-0.5 font-mono text-[10.5px] text-ink-faint">
                      {shortHash(e.hash)}{" "}
                      <span className="text-ink-faint">←</span>{" "}
                      {shortHash(e.prev_hash)}
                    </div>
                  </div>
                </div>
              ))}
          </div>
        </>
      )}
    </Drawer>
  );
}

function VerifyResultPill({
  state,
}: {
  state:
    | { kind: "ok"; result: MatterChainResponse }
    | { kind: "broken"; result: MatterChainResponse };
}) {
  const ok = state.kind === "ok";
  const r = state.result;
  const headLabel = r.head_hash ? `${r.head_hash.slice(0, 12)}…` : "—";
  return (
    <div
      className={cn(
        "mt-3 rounded-md border-[0.5px] px-3 py-2 text-[11.5px] leading-snug",
        ok
          ? "border-cleared/40 bg-cleared/10 text-cleared"
          : "border-flag/40 bg-flag/10 text-flag",
      )}
    >
      <div className="flex items-center gap-1.5 font-mono font-medium uppercase tracking-[0.06em]">
        <i
          className={cn(
            "text-[13px]",
            ok ? "ti ti-circle-check" : "ti ti-alert-triangle-filled",
          )}
        />
        {ok ? "Chain verified" : "Chain broken"}
      </div>
      {ok ? (
        <>
          <div className="mt-0.5 font-mono text-[11px] text-ink-soft">
            {r.event_count.toLocaleString()} event
            {r.event_count === 1 ? "" : "s"} on this matter · head {headLabel}
          </div>
          <div className="mt-1 text-[11px] text-ink-faint">
            Confirms the ledger is intact. Signals report patterns{" "}
            <em>within</em> it.
          </div>
        </>
      ) : (
        <div className="mt-0.5 font-mono text-[11px] text-ink-soft">
          Global chain broken — this matter's slice cannot be trusted.
        </div>
      )}
    </div>
  );
}

function HashRow({ k, v }: { k: string; v: string | null }) {
  return (
    <div className="grid grid-cols-[52px_1fr] items-baseline gap-2 py-0.5">
      <span className="font-mono text-[10.5px] uppercase tracking-[0.08em] text-ink-faint">
        {k}
      </span>
      <span className="break-all font-mono text-[11px] leading-tight text-ink">
        {v ?? "—"}
      </span>
    </div>
  );
}

function shortHash(h: string | null | undefined): string {
  if (!h) return "—";
  return h.slice(0, 8);
}

function formatTs(ts: string): string {
  const d = new Date(ts);
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })} · ${d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", hour12: false })}`;
}
