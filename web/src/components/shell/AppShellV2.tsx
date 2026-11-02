// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useEffect, useRef } from "react";
import { useRouterState } from "@tanstack/react-router";

import { logout as logoutApi } from "@/api/auth";
import { Popover } from "@/components/ds/Popover";
import { useAlerts } from "@/hooks/useAlerts";
import { useMattersInbox } from "@/hooks/useMatters";
import { useAuthStore } from "@/stores/auth";
import { cn } from "@/lib/cn";

import { BrandBar } from "./BrandBar";
import { AlertsChip, QueueChip, TopNav, type TopNavItem, UserChip } from "./TopNav";

/**
 * AppShellV2 — the unified-surface shell.
 *
 * Replaces the left-Rail AppShell for the four-surface model
 * (Matters, Inbox, Signals, Oversight). Holds the top nav and a
 * content slot; the route is responsible for rendering whatever it
 * wants inside the slot (typically a SplitView with a LeftTree on
 * the left and a DetailContainer on the right).
 *
 * Auth wiring is intentionally minimal — handle the most common
 * concerns (user-presence guard, sign-out, scroll reset on route
 * change) and leave the heavier machinery (EULA modal, help drawer,
 * route-aware sidebar entitlements) to the routes that need it or
 * to a deliberate later sweep.
 *
 * NOT YET WIRED into any route. Phase 2 introduces `/matters` as
 * the first consumer.
 */

// Three peers. Signals stays out (infrastructure — surfaces via
// Matters and Settings › Connectors, not as a destination). Recipient
// portal earns its slot because it's a distinct work surface —
// response state lives outside the Matters register and both federal
// officers (monitoring) and recipients (responding) work here.
// Oversight is the reporting layer over Matters.
// See docs/architecture/MVP-BUILD-QUEUE.md § "Information architecture".
const NAV_ITEMS: TopNavItem[] = [
  { id: "matters", label: "Awards Registry", to: "/matters", match: ["/matters", "/"] },
  { id: "recipient", label: "Recipient portal", to: "/recipient" },
  { id: "oversight", label: "Oversight", to: "/oversight" },
];

export function AppShellV2({
  children,
  rightSlot,
}: {
  children: ReactNode;
  /** Override the default user chip — pass null to suppress entirely. */
  rightSlot?: ReactNode | null;
}) {
  const user = useAuthStore((s) => s.user);
  const reset = useAuthStore((s) => s.reset);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const router = useRouterState();
  const pathname = router.location.pathname;

  // Reset scroll on route change. Mirrors AppShell behavior so deep
  // navigation (matter → matter) doesn't strand the user mid-page.
  const mainRef = useRef<HTMLElement>(null);
  useEffect(() => {
    mainRef.current?.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [pathname]);

  const handleSignOut = async () => {
    try {
      await logoutApi();
    } catch {
      // Best-effort — server-side failure shouldn't block client cleanup.
    }
    reset();
    qc.clear();
    navigate({ to: "/login" });
  };

  // Queue count for the QueueChip — total matters in the caller's
  // Matters-first Inbox (Incoming + Inflight + At-risk), Mine scope
  // + default 90d horizon so it matches what the Inbox lands on.
  // The chip stays subdued until SLA flags appear in the response
  // (future enhancement).
  const queueQuery = useMattersInbox({ scope: "mine", horizon: "90d" });
  const queueCount = queueQuery.data
    ? queueQuery.data.band_counts.incoming +
      queueQuery.data.band_counts.inflight +
      queueQuery.data.band_counts.at_risk
    : null;

  // Unattached-alerts count for the AlertsChip — pulled from the same
  // alerts list the /signals matcher consumes so a fresh disposition
  // there flips the badge without an extra fetch.
  const alertsQuery = useAlerts();
  const unattachedAlerts = alertsQuery.data?.counts.unattached ?? 0;

  // Single-tenant (federal): show the user's agency context, not a
  // tenant name. tenant_name carries the user's federal agency.
  // See memory: project_single_tenant_federal.md.
  //
  // UserChip opens a popover menu with Profile + Sign out — universal
  // SaaS pattern, no extra top-nav chrome.
  const defaultRightSlot =
    rightSlot === undefined && user ? (
      <>
        <AlertsChip
          count={unattachedAlerts}
          onClick={() => void navigate({ to: "/signals" })}
        />
        <QueueChip
          count={queueCount}
          onClick={() => void navigate({ to: "/inbox" })}
        />
        <span>{user.tenant_name ?? user.tenant_id}</span>
        <Popover
          align="end"
          sideOffset={6}
          ariaLabel="Account menu"
          trigger={<UserChip name={user.name || user.username} />}
        >
          <div className="flex flex-col py-1 min-w-[180px]">
            <button
              type="button"
              onClick={() => void navigate({ to: "/settings/profile" })}
              className="px-3 py-2 text-left text-[13px] text-ink hover:bg-bg-warm"
            >
              Profile &amp; settings
            </button>
            <button
              type="button"
              onClick={handleSignOut}
              className="px-3 py-2 text-left text-[13px] text-ink hover:bg-bg-warm border-t-[0.5px] border-rule-faint"
            >
              Sign out
            </button>
          </div>
        </Popover>
      </>
    ) : (
      rightSlot ?? null
    );

  return (
    <div className="h-screen flex flex-col bg-bg overflow-hidden">
      <BrandBar />
      <TopNav items={NAV_ITEMS} rightSlot={defaultRightSlot} />
      <main
        ref={mainRef}
        className={cn("flex-1 min-h-0 overflow-hidden", "flex")}
      >
        {children}
      </main>
    </div>
  );
}
