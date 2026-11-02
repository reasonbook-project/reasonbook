// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import {
  createRoute,
  useLocation,
  useNavigate,
} from "@tanstack/react-router";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import { schemaExportUrl } from "@/api/workflows";
import { PageHeader } from "@/components/ds/PageHeader";
import { HelpLink } from "@/components/help/HelpLink";
import {
  SCHEMA_SECTIONS,
  type SchemaSectionId,
} from "@/components/schema/tabs";
import { useWorkflowConfig, useWorkflows } from "@/hooks/useWorkflows";

import { AppShellV2 } from "@/components/shell/AppShellV2";

import { rootRoute } from "./__root";

/**
 * Phase 14 — Schema Explorer per dgp-schema-explorer-spec-v1_0.md.
 *
 * Read-only navigable rendering of the workflow's parsed `config.yaml`
 * (with tenant overrides applied at the API layer). Drives the
 * "see what you have" half of Sprint 4's tune-and-see loop; drill-through
 * to /settings/workflows for editing.
 *
 * URL: /workflows/{workflow_id}/schema?section={metrics|alerts|...}
 *
 * Sub-tab components live in `web/src/components/schema/tabs.tsx` so the
 * global Semantic Layer Catalog (`/catalog`) reuses them with multi-
 * workflow input. Per the catalog-promotion spec, this surface keeps
 * its current shape — the only addition is a "View in Semantic Catalog →"
 * link near the page header that deep-links to the catalog with this
 * workflow pre-selected.
 */
export const workflowSchemaRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workflows/$workflowId/schema",
  component: WorkflowSchemaPageShell,
});

/** AppShellV2 wrap so this route renders with the unified top nav. */
function WorkflowSchemaPageShell() {
  return (
    <AppShellV2>
      <div className="flex-1 min-h-0 overflow-y-auto">
        <WorkflowSchemaPage />
      </div>
    </AppShellV2>
  );
}

function WorkflowSchemaPage() {
  const { workflowId } = workflowSchemaRoute.useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );
  const sectionParam = params.get("section") as SchemaSectionId | null;
  const section: SchemaSectionId = SCHEMA_SECTIONS.some((s) => s.id === sectionParam)
    ? (sectionParam as SchemaSectionId)
    : "metrics";

  // Search + dim filter URL state — same shape as the catalog page.
  const queryParam = params.get("q") ?? "";
  const dimsParam = params.get("dims") ?? "";
  const activeDims = useMemo(
    () =>
      dimsParam
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    [dimsParam],
  );
  const [searchInput, setSearchInput] = useState(queryParam);
  useEffect(() => {
    setSearchInput(queryParam);
  }, [queryParam]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const workflowsQuery = useWorkflows();
  const configQuery = useWorkflowConfig(workflowId);

  const workflow = workflowsQuery.data?.workflows.find((w) => w.id === workflowId);

  const setSection = (next: SchemaSectionId) => {
    void navigate({
      to: "/workflows/$workflowId/schema",
      params: { workflowId },
      // Reset dims on tab change; preserve search query.
      search: (prev) => ({
        ...prev,
        section: next,
        dims: undefined,
      }),
    });
  };

  const setDims = (next: readonly string[]) => {
    void navigate({
      to: "/workflows/$workflowId/schema",
      params: { workflowId },
      search: (prev) => ({
        ...prev,
        dims: next.length === 0 ? undefined : next.join(","),
      }),
    });
  };

  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setSearchInput(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void navigate({
        to: "/workflows/$workflowId/schema",
        params: { workflowId },
        search: (prev) => ({
          ...prev,
          q: next.trim() === "" ? undefined : next,
        }),
      });
    }, 150);
  };

  const clearSearch = () => {
    setSearchInput("");
    if (debounceRef.current) clearTimeout(debounceRef.current);
    void navigate({
      to: "/workflows/$workflowId/schema",
      params: { workflowId },
      search: (prev) => ({ ...prev, q: undefined }),
    });
  };

  if (configQuery.isLoading) {
    return (
      <div className="px-7 py-7 text-body-sm text-ink-muted">
        Loading workflow schema…
      </div>
    );
  }

  if (configQuery.isError || !configQuery.data) {
    return (
      <div className="px-7 py-7">
        <p className="text-body text-critical-text">
          Couldn't load this workflow's schema.
        </p>
      </div>
    );
  }

  const cfg = configQuery.data;
  const ActiveTab = SCHEMA_SECTIONS.find((s) => s.id === section)!.component;

  return (
    <div className="px-7 py-7">
      <PageHeader
        title={workflow?.name ?? workflowId}
        subtitle={
          (cfg.workflow.description as string | null | undefined)?.trim() ||
          "Workflow schema"
        }
        right={
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-body-sm text-ink-muted">
              <span className="font-mono">{workflowId}</span>
              <span aria-hidden>·</span>
              <span className="font-mono">v{cfg.workflow.version}</span>
            </div>
            <a
              href={schemaExportUrl(workflowId, "yaml")}
              download
              className="rounded-md border border-rule px-3 py-1.5 text-body-sm font-medium text-ink hover:border-navy hover:text-navy"
            >
              YAML
            </a>
            <a
              href={schemaExportUrl(workflowId, "json")}
              download
              className="rounded-md border border-rule px-3 py-1.5 text-body-sm font-medium text-ink hover:border-navy hover:text-navy"
            >
              JSON
            </a>
            <HelpLink
              topic="catalog/per-workflow-schema"
              variant="icon"
              ariaLabel="Help: per-workflow Schema Explorer"
            />
          </div>
        }
      />

      {/* View-in-catalog deep link — promotes the per-workflow surface
          into the global catalog with this workflow pre-selected. */}
      <div className="mb-4 -mt-2">
        <button
          type="button"
          onClick={() =>
            void navigate({
              to: "/catalog",
              search: { workflows: workflowId, tab: section },
            })
          }
          className="text-body-sm text-ink-muted underline-offset-2 hover:text-ink hover:underline"
        >
          View in Semantic Catalog →
        </button>
      </div>

      {/* Sticky search input — same shape as the catalog page so the
          per-workflow surface and the global catalog read the same. */}
      <div className="sticky top-0 z-10 -mx-7 mb-4 border-b border-rule-soft bg-bg px-7 py-3">
        <input
          type="search"
          value={searchInput}
          onChange={handleSearchChange}
          placeholder="Search metrics, alerts, segments…"
          className="w-full rounded-md border border-rule bg-paper px-3 py-1.5 text-body-sm text-ink placeholder:text-ink-faint focus:border-navy focus:outline-none focus:ring-1 focus:ring-navy/40"
        />
      </div>

      {/* Sub-tab navigation */}
      <div className="mb-6 flex items-center gap-6 border-b border-rule-soft">
        {SCHEMA_SECTIONS.map((s) => {
          const active = s.id === section;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setSection(s.id)}
              className={
                active
                  ? "-mb-px border-b-2 border-navy py-3 text-body-sm font-medium text-ink"
                  : "-mb-px border-b-2 border-transparent py-3 text-body-sm font-medium text-ink-soft hover:text-ink"
              }
            >
              {s.label}
            </button>
          );
        })}
      </div>

      {/* Active sub-tab content — wraps the single cfg in [cfg] for the
          shared multi-workflow tab components. */}
      <ActiveTab
        workflows={[cfg]}
        query={queryParam}
        activeDims={activeDims}
        onDimsChange={setDims}
        onClearSearch={clearSearch}
      />
    </div>
  );
}
