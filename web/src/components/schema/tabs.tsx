// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode } from "react";

import type { WorkflowConfig } from "@/api/workflows";
import {
  DimChips,
  FilterCount,
  NoMatchesState,
} from "@/components/schema/DimChips";
import {
  collectDimensions,
  matchesDimensions,
  matchesQuery,
} from "@/components/schema/filter";
import { ThresholdBar, type Thresholds } from "@/components/schema/ThresholdBar";
import { cn } from "@/lib/cn";

/**
 * Common shape for every tab in the schema view. Tabs that don't have
 * dimensions to filter on (States & flow, Documentation) accept the
 * props but ignore `activeDims` / `onDimsChange`. Search query is
 * always honored where the tab has searchable items.
 */
export type SchemaTabProps = {
  workflows: WorkflowConfig[];
  /** Lowercase substring search query. Empty string means no filter. */
  query?: string;
  /** Active dimension chips (OR'd within the tab). */
  activeDims?: string[];
  /** Page callback when the user toggles or clears dimension chips. */
  onDimsChange?: (dims: string[]) => void;
  /** Page callback when the user clicks "Clear search" in the empty state. */
  onClearSearch?: () => void;
};

function toggleDim(active: readonly string[], dim: string): string[] {
  return active.includes(dim)
    ? active.filter((d) => d !== dim)
    : [...active, dim];
}

/**
 * Schema sub-tab components — shared between the per-workflow Schema
 * Explorer (`/workflows/{id}/schema`) and the global Semantic Layer
 * Catalog (`/catalog`).
 *
 * Each tab takes a ``workflows: WorkflowConfig[]`` array — single-workflow
 * callers wrap their cfg in ``[cfg]``. When more than one workflow is in
 * the view, items render with a `WorkflowTag` chip identifying which
 * workflow they belong to. When there's only one, the tag is suppressed
 * since it would be noise.
 *
 * Schema is frozen for the v1.0 release per the catalog spec — no edit
 * affordances, no UI for adding fields. All seven tabs are read-only
 * inspection.
 */

// ─── Shared chip ──────────────────────────────────────────────────────────

/**
 * Small mono-uppercase chip that names which workflow an item belongs
 * to. Renders only when the parent tab has multiple workflows in
 * view. Kept inline here rather than in a separate component file —
 * it's only used from these tabs.
 */
export function WorkflowTag({ name }: { name: string }) {
  return (
    <span className="rounded-sm bg-rule-faint px-1.5 py-px font-mono text-[10px] uppercase tracking-tracked text-ink-faint">
      {name}
    </span>
  );
}

function showTags(workflows: readonly WorkflowConfig[]): boolean {
  return workflows.length > 1;
}

function workflowDisplayName(cfg: WorkflowConfig): string {
  return cfg.workflow.name || cfg.workflow.id;
}

// ─── Metrics ──────────────────────────────────────────────────────────────

type Metric = {
  id: string;
  name: string;
  description?: string | null;
  unit?: string | null;
  format?: string | null;
  direction?: "higher_is_better" | "lower_is_better" | "neutral";
  category?: string | null;
  thresholds?: Thresholds;
};

export function MetricsTab({
  workflows,
  query = "",
  activeDims = [],
  onDimsChange,
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  const allItems = workflows.flatMap((cfg) =>
    ((cfg.metrics ?? []) as Metric[]).map((m) => ({ cfg, m })),
  );
  if (allItems.length === 0) {
    return <EmptySection label="No metrics defined." />;
  }
  const availableDims = collectDimensions(allItems, ({ m }) => m.category);
  const items = allItems.filter(
    ({ m }) =>
      matchesDimensions(m.category, activeDims) &&
      matchesQuery(
        [m.id, m.name, m.description ?? "", m.category ?? ""].join(" "),
        query,
      ),
  );
  return (
    <>
      <DimChips
        available={availableDims}
        active={activeDims}
        onToggle={(d) => onDimsChange?.(toggleDim(activeDims, d))}
        onClear={() => onDimsChange?.([])}
      />
      <FilterCount visible={items.length} total={allItems.length} />
      {items.length === 0 && query ? (
        <NoMatchesState query={query} onClearSearch={onClearSearch ?? (() => undefined)} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {items.map(({ cfg, m }) => (
            <article
              key={`${cfg.workflow.id}::${m.id}`}
              className="rounded-md border-[0.5px] border-rule-soft bg-paper p-4"
            >
              <header className="mb-2 flex flex-wrap items-baseline gap-2">
                <h3 className="font-mono text-body font-medium text-navy">
                  {m.id}
                </h3>
                {m.category && (
                  <span className="font-mono text-[10px] uppercase tracking-tracked text-ink-faint">
                    {m.category}
                  </span>
                )}
                {m.direction && m.direction !== "neutral" && (
                  <span className="font-mono text-[10px] uppercase tracking-tracked text-ink-faint">
                    {m.direction === "higher_is_better"
                      ? "↑ higher"
                      : "↓ lower"}
                  </span>
                )}
                {tagsOn && <WorkflowTag name={workflowDisplayName(cfg)} />}
              </header>
              <p className="text-body-sm text-ink">{m.name}</p>
              {m.description && (
                <p className="mt-1 text-body-sm text-ink-soft">
                  {m.description}
                </p>
              )}
              {(m.unit || m.format) && (
                <p className="mt-2 font-mono text-[10px] text-ink-faint">
                  {m.unit && `Unit: ${m.unit}`}
                  {m.unit && m.format && " · "}
                  {m.format && `Format: ${m.format}`}
                </p>
              )}
              {m.thresholds &&
                Object.values(m.thresholds).some(
                  (v) => v !== null && v !== undefined,
                ) && (
                  <div className="mt-3 border-t border-rule-soft pt-3">
                    <ThresholdBar
                      thresholds={m.thresholds}
                      direction={m.direction ?? "neutral"}
                      unit={m.unit ?? undefined}
                      format={m.format}
                      mode="read"
                    />
                  </div>
                )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}

// ─── Alerts ───────────────────────────────────────────────────────────────

type AlertCategory = {
  id: string;
  name: string;
  description?: string | null;
  color?: string | null;
};

export function AlertsTab({
  workflows,
  query = "",
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  const allItems = workflows.flatMap((cfg) =>
    ((cfg.alert_categories as AlertCategory[] | undefined) ?? []).map((c) => ({
      cfg,
      c,
    })),
  );
  if (allItems.length === 0) {
    return <EmptySection label="No alert categories defined." />;
  }
  // Alerts have no sub-category to filter on (each alert IS a category),
  // so we render search-only — no dimension chips.
  const items = allItems.filter(({ c }) =>
    matchesQuery([c.id, c.name, c.description ?? ""].join(" "), query),
  );
  return (
    <>
      <FilterCount visible={items.length} total={allItems.length} />
      {items.length === 0 && query ? (
        <NoMatchesState
          query={query}
          onClearSearch={onClearSearch ?? (() => undefined)}
        />
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map(({ cfg, c }) => (
            <li
              key={`${cfg.workflow.id}::${c.id}`}
              className="rounded-md border-[0.5px] border-rule-soft bg-paper p-3"
            >
              <div className="flex items-center gap-2">
                {c.color && (
                  <span
                    aria-hidden
                    className="h-[8px] w-[8px] rounded-full"
                    style={{ backgroundColor: c.color }}
                  />
                )}
                <span className="font-mono text-[12px] text-ink">
                  {c.id}
                </span>
                {tagsOn && (
                  <span className="ml-auto">
                    <WorkflowTag name={workflowDisplayName(cfg)} />
                  </span>
                )}
              </div>
              <p className="mt-1 text-body-sm font-medium text-ink">
                {c.name}
              </p>
              {c.description && (
                <p className="mt-1 text-body-sm text-ink-soft">
                  {c.description}
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

// ─── Segments ─────────────────────────────────────────────────────────────

type Segment = {
  id: string;
  name: string;
  filter?: string | null;
  decision_types?: string[];
};

export function SegmentsTab({
  workflows,
  query = "",
  activeDims = [],
  onDimsChange,
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  // Segments are nested as { groupKey: Segment[] } per workflow YAML.
  // Each segment item carries its group key as its dimension — a
  // segment in the "alert_severity" group has dim="alert_severity".
  type FlatSegment = {
    cfg: WorkflowConfig;
    groupKey: string;
    s: Segment;
  };
  const allItems: FlatSegment[] = [];
  for (const cfg of workflows) {
    const segs = cfg.segments as Record<string, Segment[]> | undefined;
    if (!segs) continue;
    for (const [groupKey, items] of Object.entries(segs)) {
      for (const s of items) {
        allItems.push({ cfg, groupKey, s });
      }
    }
  }
  if (allItems.length === 0) {
    return <EmptySection label="No segments defined." />;
  }
  const availableDims = collectDimensions(allItems, ({ groupKey }) => groupKey);
  const items = allItems.filter(
    ({ groupKey, s }) =>
      matchesDimensions(groupKey, activeDims) &&
      matchesQuery([s.id, s.name, s.filter ?? "", groupKey].join(" "), query),
  );
  // Re-group filtered items so the output retains the sectioned shape.
  type Section = {
    cfg: WorkflowConfig;
    groupKey: string;
    items: Segment[];
  };
  const sectionMap = new Map<string, Section>();
  for (const { cfg, groupKey, s } of items) {
    const key = `${cfg.workflow.id}::${groupKey}`;
    let section = sectionMap.get(key);
    if (!section) {
      section = { cfg, groupKey, items: [] };
      sectionMap.set(key, section);
    }
    section.items.push(s);
  }
  const sections = [...sectionMap.values()];
  return (
    <>
      <DimChips
        available={availableDims}
        active={activeDims}
        onToggle={(d) => onDimsChange?.(toggleDim(activeDims, d))}
        onClear={() => onDimsChange?.([])}
      />
      <FilterCount visible={items.length} total={allItems.length} />
      {items.length === 0 && query ? (
        <NoMatchesState
          query={query}
          onClearSearch={onClearSearch ?? (() => undefined)}
        />
      ) : (
        <div className="space-y-6">
          {sections.map(({ cfg, groupKey, items }) => (
            <section key={`${cfg.workflow.id}::${groupKey}`}>
              <h3 className="mb-2 flex items-baseline gap-2 text-tracked uppercase text-ink-soft">
                {groupKey}
                {tagsOn && <WorkflowTag name={workflowDisplayName(cfg)} />}
              </h3>
              <ul className="space-y-2">
                {items.map((s) => (
                  <li
                    key={s.id}
                    className="rounded-md border-[0.5px] border-rule-soft bg-paper p-3"
                  >
                    <div className="flex items-baseline gap-3">
                      <span className="font-mono text-[12px] text-ink">
                        {s.id}
                      </span>
                      <span className="text-body-sm font-medium text-ink">
                        {s.name}
                      </span>
                    </div>
                    {s.filter && (
                      <p className="mt-1 font-mono text-[11px] text-ink-faint">
                        {s.filter}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

// ─── Decision types ──────────────────────────────────────────────────────

export function DecisionTypesTab({
  workflows,
  query = "",
  activeDims = [],
  onDimsChange,
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  const allItems = workflows.flatMap((cfg) =>
    (cfg.decision_types ?? []).map((t) => ({ cfg, t })),
  );
  if (allItems.length === 0) {
    return <EmptySection label="No decision types defined." />;
  }
  const availableDims = collectDimensions(
    allItems,
    ({ t }) => t.category ?? null,
  );
  const items = allItems.filter(
    ({ t }) =>
      matchesDimensions(t.category, activeDims) &&
      matchesQuery(
        [t.id, t.name, t.description ?? "", t.category ?? ""].join(" "),
        query,
      ),
  );
  return (
    <>
      <DimChips
        available={availableDims}
        active={activeDims}
        onToggle={(d) => onDimsChange?.(toggleDim(activeDims, d))}
        onClear={() => onDimsChange?.([])}
      />
      <FilterCount visible={items.length} total={allItems.length} />
      {items.length === 0 && query ? (
        <NoMatchesState
          query={query}
          onClearSearch={onClearSearch ?? (() => undefined)}
        />
      ) : (
        <div className="space-y-4">
          {items.map(({ cfg, t }) => (
        <article
          key={`${cfg.workflow.id}::${t.id}`}
          className="rounded-md border-[0.5px] border-rule-soft bg-paper p-4"
        >
          <header className="flex flex-wrap items-baseline gap-2">
            <h3 className="font-mono text-body font-medium text-navy">
              {t.id}
            </h3>
            <span className="text-body-sm font-medium text-ink">
              {t.name}
            </span>
            {t.priority && (
              <span className="font-mono text-[10px] uppercase tracking-tracked text-ink-faint">
                {t.priority}
              </span>
            )}
            {t.manually_creatable && (
              <span className="rounded-sm bg-info-bg px-1.5 py-px font-mono text-[10px] uppercase tracking-tracked text-info-text">
                manually creatable
              </span>
            )}
            {t.oversight_evidence_eligible && (
              <span className="rounded-sm bg-resolved-bg px-1.5 py-px font-mono text-[10px] uppercase tracking-tracked text-resolved-text">
                apex evidence
              </span>
            )}
            {tagsOn && (
              <span className="ml-auto">
                <WorkflowTag name={workflowDisplayName(cfg)} />
              </span>
            )}
          </header>
          {t.description && (
            <p className="mt-2 text-body-sm text-ink-soft">
              {t.description}
            </p>
          )}
          <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 font-mono text-[11px]">
            {t.sla_hours != null && (
              <Pair label="SLA hours" value={String(t.sla_hours)} />
            )}
            {t.default_owner_role && (
              <Pair label="Owner role" value={t.default_owner_role} />
            )}
            {t.authoring_authority_level && (
              <Pair
                label="Authoring authority"
                value={t.authoring_authority_level}
              />
            )}
            {t.category && <Pair label="Category" value={t.category} />}
          </dl>
              {t.available_actions && t.available_actions.length > 0 && (
                <div className="mt-3 border-t border-rule-soft pt-3">
                  <div className="text-tracked uppercase text-ink-soft">
                    Actions
                  </div>
                  <ul className="mt-1 space-y-1 text-body-sm">
                    {t.available_actions.map((a) => (
                      <li key={a.id}>
                        <span className="font-mono text-[11px] text-ink">
                          {a.id}
                        </span>{" "}
                        <span className="text-ink-soft">
                          {a.name}
                        </span>
                        <span className="ml-2 font-mono text-[10px] text-ink-faint">
                          → {a.authority_required} · {a.impact}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </>
  );
}

// ─── States & flow ────────────────────────────────────────────────────────

export function StatesFlowTab({ workflows }: SchemaTabProps) {
  // The unified workflow YAML schema doesn't formally specify a per-workflow
  // state machine; the platform-wide decision lifecycle (open → assigned →
  // in_progress → decided → closed) is in dgp.decisions.manager. Render the
  // canonical lifecycle here for context — same shape regardless of how
  // many workflows are in view.
  void workflows;
  const states = [
    {
      id: "open",
      label: "Open",
      caption: "Created, no owner yet.",
      color: "info" as const,
    },
    {
      id: "assigned",
      label: "Assigned",
      caption: "Routed to an owner; awaiting acknowledgement.",
      color: "info" as const,
    },
    {
      id: "in_progress",
      label: "In progress",
      caption: "Owner has claimed; rationale being captured.",
      color: "info" as const,
    },
    {
      id: "decided",
      label: "Decided",
      caption: "Option selected, rationale recorded; awaiting action.",
      color: "warning" as const,
    },
    {
      id: "closed",
      label: "Closed",
      caption: "Action complete and outcome captured.",
      color: "resolved" as const,
    },
    {
      id: "deferred",
      label: "Deferred",
      caption: "Postponed with reason and reopen-at timestamp.",
      color: "neutral" as const,
    },
    {
      id: "escalated",
      label: "Escalated",
      caption: "Routed up the authority chain with reason.",
      color: "critical" as const,
    },
  ];
  return (
    <div className="space-y-4">
      <p className="text-body-sm text-ink-soft">
        Decisions move through a platform-wide lifecycle defined in{" "}
        <span className="font-mono text-[12px]">dgp.decisions.manager</span>.
        The state machine is uniform across workflows.
      </p>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {states.map((s) => (
          <li
            key={s.id}
            className="rounded-md border-[0.5px] border-rule-soft bg-paper p-3"
          >
            <div className="flex items-center gap-2">
              <StateDot color={s.color} />
              <span className="font-mono text-[12px] text-ink">
                {s.id}
              </span>
            </div>
            <p className="mt-1 text-body-sm font-medium text-ink">
              {s.label}
            </p>
            <p className="mt-1 text-body-sm text-ink-soft">
              {s.caption}
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StateDot({
  color,
}: {
  color: "info" | "warning" | "resolved" | "critical" | "neutral";
}) {
  const map: Record<typeof color, string> = {
    info: "bg-info-dot",
    warning: "bg-warning-dot",
    resolved: "bg-resolved-dot",
    critical: "bg-critical-dot",
    neutral: "bg-ink-faint",
  };
  return (
    <span
      aria-hidden
      className={cn("inline-block h-[8px] w-[8px] rounded-full", map[color])}
    />
  );
}

// ─── Personas ─────────────────────────────────────────────────────────────

type Persona = {
  id: string;
  name: string;
  description?: string | null;
  default_authority_level?: string | null;
};

export function PersonasTab({
  workflows,
  query = "",
  activeDims = [],
  onDimsChange,
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  const allPersonas = workflows.flatMap((cfg) =>
    ((cfg.personas as Persona[] | undefined) ?? []).map((p) => ({ cfg, p })),
  );
  const allAuthorityLevels = workflows.flatMap((cfg) =>
    (cfg.authority_levels ?? []).map((a) => ({ cfg, a })),
  );
  if (allPersonas.length === 0 && allAuthorityLevels.length === 0) {
    return <EmptySection label="No personas or authority levels defined." />;
  }
  // Personas filter on default_authority_level (drives the chip row).
  // Authority levels themselves are the dimensions — they get filtered
  // by query but not by chips (chips would be self-referential).
  const availableDims = collectDimensions(
    allPersonas,
    ({ p }) => p.default_authority_level ?? null,
  );
  const personas = allPersonas.filter(
    ({ p }) =>
      matchesDimensions(p.default_authority_level, activeDims) &&
      matchesQuery(
        [
          p.id,
          p.name,
          p.description ?? "",
          p.default_authority_level ?? "",
        ].join(" "),
        query,
      ),
  );
  const authorityLevels = allAuthorityLevels.filter(({ a }) =>
    matchesQuery([a.id, a.name].join(" "), query),
  );
  const totalVisible = personas.length + authorityLevels.length;
  const totalAll = allPersonas.length + allAuthorityLevels.length;
  return (
    <>
      <DimChips
        available={availableDims}
        active={activeDims}
        onToggle={(d) => onDimsChange?.(toggleDim(activeDims, d))}
        onClear={() => onDimsChange?.([])}
      />
      <FilterCount visible={totalVisible} total={totalAll} />
      {totalVisible === 0 && query ? (
        <NoMatchesState
          query={query}
          onClearSearch={onClearSearch ?? (() => undefined)}
        />
      ) : (
        <div className="space-y-6">
          {personas.length > 0 && (
        <section>
          <h3 className="mb-3 text-tracked uppercase text-ink-soft">
            Personas
          </h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {personas.map(({ cfg, p }) => (
              <article
                key={`${cfg.workflow.id}::${p.id}`}
                className="rounded-md border-[0.5px] border-rule-soft bg-paper p-3"
              >
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-mono text-[12px] text-navy">{p.id}</span>
                  <span className="text-body-sm font-medium text-ink">
                    {p.name}
                  </span>
                  {tagsOn && (
                    <span className="ml-auto">
                      <WorkflowTag name={workflowDisplayName(cfg)} />
                    </span>
                  )}
                </div>
                {p.default_authority_level && (
                  <p className="mt-1 font-mono text-[11px] text-ink-faint">
                    Default authority: {p.default_authority_level}
                  </p>
                )}
                {p.description && (
                  <p className="mt-2 text-body-sm text-ink-soft">
                    {p.description}
                  </p>
                )}
              </article>
            ))}
          </div>
        </section>
      )}
      {authorityLevels.length > 0 && (
        <section>
          <h3 className="mb-3 text-tracked uppercase text-ink-soft">
            Authority levels
          </h3>
          <ul className="space-y-2">
            {authorityLevels.map(({ cfg, a }) => (
              <li
                key={`${cfg.workflow.id}::${a.id}`}
                className="rounded-md border-[0.5px] border-rule-soft bg-paper p-3"
              >
                <div className="flex flex-wrap items-baseline gap-3">
                  <span className="font-mono text-[12px] text-ink">
                    {a.id}
                  </span>
                  <span className="text-body-sm font-medium text-ink">
                    {a.name}
                  </span>
                  <span className="font-mono text-[11px] text-ink-faint">
                    level {a.level}
                  </span>
                  {tagsOn && (
                    <span className="ml-auto">
                      <WorkflowTag name={workflowDisplayName(cfg)} />
                    </span>
                  )}
                </div>
                {a.can_approve.length > 0 && (
                  <p className="mt-1 font-mono text-[11px] text-ink-faint">
                    Can approve:{" "}
                    {a.can_approve.length === 1 && a.can_approve[0] === "all"
                      ? "all actions"
                      : a.can_approve.join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
        </div>
      )}
    </>
  );
}

// ─── Documentation ────────────────────────────────────────────────────────

export function DocumentationTab({
  workflows,
  query = "",
  onClearSearch,
}: SchemaTabProps) {
  const tagsOn = showTags(workflows);
  const allSections = workflows
    .map((cfg) => {
      const description = (
        cfg.workflow.description as string | null | undefined
      )?.trim();
      const docs = cfg.documentation as
        | { notes?: string; references?: string[]; change_log?: string[] }
        | undefined;
      return { cfg, description, docs };
    })
    .filter((s) => s.description || s.docs);
  if (allSections.length === 0) {
    return <EmptySection label="No documentation provided." />;
  }
  // Search filters whole workflow doc-blocks. No dimension chips —
  // documentation is prose, not enumerable.
  const sections = allSections.filter(({ cfg, description, docs }) =>
    matchesQuery(
      [
        cfg.workflow.name,
        description ?? "",
        docs?.notes ?? "",
        ...(docs?.references ?? []),
      ].join(" "),
      query,
    ),
  );
  return (
    <>
      <FilterCount visible={sections.length} total={allSections.length} />
      {sections.length === 0 && query ? (
        <NoMatchesState
          query={query}
          onClearSearch={onClearSearch ?? (() => undefined)}
        />
      ) : (
        <div className="max-w-[80ch] space-y-8 text-body text-ink">
          {sections.map(({ cfg, description, docs }) => (
        <article
          key={cfg.workflow.id}
          className="space-y-4"
        >
          {tagsOn && (
            <div>
              <WorkflowTag name={workflowDisplayName(cfg)} />
            </div>
          )}
          {description && (
            <section>
              <h3 className="mb-2 text-tracked uppercase text-ink-soft">
                Description
              </h3>
              <p className="leading-relaxed">{description}</p>
            </section>
          )}
          {docs?.notes && (
            <section>
              <h3 className="mb-2 text-tracked uppercase text-ink-soft">
                Notes
              </h3>
              <p className="leading-relaxed text-ink-soft">
                {docs.notes}
              </p>
            </section>
          )}
          {docs?.references && docs.references.length > 0 && (
            <section>
              <h3 className="mb-2 text-tracked uppercase text-ink-soft">
                References
              </h3>
              <ul className="list-disc pl-5 text-body-sm text-ink-soft">
                {docs.references.map((r, idx) => (
                  <li key={idx}>{r}</li>
                ))}
              </ul>
            </section>
          )}
        </article>
      ))}
        </div>
      )}
    </>
  );
}

// ─── Shared helpers ───────────────────────────────────────────────────────

export function EmptySection({ label }: { label: string }) {
  return <p className="text-body-sm text-ink-muted">{label}</p>;
}

function Pair({ label, value }: { label: string; value: ReactNode }) {
  return (
    <>
      <dt className="text-ink-muted">{label}</dt>
      <dd className="text-ink">{value}</dd>
    </>
  );
}

// ─── Section registry ─────────────────────────────────────────────────────
//
// Used by both the per-workflow Schema Explorer and the Catalog page to
// drive sub-tab navigation + render the active section's component.

export const SCHEMA_SECTIONS = [
  { id: "metrics", label: "Metrics", component: MetricsTab },
  { id: "alerts", label: "Alerts", component: AlertsTab },
  { id: "segments", label: "Segments", component: SegmentsTab },
  { id: "decision_types", label: "Decision types", component: DecisionTypesTab },
  { id: "states", label: "States & flow", component: StatesFlowTab },
  { id: "personas", label: "Personas", component: PersonasTab },
  { id: "documentation", label: "Documentation", component: DocumentationTab },
] as const;

export type SchemaSectionId = (typeof SCHEMA_SECTIONS)[number]["id"];
