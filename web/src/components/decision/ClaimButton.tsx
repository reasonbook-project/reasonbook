// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { ApiError } from "@/api/client";
import type { Decision } from "@/api/decisions";
import { Button } from "@/components/ds/Button";
import { useClaimDecision } from "@/hooks/useDecisions";

/**
 * Claim ownership button — shown on `open` and `assigned` decisions. On
 * success the cache invalidates and the decision flips to in_progress.
 */
export function ClaimButton({
  decision,
  currentUserId,
}: {
  decision: Decision;
  currentUserId: string | null | undefined;
}) {
  const claim = useClaimDecision();

  const ownsAlready = decision.owner_id && decision.owner_id === currentUserId;
  const ownedByOther = decision.owner_id && !ownsAlready;
  // status='assigned' means owned-but-not-claimed (the federal-finalize
  // promotion path leaves Decisions in this state). The user picks it up
  // to drive the lifecycle forward into 'in_progress'.
  const needsPickup = ownsAlready && decision.status === "assigned";

  const handleClick = () => {
    claim.mutate(decision.id);
  };

  const label = claim.isPending
    ? "Claiming…"
    : ownedByOther
      ? "Reclaim from owner"
      : needsPickup
        ? "Pick up"
        : ownsAlready
          ? "Already yours"
          : "Claim";

  // Only disable when the action is in flight or the user already owns
  // the decision AND it has moved past the pick-up stage.
  const disabled =
    claim.isPending || (Boolean(ownsAlready) && !needsPickup);

  return (
    <div className="flex items-center gap-3">
      <Button onClick={handleClick} disabled={disabled}>
        {label}
      </Button>
      {claim.isError && claim.error instanceof ApiError && (
        <span className="text-body-sm text-critical-text">
          Claim failed: {(claim.error.body as { error?: string })?.error ?? "try again"}
        </span>
      )}
    </div>
  );
}
