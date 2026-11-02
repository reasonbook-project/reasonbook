// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute } from "@tanstack/react-router";

import type { AgencySummary } from "@/api/auth";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import { useAuthStore } from "@/stores/auth";

import { rootRoute } from "../__root";

export const settingsProfileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/settings/profile",
  component: ProfilePage,
});

function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  return (
    <SettingsLayout title="Profile">
      {user ? (
        <dl className="grid grid-cols-[160px_1fr] gap-x-4 gap-y-3 text-body">
          <Row label="Name" value={user.name} />
          <Row label="Username" value={user.username} mono />
          <Row label="Email" value={user.email} />
          <Row label="Title" value={user.title ?? "—"} />
          <Row label="Role" value={user.role} mono />
          <Row
            label="Tenant"
            value={user.tenant_name ?? user.tenant_id}
          />
          <AgencyRow chain={user.agency_chain} primary={user.agency} />
        </dl>
      ) : (
        <p className="text-body-sm text-ink-muted">Loading…</p>
      )}
    </SettingsLayout>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="contents">
      <dt className="text-tracked uppercase text-ink-soft">{label}</dt>
      <dd className={mono ? "font-mono text-body-sm" : "text-ink"}>{value}</dd>
    </div>
  );
}

/**
 * Agency affiliation — renders the full hierarchical chain
 * (Department → Bureau → Program office) using the › separator,
 * with the primary (deepest) agency emphasised. Falls back to "—"
 * for state / recipient tier users whose agency_chain is empty.
 */
function AgencyRow({
  chain,
  primary,
}: {
  chain: AgencySummary[];
  primary: AgencySummary | null;
}) {
  if (chain.length === 0) {
    return (
      <div className="contents">
        <dt className="text-tracked uppercase text-ink-soft">Agency</dt>
        <dd className="text-ink-faint italic">
          — <span className="not-italic">(no federal agency assignment)</span>
        </dd>
      </div>
    );
  }
  return (
    <div className="contents">
      <dt className="text-tracked uppercase text-ink-soft">Agency</dt>
      <dd className="text-ink">
        <div className="flex flex-wrap items-baseline gap-x-1.5">
          {chain.map((entry, i) => {
            const isLast = i === chain.length - 1;
            return (
              <span key={entry.id} className="flex items-baseline gap-x-1.5">
                <span
                  className={
                    isLast ? "font-medium text-ink" : "text-ink-soft"
                  }
                >
                  {entry.name}
                </span>
                {!isLast && (
                  <span aria-hidden className="text-ink-faint">
                    ›
                  </span>
                )}
              </span>
            );
          })}
        </div>
        {primary && (
          <div className="mt-0.5 font-mono text-[11px] uppercase tracking-[0.06em] text-ink-faint">
            {primary.short_name} · depth {primary.depth}
          </div>
        )}
      </dd>
    </div>
  );
}
