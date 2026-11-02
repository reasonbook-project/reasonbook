// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { cn } from "@/lib/cn";

/**
 * Right-edge drawer tabs.
 *
 * Two small tab handles anchored to the far right of the DetailContainer,
 * near the top of the body. Each opens its named drawer; the active
 * tab fills navy. No full-height strip — just the tab buttons.
 *
 * The Drawer's translateX slide-in offset is bumped by TAB_OFFSET_PX
 * so an open drawer sits just to the left of the tabs, leaving them
 * clickable to swap between drawers.
 */

export type InspectorDrawer = "activity" | "integrity";

/** Horizontal space the tabs reserve at the right edge of the container.
 *  Drawer.rightOffset should match so the drawer doesn't cover them. */
export const TAB_OFFSET_PX = 36;

// Legacy name kept during the port; equivalent to TAB_OFFSET_PX.
export const RAIL_WIDTH_PX = TAB_OFFSET_PX;

// Vertically centered on the DetailContainer's header block (breadcrumb
// strip + eyebrow/title/subtitle/actions) rather than pinned at its top
// edge — otherwise the tabs straddle the warm breadcrumb strip and the
// paper-white header and read as floating on "two shades."
const TAB_TOP_PX = 170;

export function InspectorRail({
  active,
  onToggle,
}: {
  active: InspectorDrawer | null;
  onToggle: (which: InspectorDrawer) => void;
}) {
  return (
    <nav
      aria-label="Drawer switcher"
      className="pointer-events-auto fixed right-2 z-50 flex flex-col gap-1.5"
      style={{ top: TAB_TOP_PX }}
    >
      <RailTab
        icon="ti ti-timeline-event"
        label="Activity"
        active={active === "activity"}
        onClick={() => onToggle("activity")}
      />
      <RailTab
        icon="ti ti-shield-check"
        label="Integrity"
        active={active === "integrity"}
        onClick={() => onToggle("integrity")}
      />
    </nav>
  );
}

function RailTab({
  icon,
  label,
  active,
  onClick,
}: {
  icon: string;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-pressed={active}
      title={label}
      className={cn(
        "flex h-7 w-7 items-center justify-center rounded-md border-[0.5px] transition-colors",
        active
          ? "border-navy bg-navy text-paper"
          : "border-rule-soft bg-paper text-ink-soft hover:bg-bg-warm hover:text-ink",
      )}
    >
      <i className={cn(icon, "text-[15px]")} />
    </button>
  );
}
