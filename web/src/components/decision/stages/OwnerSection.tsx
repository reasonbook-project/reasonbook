// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { format, parseISO } from "date-fns";

import type { Decision } from "@/api/decisions";
import { AnatomyStageSection } from "@/components/ds/AnatomyStageSection";

/**
 * Stage 2 — the Owner. Surfaces who claimed the decision (owner_id +
 * authority level snapshot) and the escalation path computed at claim
 * time.
 */
export function OwnerSection({
  decision,
  ownerName,
  isLast,
  dimmed,
}: {
  decision: Decision;
  ownerName?: string | null;
  isLast?: boolean;
  dimmed?: boolean;
}) {
  const acknowledged = decision.acknowledged_at
    ? format(parseISO(decision.acknowledged_at), "MMM d, h:mm a")
    : null;

  return (
    <AnatomyStageSection
      stageNumber={2}
      stageName="OWNER"
      timestamp={acknowledged ?? undefined}
      dimmed={dimmed}
      isLast={isLast}
    >
      {decision.owner_id ? (
        <div className="space-y-3">
          <div>
            <div className="text-body">
              Claimed by{" "}
              <span className="font-medium">{ownerName ?? decision.owner_id}</span>
              {decision.owner_authority_level !== null && (
                <span className="ml-2 text-ink-soft">
                  · authority level {decision.owner_authority_level}
                </span>
              )}
            </div>
          </div>
          {decision.escalation_path && decision.escalation_path.length > 0 && (
            <div>
              <div className="text-tracked uppercase text-ink-soft">
                Escalates to
              </div>
              <ol className="mt-2 space-y-1 text-body-sm">
                {decision.escalation_path.map((step, idx) => (
                  <li key={step.user_id} className="flex items-baseline gap-2">
                    <span className="font-mono text-[11px] text-ink-faint">
                      {idx + 1}.
                    </span>
                    <span className="font-medium">{step.name}</span>
                    {step.level !== null && (
                      <span className="text-ink-faint">
                        · level {step.level}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      ) : (
        <p className="text-body-sm text-ink-muted">
          Unowned. Claim this decision to surface the escalation path.
        </p>
      )}
    </AnatomyStageSection>
  );
}
