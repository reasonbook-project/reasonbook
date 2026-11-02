// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useLocation, useNavigate } from "@tanstack/react-router";
import { type ReactNode } from "react";

import { LeftTree } from "@/components/ds/LeftTree";
import { DetailContainer } from "@/components/ds/DetailContainer";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { useWorkflows } from "@/hooks/useWorkflows";
import { useAuthStore } from "@/stores/auth";

/**
 * SettingsLayout — wraps every /settings/* page in the unified
 * shell, with a tree on the left that includes:
 *  - Account, Administration sections
 *  - Semantic engine → Semantic catalog + Workflows
 *
 * Workflows section lists every entitled workflow as a clickable
 * node, landing on the per-workflow detail (Schema / Overrides /
 * Personas / Connectors mode tabs).
 *
 * The semantic engine — workflow YAMLs + threshold overrides +
 * persona config — is where rules that govern signals and decisions
 * live. Exposing it via the same surface pattern as the four primary
 * nav items makes that responsibility legible, not buried admin
 * chrome.
 *
 * No "Tenant" / "Institution" section — DP is single-tenant (the
 * federal government). See memory: project_single_tenant_federal.md.
 */
type StaticHref =
  | "/settings/profile"
  | "/settings/users"
  | "/settings/workflows"
  | "/settings/connectors"
  | "/catalog";

type StaticNavItem = {
  id: string;
  label: string;
  href: StaticHref;
  adminOnly?: boolean;
};

const ACCOUNT_NAV: StaticNavItem[] = [
  { id: "profile", label: "Profile", href: "/settings/profile" },
];

const ADMIN_NAV: StaticNavItem[] = [
  { id: "users", label: "Users", href: "/settings/users", adminOnly: true },
];

const CATALOG_NAV: StaticNavItem[] = [
  { id: "catalog", label: "Semantic catalog", href: "/catalog" },
];

export function SettingsLayout({
  title,
  subtitle,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const location = useLocation();
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === "admin";

  const adminVisible = ADMIN_NAV.filter((n) => !n.adminOnly || isAdmin);
  const isActive = (href: string) => location.pathname.startsWith(href);

  // Workflows feed the tree's Semantic engine section. Show every
  // entitled operational workflow; the user-configuration kind is
  // hidden (those have no rules to author at the surface).
  const workflowsQuery = useWorkflows();
  const workflows = (workflowsQuery.data?.workflows ?? []).filter(
    (w) => w.kind !== "user_configuration",
  );
  const pathname = location.pathname;
  const search = new URLSearchParams(location.search);
  const selectedWorkflowId =
    pathname.startsWith("/settings/workflows") && search.get("id")
      ? search.get("id")
      : null;

  return (
    <AppShellV2>
      <SplitView
        left={
          <LeftTree>
            <LeftTree.Body>
              <LeftTree.Section title="Account">
                {ACCOUNT_NAV.map((item) => (
                  <LeftTree.Node
                    key={item.id}
                    level={1}
                    selected={isActive(item.href)}
                    onClick={() => void navigate({ to: item.href })}
                  >
                    {item.label}
                  </LeftTree.Node>
                ))}
              </LeftTree.Section>

              {adminVisible.length > 0 && (
                <LeftTree.Section title="Administration">
                  {adminVisible.map((item) => (
                    <LeftTree.Node
                      key={item.id}
                      level={1}
                      selected={isActive(item.href)}
                      onClick={() => void navigate({ to: item.href })}
                    >
                      {item.label}
                    </LeftTree.Node>
                  ))}
                </LeftTree.Section>
              )}

              <LeftTree.Section title="Semantic engine">
                {CATALOG_NAV.map((item) => (
                  <LeftTree.Node
                    key={item.id}
                    level={1}
                    selected={isActive(item.href)}
                    onClick={() => void navigate({ to: item.href })}
                  >
                    {item.label}
                  </LeftTree.Node>
                ))}
                <LeftTree.Node
                  level={1}
                  selected={
                    pathname.startsWith("/settings/workflows") &&
                    !selectedWorkflowId
                  }
                  count={workflows.length}
                  onClick={() =>
                    void navigate({ to: "/settings/workflows" })
                  }
                >
                  Workflows
                </LeftTree.Node>
                {workflows.map((w) => (
                  <LeftTree.Node
                    key={w.id}
                    level={2}
                    selected={selectedWorkflowId === w.id}
                    onClick={() =>
                      void navigate({
                        to: "/settings/workflows",
                        search: { id: w.id },
                      })
                    }
                  >
                    {w.name}
                  </LeftTree.Node>
                ))}
                <LeftTree.Node
                  level={1}
                  selected={isActive("/settings/connectors")}
                  onClick={() =>
                    void navigate({ to: "/settings/connectors" })
                  }
                >
                  Connectors
                </LeftTree.Node>
              </LeftTree.Section>
            </LeftTree.Body>
          </LeftTree>
        }
      >
        <DetailContainer title={title} subtitle={subtitle} actions={actions}>
          <div className="px-6 py-6">{children}</div>
        </DetailContainer>
      </SplitView>
    </AppShellV2>
  );
}
