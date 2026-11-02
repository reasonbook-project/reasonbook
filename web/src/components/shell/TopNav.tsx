// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Link, useRouterState } from "@tanstack/react-router";
import { forwardRef, type ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * TopNav — the workspace navigation strip.
 *
 * Second tier of the shell chrome: BrandBar sits above this and owns
 * product identity, so TopNav carries only navigation (Matters,
 * Signals, Oversight) on the left and the user/agency chip cluster
 * on the right.
 *
 * Current-item detection uses pathname-prefix match against each
 * item's `match` (or `to` if no `match` given). Pass an array of
 * prefixes to cover multiple matching paths (e.g., Inbox might match
 * both `/inbox` and `/`).
 */
export type TopNavItem = {
  /** Stable id used as React key. */
  id: string;
  /** Visible label. */
  label: string;
  /** Route to navigate to. */
  to: string;
  /**
   * Pathname prefix(es) that mean "this nav item is current". If
   * omitted, defaults to [to].
   */
  match?: string | string[];
};

export function TopNav({
  items,
  rightSlot,
  className,
}: {
  items: TopNavItem[];
  rightSlot?: ReactNode;
  className?: string;
}) {
  const router = useRouterState();
  const pathname = router.location.pathname;

  const matches = (item: TopNavItem) => {
    const prefixes = item.match
      ? Array.isArray(item.match)
        ? item.match
        : [item.match]
      : [item.to];
    return prefixes.some(
      (p) => pathname === p || pathname.startsWith(`${p}/`),
    );
  };

  return (
    <header
      className={cn(
        "flex items-center gap-6 px-5 py-3.5",
        "border-b-[0.5px] border-rule",
        "bg-paper",
        className,
      )}
    >
      <nav className="flex items-center gap-5">
        {items.map((item) => {
          const current = matches(item);
          return (
            <Link
              key={item.id}
              to={item.to}
              className={cn(
                "text-[13px] py-1.5",
                current
                  ? "text-ink border-b-[1.5px] border-navy pb-[3px]"
                  : "text-ink-soft hover:text-ink",
              )}
              aria-current={current ? "page" : undefined}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {rightSlot && (
        <div className="ml-auto flex items-center gap-3 text-[12px] text-ink-muted">
          {rightSlot}
        </div>
      )}
    </header>
  );
}

/**
 * UserChip — small pill rendered in the TopNav's right slot. Shows
 * the current user's name; click is wired by the consumer (typically
 * a sign-out menu).
 */
type UserChipProps = {
  name: string;
  onClick?: () => void;
  className?: string;
};

/**
 * QueueChip — small pill rendered next to the agency name in the
 * top-right slot. Shows the count of items in the current user's
 * queue and navigates to /inbox on click.
 *
 * Lives outside the primary nav because Inbox is a subject-centric
 * surface ("what's mine to do") rather than an object-centric work
 * surface (Matters/Signals/Oversight). Putting it in the personal-
 * action area — near the user chip — reflects that asymmetry.
 *
 * `urgent` adds a small red dot for SLA-at-risk states. The consumer
 * decides when to set it.
 */
export const QueueChip = forwardRef<
  HTMLButtonElement,
  {
    count: number | null;
    onClick?: () => void;
    urgent?: boolean;
    className?: string;
  }
>(function QueueChip({ count, onClick, urgent, className, ...rest }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      className={cn(
        "relative px-2.5 py-1 rounded-full",
        "bg-bg-warm border-[0.5px] border-rule",
        "text-[12px] text-ink",
        "hover:border-navy",
        "inline-flex items-center gap-1.5",
        className,
      )}
      {...rest}
    >
      {urgent && (
        <span
          aria-hidden
          className="w-1.5 h-1.5 rounded-full bg-flag"
        />
      )}
      <span className="font-mono">{count ?? "…"}</span>
      <span className="text-ink-soft">in queue</span>
    </button>
  );
});

/**
 * AlertsChip — status pill for unattached alerts. Sits next to the
 * QueueChip in the top-right slot; navigates to the /signals matcher
 * on click. Hidden entirely when count is 0 — an empty state on this
 * chip would train operators to ignore it.
 *
 * Uses the flag palette (small red dot + red count) so the badge reads
 * as "there's work sitting here nobody owns" rather than a benign
 * status count.
 */
export const AlertsChip = forwardRef<
  HTMLButtonElement,
  {
    count: number | null;
    onClick?: () => void;
    className?: string;
  }
>(function AlertsChip({ count, onClick, className, ...rest }, ref) {
  if (!count || count <= 0) return null;
  return (
    <button
      ref={ref}
      type="button"
      onClick={onClick}
      title={`${count} unmatched ${count === 1 ? "signal needs" : "signals need"} a matter`}
      className={cn(
        "relative px-2.5 py-1 rounded-full",
        "bg-flag/5 border-[0.5px] border-flag/40",
        "text-[12px] text-flag",
        "hover:border-flag",
        "inline-flex items-center gap-1.5",
        className,
      )}
      {...rest}
    >
      <span aria-hidden className="w-1.5 h-1.5 rounded-full bg-flag" />
      <span className="font-mono">{count}</span>
      <span>{count === 1 ? "alert" : "alerts"}</span>
    </button>
  );
});

/**
 * UserChip — pill rendered in the TopNav's right slot. Click is wired
 * by the consumer (typically by wrapping in a Popover that surfaces
 * Profile + Sign out). forwardRef so Radix's <Popover.Trigger asChild>
 * can attach.
 */
export const UserChip = forwardRef<HTMLButtonElement, UserChipProps>(
  function UserChip({ name, onClick, className, ...rest }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        onClick={onClick}
        className={cn(
          "px-2.5 py-1 rounded-full",
          "bg-bg-warm border-[0.5px] border-rule",
          "text-[12px] text-ink",
          "hover:border-navy",
          className,
        )}
        {...rest}
      >
        {name}
      </button>
    );
  },
);
