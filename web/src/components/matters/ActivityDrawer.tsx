// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo, useState } from "react";

import { Drawer } from "@/components/ds/Drawer";
import { type ChainEvent } from "@/api/matters";
import { useMatterChain } from "@/hooks/useMatters";
import { cn } from "@/lib/cn";
import { RAIL_WIDTH_PX } from "@/components/matters/InspectorRail";

/**
 * Right-side activity drawer — event timeline for a matter.
 *
 * Data source: /api/integrity/matters/<matter_id>/chain (same endpoint
 * that powers IntegrityDrawer). Same events, different framing —
 * Activity foregrounds who did what when; Integrity foregrounds the
 * hash chain the events participate in.
 *
 * Filter chips: All / Events / Comments. "Comments" = decision_events
 * rows with action='comment'; "Events" = everything else.
 */
export function ActivityDrawer({
  matterId,
  open,
  onClose,
}: {
  matterId: string;
  open: boolean;
  onClose: () => void;
}) {
  const chain = useMatterChain(open ? matterId : undefined);
  const [filter, setFilter] = useState<"all" | "events" | "comments">("all");

  const events = chain.data?.events ?? [];
  const filtered = useMemo(
    () =>
      filter === "all"
        ? events
        : filter === "comments"
          ? events.filter((e) => e.action === "comment")
          : events.filter((e) => e.action !== "comment"),
    [events, filter],
  );
  const grouped = useMemo(() => groupByDay(filtered), [filtered]);
  const counts = useMemo(
    () => ({
      all: events.length,
      events: events.filter((e) => e.action !== "comment").length,
      comments: events.filter((e) => e.action === "comment").length,
    }),
    [events],
  );

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={420}
      rightOffset={RAIL_WIDTH_PX}
      ariaLabel="Activity"
    >
      <header className="flex items-center justify-between border-b-[0.5px] border-rule-soft px-4 py-3">
        <span className="inline-flex items-center gap-2 font-display text-[14px] font-medium text-ink">
          <i className="ti ti-timeline-event text-[16px] text-ink-soft" />
          Activity
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close activity"
          className="rounded-md p-1 text-ink-faint hover:bg-bg-warm hover:text-ink"
        >
          <i className="ti ti-x text-[15px]" />
        </button>
      </header>

      <div className="flex gap-1.5 border-b-[0.5px] border-rule-soft bg-bg-warm px-4 py-2">
        <FilterChip
          label="All"
          count={counts.all}
          active={filter === "all"}
          onClick={() => setFilter("all")}
        />
        <FilterChip
          label="Events"
          count={counts.events}
          active={filter === "events"}
          onClick={() => setFilter("events")}
        />
        <FilterChip
          label="Comments"
          count={counts.comments}
          active={filter === "comments"}
          onClick={() => setFilter("comments")}
        />
      </div>

      <div className="flex-1 overflow-y-auto py-1.5">
        {chain.isLoading && (
          <p className="px-4 py-6 text-body-sm text-ink-muted">Loading…</p>
        )}
        {chain.isError && (
          <p className="px-4 py-6 text-body-sm text-flag">
            Couldn't load activity.
          </p>
        )}
        {!chain.isLoading && !chain.isError && filtered.length === 0 && (
          <p className="px-4 py-6 text-body-sm text-ink-muted">
            Nothing to show for this filter.
          </p>
        )}
        {grouped.map((day) => (
          <div key={day.key}>
            <div className="px-4 py-2 font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-faint">
              {day.label}
            </div>
            {day.events.map((event) => (
              <EventRow key={event.event_id} event={event} />
            ))}
          </div>
        ))}
      </div>
    </Drawer>
  );
}

function FilterChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full border-[0.5px] px-2.5 py-0.5 font-display text-[11.5px] font-medium",
        active
          ? "border-navy bg-navy text-paper"
          : "border-rule-soft bg-paper text-ink-soft hover:bg-bg-warm",
      )}
    >
      {label}
      <span className="ml-1 font-mono text-[10.5px] opacity-70">{count}</span>
    </button>
  );
}

function EventRow({ event }: { event: ChainEvent }) {
  const time = event.ts ? formatTime(event.ts) : "—";
  const iconClass = iconFor(event.action);
  const iconColor = colorFor(event.action);
  return (
    <div className="grid grid-cols-[52px_20px_1fr] items-start gap-2 px-4 py-2 hover:bg-bg-warm">
      <span className="pt-0.5 font-mono text-[11px] text-ink-faint">{time}</span>
      <i className={cn("pt-0.5 text-[16px]", iconClass, iconColor)} />
      <div className="text-[12.5px] leading-tight text-ink">
        {event.summary}
        {event.decision_number && (
          <span className="ml-1.5 font-mono text-[11px] text-ink-faint">
            · {event.decision_number}
          </span>
        )}
        {event.actor_name && (
          <span className="ml-1 text-ink-soft">· {event.actor_name}</span>
        )}
      </div>
    </div>
  );
}

/* ─── Helpers ───────────────────────────────────────────────────────── */

function iconFor(action: string): string {
  switch (action) {
    case "created":
      return "ti ti-circle-plus";
    case "assigned":
    case "claim":
      return "ti ti-user-check";
    case "finalize":
    case "outcome":
      return "ti ti-check";
    case "action":
      return "ti ti-flag";
    case "defer":
      return "ti ti-clock-pause";
    case "escalate":
      return "ti ti-arrow-up-right";
    case "comment":
      return "ti ti-message-2";
    case "attachment_added":
    case "attachment_removed":
      return "ti ti-paperclip";
    case "ownership_transferred":
      return "ti ti-user-share";
    case "matter_field_amended":
      return "ti ti-edit";
    default:
      return "ti ti-point";
  }
}

function colorFor(action: string): string {
  if (
    action === "finalize" ||
    action === "outcome" ||
    action === "action"
  ) {
    return "text-cleared";
  }
  if (action === "escalate") return "text-flag";
  if (action === "comment") return "text-ink-faint";
  return "text-navy";
}

function formatTime(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

type DayGroup = { key: string; label: string; events: ChainEvent[] };

function groupByDay(events: ChainEvent[]): DayGroup[] {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);

  const groups = new Map<string, DayGroup>();
  for (const e of events) {
    if (!e.ts) continue;
    const d = new Date(e.ts);
    const day = new Date(d);
    day.setHours(0, 0, 0, 0);
    const key = day.toISOString().slice(0, 10);
    let label: string;
    if (day.getTime() === today.getTime()) {
      label = `Today · ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } else if (day.getTime() === yesterday.getTime()) {
      label = `Yesterday · ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
    } else {
      label = d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year:
          d.getFullYear() === today.getFullYear() ? undefined : "numeric",
      });
    }
    let group = groups.get(key);
    if (!group) {
      group = { key, label, events: [] };
      groups.set(key, group);
    }
    group.events.push(e);
  }
  // Reverse so newest day appears first
  return [...groups.values()].reverse();
}
