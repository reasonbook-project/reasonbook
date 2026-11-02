// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode, useMemo, useState } from "react";

import type { ControlPoint } from "@/api/controlPoints";
import { Button } from "@/components/ds/Button";
import { useControlPoints, useMarkGap } from "@/hooks/useControlPoints";
import { cn } from "@/lib/cn";

/**
 * Process-adherence view — the "named gap, not silent" surface for a matter.
 *
 * Per ADR-11 (docs/architecture/_archive/Spine/ADR-11-accountability-spine.md). Each
 * row is one control point: the gate it represents, the owning authority,
 * and either the Decision that cleared it or the recorded reason it was
 * skipped. Rows are grouped by tier (Federal → State → Recipient) so the
 * panel reads the way oversight expects the fund-flow chain to be reviewed.
 */
export function ControlPointsPanel({
  matterId,
  matterOriginatingDecisionId,
}: {
  matterId: string;
  /** Required to land mark-gap events on the matter's primary ledger. */
  matterOriginatingDecisionId: string | null;
}) {
  const query = useControlPoints(matterId);
  const [gapTarget, setGapTarget] = useState<ControlPoint | null>(null);

  const byTier = useMemo(() => {
    const items = query.data?.items ?? [];
    return {
      federal: items.filter((cp) => cp.tier === "federal"),
      state: items.filter((cp) => cp.tier === "state"),
      recipient: items.filter((cp) => cp.tier === "recipient"),
    };
  }, [query.data?.items]);

  const counts = query.data?.counts;

  return (
    <section className="space-y-5">
      <p className="text-body-sm text-ink-soft">
        Every required control on this matter — cleared, pending, or
        recorded as a named gap with a reason on the chain.
      </p>

      {counts && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Cleared" value={counts.cleared} emphasis="cleared" />
          <Stat label="Pending" value={counts.pending} />
          <Stat label="Named gap" value={counts.skipped} emphasis="warn" />
          <Stat label="Total" value={counts.total} />
        </div>
      )}

      {query.isLoading && (
        <div className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-6 text-body-sm text-ink-muted">
          Loading control points…
        </div>
      )}
      {query.isError && (
        <div className="rounded-md border-[0.5px] border-flag/30 bg-flag/5 px-4 py-3 text-body-sm text-flag">
          Could not load control points.
        </div>
      )}
      {query.isSuccess && counts?.total === 0 && (
        <div className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-6 text-body-sm text-ink-muted">
          No control points materialized for this matter yet.
        </div>
      )}

      {query.isSuccess && counts && counts.total > 0 && (
        <div className="space-y-5">
          <TierGroup
            tierLabel="Federal"
            items={byTier.federal}
            onMarkGap={(cp) => setGapTarget(cp)}
            canMarkGap={Boolean(matterOriginatingDecisionId)}
          />
          <TierGroup
            tierLabel="State"
            items={byTier.state}
            onMarkGap={(cp) => setGapTarget(cp)}
            canMarkGap={Boolean(matterOriginatingDecisionId)}
          />
          <TierGroup
            tierLabel="Recipient"
            items={byTier.recipient}
            onMarkGap={(cp) => setGapTarget(cp)}
            canMarkGap={Boolean(matterOriginatingDecisionId)}
          />
        </div>
      )}

      {gapTarget && matterOriginatingDecisionId && (
        <MarkGapDrawer
          controlPoint={gapTarget}
          decisionId={matterOriginatingDecisionId}
          onClose={() => setGapTarget(null)}
        />
      )}
    </section>
  );
}

function TierGroup({
  tierLabel,
  items,
  onMarkGap,
  canMarkGap,
}: {
  tierLabel: string;
  items: ControlPoint[];
  onMarkGap: (cp: ControlPoint) => void;
  canMarkGap: boolean;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
        {tierLabel}
      </h3>
      <div className="overflow-hidden rounded-md border-[0.5px] border-rule-soft bg-paper">
        {items.map((cp, i) => (
          <ControlPointRow
            key={cp.id}
            cp={cp}
            isFirst={i === 0}
            onMarkGap={onMarkGap}
            canMarkGap={canMarkGap}
          />
        ))}
      </div>
    </div>
  );
}

function ControlPointRow({
  cp,
  isFirst,
  onMarkGap,
  canMarkGap,
}: {
  cp: ControlPoint;
  isFirst: boolean;
  onMarkGap: (cp: ControlPoint) => void;
  canMarkGap: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-4 px-4 py-3 border-t-[0.5px] border-rule-faint",
        isFirst && "border-t-0",
      )}
    >
      <StatusBadge status={cp.status} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 text-body">
          <span className="font-medium text-brand-ink">
            {humanizeArchetype(cp.archetype_id)}
          </span>
          <span className="text-ink-faint">·</span>
          <span className="text-ink-soft">{humanizeTrigger(cp.trigger_event)}</span>
          <GateTypePill gateType={cp.gate_type} />
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 font-mono text-[11.5px] text-ink-muted">
          {cp.required_authority_role && (
            <>
              <span>Authority: {humanizeRole(cp.required_authority_role)}</span>
            </>
          )}
          {cp.status === "cleared" && cp.cleared_at && (
            <>
              <span aria-hidden>·</span>
              <span>Cleared {formatDate(cp.cleared_at)}</span>
            </>
          )}
          {cp.status === "skipped" && cp.cleared_at && (
            <>
              <span aria-hidden>·</span>
              <span>Gap recorded {formatDate(cp.cleared_at)}</span>
            </>
          )}
        </div>
        {cp.status === "skipped" && cp.named_gap_reason && (
          <p className="mt-1.5 text-body-sm text-ink-soft italic">
            “{cp.named_gap_reason}”
          </p>
        )}
      </div>
      {cp.status === "pending" && canMarkGap && (
        <Button compact variant="ghost" onClick={() => onMarkGap(cp)}>
          Record named gap
        </Button>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: ControlPoint["status"] }) {
  const map: Record<ControlPoint["status"], { label: string; cls: string; icon: string }> = {
    cleared: {
      label: "Cleared",
      cls: "bg-cleared/10 text-cleared",
      icon: "ti-check",
    },
    pending: {
      label: "Pending",
      cls: "bg-slate-100 text-slate-700",
      icon: "ti-clock",
    },
    skipped: {
      label: "Named gap",
      cls: "bg-amber-100 text-amber-800",
      icon: "ti-alert-triangle",
    },
    missed: {
      label: "Missed",
      cls: "bg-flag/10 text-flag",
      icon: "ti-alert-circle",
    },
  };
  const { label, cls, icon } = map[status];
  return (
    <span
      className={cn(
        "mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-sm px-2 py-0.5 font-mono text-[11px] font-medium",
        cls,
      )}
    >
      <i className={`ti ${icon}`} aria-hidden />
      {label}
    </span>
  );
}

function GateTypePill({ gateType }: { gateType: ControlPoint["gate_type"] }) {
  return (
    <span
      className={cn(
        "rounded-sm px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em]",
        gateType === "gate"
          ? "bg-navy/10 text-navy"
          : "bg-slate-100 text-slate-600",
      )}
    >
      {gateType}
    </span>
  );
}

function Stat({
  label,
  value,
  emphasis,
}: {
  label: string;
  value: number;
  emphasis?: "cleared" | "warn";
}) {
  const valueClass =
    emphasis === "cleared"
      ? "text-cleared"
      : emphasis === "warn"
        ? "text-amber-700"
        : "text-brand-ink";
  return (
    <div className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3">
      <div className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
        {label}
      </div>
      <div className={cn("mt-1 text-[24px] font-medium leading-none", valueClass)}>
        {value}
      </div>
    </div>
  );
}

function MarkGapDrawer({
  controlPoint,
  decisionId,
  onClose,
}: {
  controlPoint: ControlPoint;
  decisionId: string;
  onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const post = useMarkGap();
  const valid = reason.trim().length >= 8;

  const submit = () => {
    if (!valid) return;
    post.mutate(
      {
        controlPointId: controlPoint.id,
        body: { reason: reason.trim(), decision_id: decisionId },
      },
      { onSuccess: () => onClose() },
    );
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/30"
        onClick={onClose}
        aria-hidden
      />
      <aside
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l-[0.5px] border-rule bg-paper-warm"
        role="dialog"
        aria-labelledby="mark-gap-title"
      >
        <header className="border-b-[0.5px] border-rule-soft px-5 py-4">
          <div className="font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
            Record named gap
          </div>
          <h2
            id="mark-gap-title"
            className="mt-1 text-[18px] font-medium text-brand-ink"
          >
            {humanizeArchetype(controlPoint.archetype_id)} ·{" "}
            {humanizeTrigger(controlPoint.trigger_event)}
          </h2>
          <p className="mt-1 font-mono text-[11.5px] text-ink-muted">
            Tier {controlPoint.tier} · {controlPoint.gate_type}
          </p>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          <label className="mb-1 block text-body-sm text-ink-soft">
            Why this control is being skipped (the auditable record)
          </label>
          <textarea
            className="w-full rounded-sm border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body min-h-[160px]"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Required. Min 8 characters — this becomes part of the ledger."
            autoFocus
          />
          <div className="mt-1 text-[11.5px] text-ink-muted">
            {reason.trim().length} characters
            {!valid && reason.length > 0 && (
              <span className="ml-2 text-flag">— too short</span>
            )}
          </div>
          {post.isError && (
            <div className="mt-3 rounded-sm border-[0.5px] border-flag/30 bg-flag/5 px-3 py-2 text-body-sm text-flag">
              {post.error.message || "Could not record gap."}
            </div>
          )}
        </div>

        <footer className="border-t-[0.5px] border-rule-soft px-5 py-4">
          <div className="flex gap-2">
            <Button onClick={submit} disabled={!valid || post.isPending}>
              {post.isPending ? "Recording…" : "Record gap"}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </footer>
      </aside>
    </>
  );
}

/* ─── Helpers ────────────────────────────────────────────────────────────── */

function humanizeArchetype(id: string): ReactNode {
  return id
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function humanizeTrigger(t: string): string {
  return (
    {
      on_promote: "On promote",
      on_outcome: "On outcome",
      on_modification: "On modification",
      on_adverse_action: "On adverse action",
      on_closeout: "On closeout",
    }[t] ?? t
  );
}

function humanizeRole(r: string): string {
  return r
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}
