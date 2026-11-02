// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Button } from "@/components/ds/Button";
import { useVerifyChain } from "@/hooks/useVerifyChain";
import { cn } from "@/lib/cn";

/**
 * Click-to-verify the SEC-1 hash chain. Renders the result chip
 * inline below the button (green / red), or an error message. Manual
 * trigger only — the freshness of the head hash matters per click,
 * which is also the "we just verified" moment.
 *
 * Lives in /matters AND every matter detail header so the "we can
 * prove integrity" claim is one click away from any demo surface.
 *
 * Uses the DS ghost button (utility action, not a primary CTA) so the
 * styling matches every other secondary action across the platform.
 */
export function VerifyChainButton() {
  const verify = useVerifyChain();
  const result = verify.data;

  return (
    <div className="flex flex-col items-end gap-1.5">
      <Button
        variant="ghost"
        onClick={() => verify.mutate()}
        disabled={verify.isPending}
      >
        <i className="ti ti-shield-check text-[16px]" />
        {verify.isPending ? "Verifying…" : "Verify chain"}
      </Button>
      {result && (
        <div
          className={cn(
            "max-w-[360px] rounded-sm border-[0.5px] px-2.5 py-1.5 text-right font-mono text-[11px] leading-snug",
            result.ok
              ? "border-[#16a34a] bg-[#dcfce7] text-[#15803d]"
              : "border-[#dc2626] bg-[#fee2e2] text-[#9c1c1c]",
          )}
        >
          {result.ok ? (
            <>
              <div className="font-medium uppercase tracking-[0.06em]">
                <i className="ti ti-circle-check mr-1" />
                Chain verified
              </div>
              <div className="text-ink-soft">
                {result.total_events.toLocaleString()} events · head{" "}
                {result.head_hash.slice(0, 12)}…
              </div>
              <div className="mt-1 normal-case text-ink-faint" style={{ fontFamily: "var(--font-body, system-ui)" }}>
                Confirms the ledger is intact. Signals report patterns
                <em> within</em> it.
              </div>
            </>
          ) : (
            <>
              <div className="font-medium uppercase tracking-[0.06em]">
                <i className="ti ti-alert-triangle-filled mr-1" />
                Chain broken
              </div>
              <div className="text-ink-soft">
                Break at index {result.broken_at_index}
              </div>
            </>
          )}
        </div>
      )}
      {verify.isError && (
        <div className="text-[11px] text-critical-text">
          Verify failed: {(verify.error as Error).message}
        </div>
      )}
    </div>
  );
}
