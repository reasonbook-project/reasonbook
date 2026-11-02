// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, useLocation, useNavigate } from "@tanstack/react-router";
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  type CatalogDomain,
  type CatalogEntry,
  type CatalogEntryType,
  type CatalogTier,
  DIRECTION_LABEL,
  DOMAIN_LABEL,
  TIER_LABEL,
  TYPE_LABEL,
  type WhoWatches,
  WHO_WATCHES_LABEL,
} from "@/api/catalog";
import { HelpLink } from "@/components/help/HelpLink";
import { SettingsLayout } from "@/components/settings/SettingsLayout";
import { useCatalog } from "@/hooks/useCatalog";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";

/**
 * Semantic Layer Catalog — faceted, multi-view read-only lens over the
 * semantic engine.
 *
 * Per docs/architecture/backlog/01_semantic_layer/DESIGN-SPEC-semantic-catalog.md:
 *
 *  - One unified dataset of catalog entries (metrics, alerts, personas,
 *    decision types, archetypes, programs) flattened by /api/catalog/entries.
 *  - Faceted search on the left (entity type, who_watches, tier, domain,
 *    workflow). Counts update with active filters.
 *  - Group-by × mode picks the render:
 *       group_by=who, mode=cards     → View B (default) — by who watches
 *       group_by=type, mode=cards    → View A — by entity type
 *       group_by=*,    mode=reference → View C — master/detail
 *  - URL-synced state so a filtered/grouped view is shareable.
 *  - De-IT-ified: every card leads with name + meaning + plain
 *    thresholds; the snake_case id / unit / format drop to a faint mono
 *    technical line, collapsed by default.
 */
export const catalogRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/catalog",
  component: CatalogPage,
});

type GroupBy = "who" | "type";
type Mode = "cards" | "reference";

function CatalogPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );

  // ── URL state ────────────────────────────────────────────────────────
  const groupBy = (params.get("group_by") as GroupBy) || "who";
  const mode = (params.get("mode") as Mode) || "cards";
  const queryParam = params.get("q") ?? "";
  const facetTypes = useSetParam(params.get("type"));
  const facetWho = useSetParam(params.get("who"));
  const facetTier = useSetParam(params.get("tier"));
  const facetDomain = useSetParam(params.get("domain"));
  const facetWorkflow = useSetParam(params.get("workflow"));

  const [searchInput, setSearchInput] = useState(queryParam);
  useEffect(() => {
    setSearchInput(queryParam);
  }, [queryParam]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateSearch = (updates: Record<string, string | undefined>) => {
    void navigate({
      to: "/catalog",
      search: (prev) => {
        const next: Record<string, string> = { ...(prev as object) } as Record<
          string,
          string
        >;
        for (const [k, v] of Object.entries(updates)) {
          if (v === undefined || v === "") delete next[k];
          else next[k] = v;
        }
        return next;
      },
    });
  };

  const handleSearchChange = (e: ChangeEvent<HTMLInputElement>) => {
    const next = e.target.value;
    setSearchInput(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      updateSearch({ q: next.trim() === "" ? undefined : next });
    }, 150);
  };

  const toggleFacet = (key: string, value: string, current: Set<string>) => {
    const next = new Set(current);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    const joined = [...next].sort().join(",");
    updateSearch({ [key]: joined || undefined });
  };

  const clearAll = () => {
    void navigate({
      to: "/catalog",
      search: () => ({}),
    });
  };

  // ── Data + filtering ────────────────────────────────────────────────
  const catalogQuery = useCatalog();
  const entries = catalogQuery.data?.entries ?? [];

  const matchesFacets = (e: CatalogEntry): boolean => {
    if (facetTypes.size > 0 && !facetTypes.has(e.type)) return false;
    if (facetWho.size > 0 && !facetWho.has(e.who_watches)) return false;
    if (facetTier.size > 0 && !facetTier.has(e.tier)) return false;
    if (facetDomain.size > 0 && !facetDomain.has(e.domain)) return false;
    if (facetWorkflow.size > 0) {
      const wf = e.workflow_id ?? "—";
      if (!facetWorkflow.has(wf)) return false;
    }
    if (queryParam) {
      const q = queryParam.toLowerCase();
      const hay = `${e.name} ${e.meaning ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  };

  const filtered = useMemo(
    () => entries.filter(matchesFacets),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [entries, facetTypes, facetWho, facetTier, facetDomain, facetWorkflow, queryParam],
  );

  // Facet counts always reflect the *current* filtered set (per spec).
  const counts = useMemo(() => countFacets(filtered), [filtered]);
  // For showing "live counts" on facets the user could click, we count
  // against `entries` minus that facet's current filter so the badge
  // reads honestly when the facet is multi-select.
  const totalCounts = useMemo(() => countFacets(entries), [entries]);

  // ── Render ─────────────────────────────────────────────────────────
  return (
    <SettingsLayout
      title="Semantic catalog"
      subtitle="Faceted lens over every metric, alert, persona, decision type, archetype, and program in the live semantic config."
      actions={
        <div className="flex items-center gap-3">
          <span className="font-mono text-body-sm text-ink-muted">v2.0</span>
          <HelpLink
            topic="catalog/browse"
            variant="icon"
            ariaLabel="Help: browsing the Semantic Layer Catalog"
          />
        </div>
      }
    >
      <div className="-mx-6 -my-6">
      <div className="px-7 pt-2">
      </div>

      {/* Top control bar — search + view toggle */}
      <div className="border-b-[0.5px] border-rule-soft bg-bg px-7 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex flex-1 items-center gap-2 rounded-md border border-rule bg-paper px-3 py-1.5 min-w-[240px]">
            <span aria-hidden className="text-ink-faint">🔍</span>
            <input
              type="search"
              value={searchInput}
              onChange={handleSearchChange}
              placeholder="Search names and meanings…"
              className="flex-1 bg-transparent text-body-sm text-ink placeholder:text-ink-faint focus:outline-none"
            />
            {searchInput && (
              <button
                type="button"
                onClick={() => {
                  setSearchInput("");
                  updateSearch({ q: undefined });
                }}
                aria-label="Clear search"
                className="text-ink-faint hover:text-ink"
              >
                ×
              </button>
            )}
          </div>

          <ViewToggle
            groupBy={groupBy}
            mode={mode}
            onChange={(g, m) => updateSearch({ group_by: g, mode: m })}
          />
        </div>
      </div>

      {/* Body: facet rail + results */}
      <div className="grid grid-cols-1 lg:grid-cols-[230px_1fr]">
        <aside className="border-r-[0.5px] border-rule-soft bg-paper px-4 py-5 min-h-[calc(100vh-180px)]">
          {(facetTypes.size +
            facetWho.size +
            facetTier.size +
            facetDomain.size +
            facetWorkflow.size >
            0 ||
            queryParam) && (
            <button
              type="button"
              onClick={clearAll}
              className="mb-3 text-body-sm text-brand hover:underline"
            >
              Clear all
            </button>
          )}

          <FacetGroup
            label="Type"
            options={(["metric", "alert", "persona", "decision_type", "archetype", "program"] as CatalogEntryType[]).map(
              (v) => ({
                value: v,
                label: TYPE_LABEL[v],
                count: counts.type[v] ?? 0,
                totalCount: totalCounts.type[v] ?? 0,
              }),
            )}
            active={facetTypes}
            onToggle={(v) => toggleFacet("type", v, facetTypes)}
          />
          <FacetGroup
            label="Who watches"
            options={Object.keys(WHO_WATCHES_LABEL).map((v) => ({
              value: v,
              label: WHO_WATCHES_LABEL[v as WhoWatches],
              count: counts.who[v] ?? 0,
              totalCount: totalCounts.who[v] ?? 0,
            }))}
            active={facetWho}
            onToggle={(v) => toggleFacet("who", v, facetWho)}
          />
          <FacetGroup
            label="Tier"
            options={Object.keys(TIER_LABEL).map((v) => ({
              value: v,
              label: TIER_LABEL[v as CatalogTier],
              count: counts.tier[v] ?? 0,
              totalCount: totalCounts.tier[v] ?? 0,
            }))}
            active={facetTier}
            onToggle={(v) => toggleFacet("tier", v, facetTier)}
          />
          <FacetGroup
            label="Domain"
            options={Object.keys(DOMAIN_LABEL).map((v) => ({
              value: v,
              label: DOMAIN_LABEL[v as CatalogDomain],
              count: counts.domain[v] ?? 0,
              totalCount: totalCounts.domain[v] ?? 0,
            }))}
            active={facetDomain}
            onToggle={(v) => toggleFacet("domain", v, facetDomain)}
          />
        </aside>

        <section className="px-7 py-5 min-w-0">
          <div className="mb-4 font-mono text-body-sm text-ink-muted">
            {filtered.length} {filtered.length === 1 ? "entry" : "entries"}
            {queryParam && (
              <>
                {" "}
                · matching <span className="text-ink-soft">"{queryParam}"</span>
              </>
            )}
          </div>

          {catalogQuery.isLoading ? (
            <p className="text-body-sm text-ink-muted">Loading catalog…</p>
          ) : filtered.length === 0 ? (
            <p className="text-body-sm text-ink-muted">
              No entries match the current filters.
            </p>
          ) : mode === "reference" ? (
            <ReferenceView entries={filtered} />
          ) : groupBy === "who" ? (
            <GroupedCardsView
              entries={filtered}
              groupKey="who_watches"
              groupLabel="What the {} watches"
              labelMap={WHO_WATCHES_LABEL}
            />
          ) : (
            <GroupedCardsView
              entries={filtered}
              groupKey="type"
              groupLabel="{}"
              labelMap={TYPE_LABEL}
            />
          )}
        </section>
      </div>
      </div>
    </SettingsLayout>
  );
}

/* ─── View toggle ──────────────────────────────────────────────────────── */

function ViewToggle({
  groupBy,
  mode,
  onChange,
}: {
  groupBy: GroupBy;
  mode: Mode;
  onChange: (group_by: GroupBy, mode: Mode) => void;
}) {
  const VIEWS: { id: string; label: string; group_by: GroupBy; mode: Mode }[] = [
    { id: "who", label: "By who watches", group_by: "who", mode: "cards" },
    { id: "type", label: "By type", group_by: "type", mode: "cards" },
    { id: "reference", label: "Reference", group_by: groupBy, mode: "reference" },
  ];
  const activeId = mode === "reference" ? "reference" : groupBy;
  return (
    <div className="inline-flex rounded-md border border-rule bg-paper overflow-hidden">
      {VIEWS.map((v) => (
        <button
          key={v.id}
          type="button"
          onClick={() => onChange(v.group_by, v.mode)}
          className={cn(
            "px-3 py-1.5 text-body-sm border-l border-rule-faint first:border-l-0",
            activeId === v.id
              ? "bg-brand text-white font-medium"
              : "text-ink-soft hover:text-ink",
          )}
        >
          {v.label}
        </button>
      ))}
    </div>
  );
}

/* ─── Facets ───────────────────────────────────────────────────────────── */

type FacetOption = { value: string; label: string; count: number; totalCount: number };

function FacetGroup({
  label,
  options,
  active,
  onToggle,
}: {
  label: string;
  options: FacetOption[];
  active: Set<string>;
  onToggle: (value: string) => void;
}) {
  // Hide options with zero items in the overall catalog (defensive against
  // schema additions that haven't been populated yet).
  const visible = options.filter((o) => o.totalCount > 0);
  if (visible.length === 0) return null;
  return (
    <div className="mb-5">
      <h3 className="mb-2 font-mono text-[11px] tracking-[0.06em] uppercase text-ink-muted">
        {label}
      </h3>
      {visible.map((o) => {
        const on = active.has(o.value);
        return (
          <label
            key={o.value}
            className={cn(
              "flex cursor-pointer items-center gap-2 py-1 text-body-sm",
              on ? "text-ink font-medium" : "text-ink-soft hover:text-ink",
            )}
          >
            <span
              className={cn(
                "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border-[1.5px]",
                on ? "border-brand bg-brand text-white" : "border-rule",
              )}
              aria-hidden
            >
              {on && <span className="text-[8px] leading-none">✓</span>}
            </span>
            <input
              type="checkbox"
              checked={on}
              onChange={() => onToggle(o.value)}
              className="sr-only"
            />
            <span className="flex-1">{o.label}</span>
            <span className="ml-auto font-mono text-[11px] text-ink-faint">
              {o.count}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/* ─── Card views (A + B) ───────────────────────────────────────────────── */

function GroupedCardsView({
  entries,
  groupKey,
  groupLabel,
  labelMap,
}: {
  entries: CatalogEntry[];
  groupKey: "who_watches" | "type";
  groupLabel: string;
  labelMap: Record<string, string>;
}) {
  // Stable order: preserve labelMap key order (matches the enum order).
  const groupKeys = Object.keys(labelMap).filter((k) =>
    entries.some((e) => e[groupKey] === k),
  );
  return (
    <div>
      {groupKeys.map((g) => {
        const groupEntries = entries.filter((e) => e[groupKey] === g);
        if (groupEntries.length === 0) return null;
        return (
          <section key={g} className="mb-7">
            <h2 className="mb-3 flex items-baseline gap-2 text-[15px] font-semibold text-brand">
              {groupLabel.replace("{}", labelMap[g])}
              <span className="font-mono text-[12px] font-normal text-ink-muted">
                {groupEntries.length}
              </span>
            </h2>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {groupEntries.map((e) => (
                <ResultCard key={`${e.type}:${e.id}`} entry={e} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function ResultCard({ entry }: { entry: CatalogEntry }) {
  const [open, setOpen] = useState(false);
  const facets: Array<{ label: string; value: string }> = [];
  if (entry.who_watches) {
    facets.push({
      label: "Watched by",
      value: WHO_WATCHES_LABEL[entry.who_watches] ?? entry.who_watches,
    });
  }
  if (entry.tier) {
    facets.push({
      label: "Tier",
      value: TIER_LABEL[entry.tier] ?? entry.tier,
    });
  }
  if (entry.domain) {
    facets.push({
      label: "Domain",
      value: DOMAIN_LABEL[entry.domain] ?? entry.domain,
    });
  }
  if (entry.owner) {
    facets.push({ label: "Owner role", value: entry.owner });
  }
  return (
    <article className="rounded-md border-[0.5px] border-rule bg-paper px-4 py-3.5">
      <header className="flex items-start justify-between gap-2">
        <h3 className="text-[14.5px] font-medium text-brand leading-snug">
          {entry.name}
        </h3>
        <DirectionChip entry={entry} />
      </header>
      {entry.meaning && (
        <p className="mt-1.5 text-body-sm text-ink-soft leading-relaxed">
          {entry.meaning}
        </p>
      )}
      {entry.why_it_matters && (
        <div className="mt-2.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
            Why it matters
          </div>
          <p className="mt-0.5 text-[12.5px] text-ink-soft leading-relaxed">
            {entry.why_it_matters}
          </p>
        </div>
      )}
      {entry.plain_thresholds && (
        <div className="mt-2.5">
          <div className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
            Fires when
          </div>
          <p className="mt-0.5 text-[12.5px] text-ink-muted leading-relaxed">
            {entry.plain_thresholds}
          </p>
        </div>
      )}
      {facets.length > 0 && (
        <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1.5 border-t-[0.5px] border-rule-faint pt-2.5">
          {facets.map((f) => (
            <div key={f.label} className="flex flex-col">
              <dt className="font-mono text-[10px] uppercase tracking-[0.08em] text-ink-faint">
                {f.label}
              </dt>
              <dd className="text-[12.5px] text-ink">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <div className="mt-2.5 flex items-baseline justify-between gap-2 border-t-[0.5px] border-rule-faint pt-2">
        {hasSubstantiveTechnical(entry) ? (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="font-mono text-[11px] text-ink-faint hover:text-ink-soft"
          >
            {open ? "▾" : "▸"} {entry.technical.id as string}
            {entry.technical.unit ? ` · ${entry.technical.unit as string}` : null}
          </button>
        ) : (
          <span className="font-mono text-[11px] text-ink-faint">
            id · {entry.technical.id as string}
          </span>
        )}
      </div>
      {open && hasSubstantiveTechnical(entry) && (
        <pre className="mt-1.5 max-w-full overflow-x-auto font-mono text-[10.5px] text-ink-faint">
          {JSON.stringify(entry.technical, null, 2)}
        </pre>
      )}
    </article>
  );
}

/** True when the technical payload has more than id + presentation
 *  hints — worth exposing as a JSON expander for metrics (thresholds,
 *  format, unit). Alerts / personas / archetypes / programs collapse
 *  to just id + icon + color, which don't warrant a debug expander. */
function hasSubstantiveTechnical(entry: CatalogEntry): boolean {
  if (entry.type !== "metric") return false;
  const t = entry.technical as Record<string, unknown>;
  return Boolean(t.unit || t.format || t.thresholds);
}

function DirectionChip({ entry }: { entry: CatalogEntry }) {
  if (entry.direction) {
    const label = DIRECTION_LABEL[entry.direction];
    const cls =
      entry.direction === "higher_is_better"
        ? "bg-cleared/15 text-cleared"
        : entry.direction === "lower_is_better"
          ? "bg-amber-100 text-amber-800"
          : "bg-slate-100 text-slate-700";
    return (
      <span className={cn("shrink-0 rounded-md px-2 py-0.5 text-[11px]", cls)}>
        {label}
      </span>
    );
  }
  if (entry.severity) {
    const cls =
      entry.severity === "critical"
        ? "bg-flag/10 text-flag"
        : entry.severity === "warning"
          ? "bg-amber-100 text-amber-800"
          : "bg-slate-100 text-slate-700";
    return (
      <span className={cn("shrink-0 rounded-md px-2 py-0.5 text-[11px]", cls)}>
        {entry.severity}
      </span>
    );
  }
  return null;
}

/* ─── Reference view (C) ──────────────────────────────────────────────── */

function ReferenceView({ entries }: { entries: CatalogEntry[] }) {
  const [selectedId, setSelectedId] = useState<string>(
    entries[0] ? `${entries[0].type}:${entries[0].id}` : "",
  );
  const selected = entries.find((e) => `${e.type}:${e.id}` === selectedId) ?? entries[0];
  return (
    <div className="grid grid-cols-1 gap-0 rounded-md border-[0.5px] border-rule bg-paper md:grid-cols-[240px_1fr] overflow-hidden">
      <aside className="max-h-[640px] overflow-y-auto bg-brand/[0.03] p-2 border-b-[0.5px] md:border-b-0 md:border-r-[0.5px] border-rule-faint">
        {entries.map((e) => {
          const id = `${e.type}:${e.id}`;
          const on = id === selectedId;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setSelectedId(id)}
              className={cn(
                "block w-full rounded-md px-2.5 py-1.5 text-left text-body-sm",
                on
                  ? "bg-brand/10 text-brand-ink font-medium"
                  : "text-ink-soft hover:bg-paper-warm",
              )}
            >
              {e.name}
            </button>
          );
        })}
      </aside>
      <div className="p-5">
        {selected && <DefinitionPanel entry={selected} />}
      </div>
    </div>
  );
}

function DefinitionPanel({ entry }: { entry: CatalogEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <article>
      <h3 className="text-[18px] font-semibold text-brand">{entry.name}</h3>
      <FieldRow label="Meaning" value={entry.meaning} />
      <FieldRow label="Why it matters" value={entry.why_it_matters} />
      <div className="mt-3 grid grid-cols-2 gap-4">
        <FieldRow label="Owner" value={entry.owner} small />
        <FieldRow label="Thresholds" value={entry.plain_thresholds} small />
      </div>
      <div className="mt-4 border-t-[0.5px] border-rule-faint pt-3">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex items-center gap-1.5 font-mono text-[12px] text-ink-muted hover:text-ink-soft"
        >
          {open ? "▾" : "▸"} technical contract — {entry.technical.id as string}
        </button>
        {open && (
          <pre className="mt-2 max-w-full overflow-x-auto font-mono text-[10.5px] text-ink-faint">
            {JSON.stringify(entry.technical, null, 2)}
          </pre>
        )}
      </div>
    </article>
  );
}

function FieldRow({
  label,
  value,
  small,
}: {
  label: string;
  value: string | null;
  small?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="mt-3">
      <div className="font-mono text-[11px] tracking-[0.04em] uppercase text-ink-muted">
        {label}
      </div>
      <div className={cn("mt-1 text-ink", small ? "text-body-sm" : "text-body")}>
        {value}
      </div>
    </div>
  );
}

/* ─── Helpers ──────────────────────────────────────────────────────────── */

function useSetParam(raw: string | null): Set<string> {
  return useMemo(() => {
    if (!raw) return new Set();
    return new Set(raw.split(",").map((s) => s.trim()).filter(Boolean));
  }, [raw]);
}

type FacetCounts = {
  type: Record<string, number>;
  who: Record<string, number>;
  tier: Record<string, number>;
  domain: Record<string, number>;
};

function countFacets(entries: CatalogEntry[]): FacetCounts {
  const counts: FacetCounts = { type: {}, who: {}, tier: {}, domain: {} };
  for (const e of entries) {
    counts.type[e.type] = (counts.type[e.type] ?? 0) + 1;
    counts.who[e.who_watches] = (counts.who[e.who_watches] ?? 0) + 1;
    counts.tier[e.tier] = (counts.tier[e.tier] ?? 0) + 1;
    counts.domain[e.domain] = (counts.domain[e.domain] ?? 0) + 1;
  }
  return counts;
}
