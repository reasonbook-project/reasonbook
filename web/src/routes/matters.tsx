// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { createRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMemo, useState } from "react";

import { Button } from "@/components/ds/Button";
import {
  Breadcrumb,
  DetailContainer,
} from "@/components/ds/DetailContainer";
import { LeftTree } from "@/components/ds/LeftTree";
import { ActivityDrawer } from "@/components/matters/ActivityDrawer";
import { IntegrityDrawer } from "@/components/matters/IntegrityDrawer";
import { InspectorRail } from "@/components/matters/InspectorRail";
import { AppShellV2 } from "@/components/shell/AppShellV2";
import { SplitView } from "@/components/shell/SplitView";
import { ReassignMatterModal } from "@/components/matters/ReassignMatterModal";
import { useAuthStore } from "@/stores/auth";
import { useMatter, useMatterMeta, useMatters } from "@/hooks/useMatters";
import { useRegistryCases, useRegistryDisputes } from "@/hooks/useRegistry";
import { type Matter, type MatterSummary } from "@/api/matters";
import { cn } from "@/lib/cn";

import { rootRoute } from "./__root";
import { MatterCaseFileBody } from "./matterDetail";

/**
 * /matters — the unified Register + Matters + Case file surface.
 *
 * Per docs/architecture/_archive/ui-improvements/02-unified-surface.html.
 * Replaces /register (the discovery tree), /matters (the inspector),
 * and /awards/$matterId (the case file) with a single screen:
 *
 *  - LeftTree: Agency → Program → Matter (the hierarchical container
 *    that lets the user find what they're working on).
 *  - DetailContainer: the Inspector — a single unified surface for the
 *    selected matter. Prior mode tabs (Inspector / Case file / Activity
 *    / Audit chain) retired 2026-07-08 per Option C; Activity + Integrity
 *    are now right drawers, everything else is the main body.
 *
 * URL state:
 *  ?id=<matterId>          — selected matter
 *  ?mode=…                 — accepted for backwards compatibility; ignored.
 *
 * Old routes redirect here (in a follow-up commit). Matter ≡ Matter
 * per ADR-11; "matter" is the surface noun, "matter" remains the
 * code-side identifier (no schema change, no URL-param rename).
 */
type MatterMode = "inspector" | "case-file" | "activity" | "audit-chain";

// Retained so existing links with ?mode=… still parse; the value is no
// longer read after tab retirement (2026-07-08).
const VALID_MODES: ReadonlyArray<MatterMode> = [
  "inspector",
  "case-file",
  "activity",
  "audit-chain",
];

export type StageFacet =
  | "awaiting_owner"
  | "in_progress"
  | "awaiting_response"
  | "cleared";
const VALID_STAGES: ReadonlyArray<StageFacet> = [
  "awaiting_owner",
  "in_progress",
  "awaiting_response",
  "cleared",
];

export type OwnerFacet = "mine" | "team" | "unassigned";
const VALID_OWNERS: ReadonlyArray<OwnerFacet> = ["mine", "team", "unassigned"];

/** Read a comma-separated facet param and keep only known values.
 *  Empty / all-invalid inputs collapse to `undefined` so the URL stays
 *  clean when no facet is active. */
function parseCsvFacet<T extends string>(
  raw: unknown,
  valid: ReadonlyArray<T>,
): T[] {
  if (typeof raw !== "string" || !raw) return [];
  return raw
    .split(",")
    .filter((s): s is T => (valid as ReadonlyArray<string>).includes(s));
}

export const mattersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/matters",
  validateSearch: (search: Record<string, unknown>): {
    id?: string;
    mode?: MatterMode;
    decision?: string;
    q?: string;
    // CSV form in the URL so callers can pass strings without the
    // TanStack Router param-type friction. Decoded to arrays inside
    // MattersPage via parseCsvFacet.
    stage?: string;
    owner?: string;
  } => {
    const id = typeof search.id === "string" ? search.id : undefined;
    const m =
      typeof search.mode === "string" && (VALID_MODES as string[]).includes(search.mode)
        ? (search.mode as MatterMode)
        : undefined;
    const decision =
      typeof search.decision === "string" ? search.decision : undefined;
    const q =
      typeof search.q === "string" && search.q.trim() ? search.q : undefined;
    const stageCsv =
      typeof search.stage === "string" && search.stage ? search.stage : undefined;
    const ownerCsv =
      typeof search.owner === "string" && search.owner ? search.owner : undefined;
    return { id, mode: m, decision, q, stage: stageCsv, owner: ownerCsv };
  },
  // Auth gate: __root.tsx redirects anonymous users on any non-public
  // path, so no beforeLoad needed here.
  component: MattersPage,
});

function MattersPage() {
  const {
    id: selectedId,
    mode: modeParam,
    decision: decisionParam,
    q: qParam,
    stage: stageParam,
    owner: ownerParam,
  } = mattersRoute.useSearch();
  const navigate = useNavigate();
  const currentMode: MatterMode = modeParam ?? "inspector";
  const q = qParam ?? "";
  const stage: StageFacet[] = parseCsvFacet(stageParam, VALID_STAGES);
  const owner: OwnerFacet[] = parseCsvFacet(ownerParam, VALID_OWNERS);

  const csvOrUndef = (arr: readonly string[]): string | undefined =>
    arr.length > 0 ? arr.join(",") : undefined;

  const baseFacetSearch = {
    stage: csvOrUndef(stage),
    owner: csvOrUndef(owner),
  };

  const setSelected = (id: string | null, mode?: MatterMode) =>
    void navigate({
      to: "/matters",
      search: {
        id: id ?? undefined,
        mode: mode ?? (id ? currentMode : undefined),
        q: q || undefined,
        ...baseFacetSearch,
      },
    });
  const setDecision = (decisionId: string | null) =>
    void navigate({
      to: "/matters",
      search: {
        id: selectedId,
        mode: "case-file",
        decision: decisionId ?? undefined,
        q: q || undefined,
        ...baseFacetSearch,
      },
    });
  const setQ = (next: string) =>
    void navigate({
      to: "/matters",
      search: {
        id: selectedId,
        mode: modeParam,
        decision: decisionParam,
        q: next || undefined,
        ...baseFacetSearch,
      },
    });
  const setStage = (next: StageFacet[]) =>
    void navigate({
      to: "/matters",
      search: {
        id: selectedId,
        mode: modeParam,
        decision: decisionParam,
        q: q || undefined,
        stage: csvOrUndef(next),
        owner: baseFacetSearch.owner,
      },
    });
  const setOwner = (next: OwnerFacet[]) =>
    void navigate({
      to: "/matters",
      search: {
        id: selectedId,
        mode: modeParam,
        decision: decisionParam,
        q: q || undefined,
        stage: baseFacetSearch.stage,
        owner: csvOrUndef(next),
      },
    });
  const clearFacets = () =>
    void navigate({
      to: "/matters",
      search: {
        id: selectedId,
        mode: modeParam,
        decision: decisionParam,
        q: q || undefined,
      },
    });
  // Breadcrumb scope handlers — clear the selected matter and set the
  // tree filter so the user lands on a scoped tree view instead of the
  // empty welcome screen.
  const scopeTo = (needle: string) =>
    void navigate({
      to: "/matters",
      search: { q: needle || undefined },
    });
  const clearAll = () =>
    void navigate({ to: "/matters", search: {} });

  return (
    <AppShellV2>
      <SplitView
        left={
          <MatterTree
            selectedId={selectedId ?? null}
            onSelect={(id) => setSelected(id)}
            q={q}
            onQChange={setQ}
            stage={stage}
            onStageChange={setStage}
            owner={owner}
            onOwnerChange={setOwner}
            onClearFacets={clearFacets}
          />
        }
      >
        {selectedId ? (
          <MatterDetail
            matterId={selectedId}
            onClearSelection={clearAll}
            onScopeTo={scopeTo}
            expandedDecisionId={decisionParam ?? null}
            onExpandDecision={setDecision}
          />
        ) : (
          <MattersOverview
            filter={q}
            onClearFilter={q ? clearAll : undefined}
          />
        )}
      </SplitView>
    </AppShellV2>
  );
}

/* ─── Left tree ─────────────────────────────────────────────────────── */

type TreeTab = "matters" | "cases" | "disputes";

export function MatterTree({
  selectedId,
  onSelect,
  q,
  onQChange,
  stage = [],
  onStageChange,
  owner = [],
  onOwnerChange,
  onClearFacets,
  initialTab = "matters",
}: {
  selectedId: string | null;
  onSelect: (id: string) => void;
  q: string;
  onQChange: (q: string) => void;
  /** Multi-select facets. Empty array = "no filter on this axis." */
  stage?: StageFacet[];
  onStageChange?: (next: StageFacet[]) => void;
  owner?: OwnerFacet[];
  onOwnerChange?: (next: OwnerFacet[]) => void;
  onClearFacets?: () => void;
  /** Which tab the tree opens on. Caller can pass "disputes" to keep
   *  the rail context stable when the reader clicks a Dispute row and
   *  navigates to /disputes/:id — otherwise the tree resets to
   *  Matters and hides the tab the reader just came from.
   *
   *  This is a controlled *default*: if the caller flips it (e.g., the
   *  decisionDetail route derives it from the loaded Decision, which
   *  may resolve after first render), MatterTree tracks the new value.
   *  User clicks on tabs always win over prop changes. */
  initialTab?: TreeTab;
}) {
  const mattersQuery = useMatters();
  const metaQuery = useMatterMeta();
  const casesQuery = useRegistryCases();
  const disputesQuery = useRegistryDisputes();
  const setQ = onQChange;
  const navigate = useNavigate();
  // User's explicit tab pick — null means "follow initialTab prop."
  // This makes initialTab a controlled default that re-syncs when the
  // caller derives it from async data (fixes the /decisions/PI-* rail
  // race where the loaded Decision's number decides the tab after
  // first render).
  const [userTab, setUserTab] = useState<TreeTab | null>(null);
  const tab: TreeTab = userTab ?? initialTab;
  const setTab = (next: TreeTab) => setUserTab(next);
  const [expandedAgencies, setExpandedAgencies] = useState<
    Record<string, boolean>
  >({});
  const [expandedPrograms, setExpandedPrograms] = useState<
    Record<string, boolean>
  >({});

  const currentUser = useAuthStore((s) => s.user);
  const currentUserId = currentUser?.id ?? null;

  const items = useMemo(
    () => mattersQuery.data?.items ?? [],
    [mattersQuery.data?.items],
  );

  // Predicates per facet. A facet with an empty selection is inert —
  // it doesn't narrow. Otherwise the matter has to match at least one
  // option in each active facet (AND across facets, OR within one).
  const stagePred = (m: MatterSummary) =>
    stage.length === 0
      ? true
      : stage.includes((m.stage ?? "awaiting_owner") as StageFacet);
  const ownerPred = (m: MatterSummary) => {
    if (owner.length === 0) return true;
    const oid = m.owner_id ?? null;
    for (const o of owner) {
      if (o === "unassigned" && oid === null) return true;
      if (o === "mine" && currentUserId && oid === currentUserId) return true;
      if (o === "team" && oid !== null && oid !== currentUserId) return true;
    }
    return false;
  };
  const filteredItems = useMemo(
    () => items.filter((m) => stagePred(m) && ownerPred(m)),
    // Predicates close over the facet arrays already; listed for eslint.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [items, stage, owner, currentUserId],
  );

  // Facet counts — absolute (full item set) so the reader sees the
  // universe available in each bucket. Matches the mockup's counts.
  const facetCounts = useMemo(() => {
    const stageCounts: Record<StageFacet, number> = {
      awaiting_owner: 0,
      in_progress: 0,
      awaiting_response: 0,
      cleared: 0,
    };
    const ownerCounts: Record<OwnerFacet, number> = {
      mine: 0,
      team: 0,
      unassigned: 0,
    };
    for (const m of items) {
      const s = (m.stage ?? "awaiting_owner") as StageFacet;
      stageCounts[s] += 1;
      const oid = m.owner_id ?? null;
      if (oid === null) ownerCounts.unassigned += 1;
      else if (currentUserId && oid === currentUserId) ownerCounts.mine += 1;
      else ownerCounts.team += 1;
    }
    return { stage: stageCounts, owner: ownerCounts };
  }, [items, currentUserId]);

  const anyFacet = stage.length > 0 || owner.length > 0;
  const toggleIn = <T extends string>(arr: T[], v: T): T[] =>
    arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  // Group by agency → program → matter. Counts roll up.
  const tree = useMemo(
    () => groupTree(filteredItems, q),
    [filteredItems, q],
  );

  // Client-side filter for Signals + Disputes so the search bar above
  // the tabs filters all three tabs, not just Matters. Both lists are
  // small (dozens, not thousands) so client-side is fine.
  const filteredCases = useMemo(
    () => filterCases(casesQuery.data?.items ?? [], q),
    [casesQuery.data?.items, q],
  );
  const filteredDisputes = useMemo(
    () => filterDisputes(disputesQuery.data?.items ?? [], q),
    [disputesQuery.data?.items, q],
  );

  // Auto-expand the agency / program containing the selected matter.
  const autoExpand = useMemo(() => {
    if (!selectedId) return { agency: null, program: null };
    const match = filteredItems.find((b) => b.id === selectedId);
    if (!match) return { agency: null, program: null };
    return {
      agency: shortAgency(match.awarding_agency),
      program: `${shortAgency(match.awarding_agency)}::${match.program_id}`,
    };
  }, [filteredItems, selectedId]);

  // When a search filter is active, auto-expand every remaining node so
  // the user doesn't have to click through — the tree already narrowed
  // to just the matches; hiding them behind collapsed nodes wastes the
  // filter's work.
  const searching = q.trim().length > 0;
  const isAgencyOpen = (a: string) =>
    expandedAgencies[a] ?? (searching || autoExpand.agency === a);
  const isProgramOpen = (key: string) =>
    expandedPrograms[key] ?? (searching || autoExpand.program === key);

  return (
    <LeftTree>
      <LeftTree.Search
        placeholder="Search awards, flags, disputes, or FAIN / CFDA…"
        value={q}
        onChange={setQ}
      />
      <LeftTree.Tabs>
        <LeftTree.Tab
          current={tab === "matters"}
          count={metaQuery.data?.matters ?? items.length}
          onClick={() => setTab("matters")}
        >
          Matters
        </LeftTree.Tab>
        <LeftTree.Tab
          current={tab === "cases"}
          count={filteredCases.length}
          onClick={() => setTab("cases")}
        >
          Flags
        </LeftTree.Tab>
        <LeftTree.Tab
          current={tab === "disputes"}
          count={filteredDisputes.length}
          onClick={() => setTab("disputes")}
        >
          Disputes
        </LeftTree.Tab>
      </LeftTree.Tabs>
      {tab === "matters" && anyFacet && (
        <FacetChipStrip
          stage={stage}
          owner={owner}
          onRemoveStage={(v) => onStageChange?.(stage.filter((s) => s !== v))}
          onRemoveOwner={(v) => onOwnerChange?.(owner.filter((s) => s !== v))}
          onClearAll={onClearFacets}
        />
      )}
      <LeftTree.Body>
        {tab === "cases" && (
          <CasesList
            items={filteredCases}
            loading={casesQuery.isLoading}
            onSelect={(caseItem) =>
              void navigate({
                to: "/workflows/$workflowId/decisions/$decisionId",
                params: {
                  workflowId: caseItem.workflow_id,
                  decisionId: caseItem.id,
                },
              })
            }
          />
        )}
        {tab === "disputes" && (
          <DisputesList
            items={filteredDisputes}
            loading={disputesQuery.isLoading}
            onSelect={(d) =>
              void navigate({
                to: "/disputes/$disputeId",
                params: { disputeId: d.id },
              })
            }
          />
        )}
        {tab === "matters" && (
          <LeftTree.Section
            title="Stage"
            collapsible
            summary={stage.length > 0 ? stageSummary(stage) : undefined}
          >
            {STAGE_OPTIONS.map((opt) => (
              <LeftTree.CheckboxRow
                key={opt.value}
                dot={opt.dot}
                checked={stage.includes(opt.value)}
                count={facetCounts.stage[opt.value]}
                onToggle={() => onStageChange?.(toggleIn(stage, opt.value))}
              >
                {opt.label}
              </LeftTree.CheckboxRow>
            ))}
          </LeftTree.Section>
        )}
        {tab === "matters" && (
          <LeftTree.Section
            title="Owner"
            collapsible
            summary={owner.length > 0 ? ownerSummary(owner) : undefined}
          >
            {OWNER_OPTIONS.map((opt) => (
              <LeftTree.CheckboxRow
                key={opt.value}
                checked={owner.includes(opt.value)}
                count={facetCounts.owner[opt.value]}
                onToggle={() => onOwnerChange?.(toggleIn(owner, opt.value))}
              >
                {opt.label}
              </LeftTree.CheckboxRow>
            ))}
          </LeftTree.Section>
        )}
        {tab === "matters" && (
          <LeftTree.Section title="Agency & program">
            {tree.map((agency) => {
              const open = isAgencyOpen(agency.label);
              return (
                <div key={agency.label}>
                  <LeftTree.Node
                    level={1}
                    twist={open ? "open" : "closed"}
                    count={agency.count}
                    onClick={() =>
                      setExpandedAgencies((prev) => ({
                        ...prev,
                        [agency.label]: !open,
                      }))
                    }
                  >
                    {agency.label}
                  </LeftTree.Node>
                  {open &&
                    agency.programs.map((program) => {
                      const programKey = `${agency.label}::${program.id}`;
                      const pOpen = isProgramOpen(programKey);
                      return (
                        <div key={programKey}>
                          <LeftTree.Node
                            level={2}
                            twist={pOpen ? "open" : "closed"}
                            count={program.matters.length}
                            onClick={() =>
                              setExpandedPrograms((prev) => ({
                                ...prev,
                                [programKey]: !pOpen,
                              }))
                            }
                          >
                            {program.label}
                          </LeftTree.Node>
                          {pOpen &&
                            program.matters.map((m) => (
                              <MatterLeaf
                                key={m.id}
                                matter={m}
                                selected={m.id === selectedId}
                                onClick={() => onSelect(m.id)}
                              />
                            ))}
                        </div>
                      );
                    })}
                </div>
              );
            })}
          </LeftTree.Section>
        )}
        {tab === "matters" && tree.length === 0 && (
          <div className="px-3.5 py-6 text-[12px] text-ink-muted">
            {mattersQuery.isLoading
              ? "Loading matters…"
              : "No matters match this filter."}
          </div>
        )}
      </LeftTree.Body>
    </LeftTree>
  );
}

/* ─── Cases tab body ───────────────────────────────────────────────── */

import type { Dispute, RegistryDecisionSummary } from "@/api/registry";

const SEVERITY_DOT: Record<string, string> = {
  critical: "bg-flag",
  high: "bg-accent-warning",
  medium: "bg-ink-faint",
  low: "bg-ink-faint",
};

function CasesList({
  items,
  loading,
  onSelect,
}: {
  items: RegistryDecisionSummary[];
  loading: boolean;
  onSelect: (c: RegistryDecisionSummary) => void;
}) {
  if (loading) {
    return (
      <div className="px-3.5 py-6 text-[12px] text-ink-muted">
        Loading cases…
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="px-3.5 py-6 text-[12px] text-ink-muted">
        No signals promoted yet. Signals show up here when an
        automated detector fires on a matter and an officer promotes
        it into a governed Decision.
      </div>
    );
  }
  return (
    <ul className="py-1">
      {items.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            onClick={() => onSelect(c)}
            className="w-full px-3.5 py-2 text-left hover:bg-bg-warm transition-colors"
          >
            <div className="flex items-center gap-2">
              {c.alert?.severity && (
                <span
                  aria-hidden
                  className={cn(
                    "inline-block h-1.5 w-1.5 rounded-full shrink-0",
                    SEVERITY_DOT[c.alert.severity] ?? "bg-ink-faint",
                  )}
                />
              )}
              <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-faint">
                {c.decision_number}
              </span>
              <span className="ml-auto font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-faint">
                {c.status.replace(/_/g, " ")}
              </span>
            </div>
            <div className="mt-0.5 text-[12.5px] text-ink truncate">
              {c.title}
            </div>
            {c.alert && (
              <div className="mt-0.5 text-[11px] text-ink-soft italic truncate">
                Promoted from {c.alert.source}: {c.alert.title}
              </div>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}

/* ─── Disputes tab body ───────────────────────────────────────────── */

function DisputesList({
  items,
  loading,
  onSelect,
}: {
  items: Dispute[];
  loading: boolean;
  onSelect: (d: Dispute) => void;
}) {
  if (loading) {
    return (
      <div className="px-3.5 py-6 text-[12px] text-ink-muted">
        Loading disputes…
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="px-3.5 py-6 text-[12px] text-ink-muted">
        No disputes yet. Disputes show up here when two candidate
        identities need reconciling before an award moves.
      </div>
    );
  }
  return (
    <ul className="py-1">
      {items.map((d) => {
        const isOpen = d.status === "open";
        return (
          <li key={d.id}>
            <button
              type="button"
              onClick={() => onSelect(d)}
              className="w-full px-3.5 py-2 text-left hover:bg-bg-warm transition-colors"
            >
              <div className="flex items-center gap-2">
                <span
                  aria-hidden
                  className={cn(
                    "inline-block h-1.5 w-1.5 rounded-full shrink-0",
                    isOpen ? "bg-accent-warning" : "bg-ink-faint",
                  )}
                />
                <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-ink-faint">
                  {isOpen ? "open" : "resolved"}
                </span>
              </div>
              <div className="mt-0.5 text-[12.5px] text-ink truncate">
                {d.subject_name}
              </div>
              <div className="mt-0.5 text-[11px] text-ink-soft italic truncate">
                {sourceOfCandidate(d.candidate_a)} ⇄ {sourceOfCandidate(d.candidate_b)}
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function sourceOfCandidate(c: Record<string, unknown>): string {
  const s = (c["source"] as string | undefined) ?? "candidate";
  return s;
}

/* ─── Detail (right pane) ───────────────────────────────────────────── */

function MatterDetail({
  matterId,
  onClearSelection,
  onScopeTo,
  expandedDecisionId,
  onExpandDecision,
}: {
  matterId: string;
  onClearSelection: () => void;
  /** Called by the agency / program breadcrumb crumbs. Clears the
   *  selected matter and applies the given needle as the tree
   *  filter so the reader lands on a scoped list. */
  onScopeTo: (needle: string) => void;
  expandedDecisionId: string | null;
  onExpandDecision: (decisionId: string | null) => void;
}) {
  const matterQuery = useMatter(matterId);
  const matter = matterQuery.data;
  const [reassignOpen, setReassignOpen] = useState(false);
  // Two right drawers, single-open at a time. Toggling one closes the
  // other so the shell doesn't stack modal backdrops.
  const [activeDrawer, setActiveDrawer] = useState<
    "activity" | "integrity" | null
  >(null);
  const toggleDrawer = (which: "activity" | "integrity") =>
    setActiveDrawer((cur) => (cur === which ? null : which));

  // Title / subtitle / breadcrumb derived from the matter. Prefer the
  // deepest non-federal node name (the recipient or subrecipient — the
  // actual subject of the matter); fall back to summary helpers when
  // matter.nodes is sparse.
  const title = matter
    ? matterTitleFromMatter(matter)
    : matterQuery.isLoading
      ? "Loading…"
      : "Matter";
  const subtitle = matter ? buildSubtitle(matter) : "";

  const breadcrumb = matter ? (
    <Breadcrumb
      crumbs={[
        { label: "All matters", onClick: onClearSelection },
        {
          label: shortAgency(matter.awarding_agency),
          onClick: () => onScopeTo(shortAgency(matter.awarding_agency)),
        },
        {
          label: matter.program_id.toUpperCase(),
          onClick: () => onScopeTo(matter.program_id),
        },
        { label: matterTitleFromMatter(matter), current: true },
      ]}
    />
  ) : (
    <Breadcrumb
      crumbs={[
        { label: "All matters", onClick: onClearSelection },
        { label: "…", current: true },
      ]}
    />
  );

  const actions = matter ? (
    <>
      <Button
        variant="ghost"
        onClick={() => setReassignOpen(true)}
      >
        <i className="ti ti-user-share text-[16px]" />
        Reassign
      </Button>
      <Button
        variant="ghost"
        onClick={() =>
          window.open(
            `/api/matters/${matter.id}/case-file`,
            "_blank",
            "noopener,noreferrer",
          )
        }
      >
        <i className="ti ti-file-export text-[16px]" />
        Export
      </Button>
    </>
  ) : null;

  return (
    <DetailContainer
      breadcrumb={breadcrumb}
      eyebrow={
        matter && (
          <span className="inline-flex items-center gap-2">
            <span className="text-navy">Inspector</span>
            <span
              aria-hidden
              className="inline-block w-1 h-1 rounded-full bg-ink-faint"
            />
            <span>Formal record of a federal-award matter</span>
          </span>
        )
      }
      title={title}
      subtitle={subtitle}
      actions={actions}
    >
      {matterQuery.isLoading && !matter && (
        <div className="px-6 py-8 text-[13px] text-ink-muted">
          Loading matter…
        </div>
      )}
      {matterQuery.isError && (
        <div className="px-6 py-8 text-[13px] text-flag">
          Couldn't load this matter.
        </div>
      )}
      {matter && (
        <MatterCaseFileBody
          matterId={matterId}
          hideChrome
          expandedDecisionId={expandedDecisionId}
          onExpandDecision={onExpandDecision}
        />
      )}
      {matter && (
        <ReassignMatterModal
          open={reassignOpen}
          onClose={() => setReassignOpen(false)}
          matter={matter}
        />
      )}
      {matter && (
        <>
          <InspectorRail active={activeDrawer} onToggle={toggleDrawer} />
          <ActivityDrawer
            matterId={matter.id}
            open={activeDrawer === "activity"}
            onClose={() => setActiveDrawer(null)}
          />
          <IntegrityDrawer
            matterId={matter.id}
            open={activeDrawer === "integrity"}
            onClose={() => setActiveDrawer(null)}
          />
        </>
      )}
    </DetailContainer>
  );
}


/* ─── Overview when no matter is selected ───────────────────────────── */

function MattersOverview({
  filter,
  onClearFilter,
}: {
  filter?: string;
  onClearFilter?: () => void;
}) {
  const metaQuery = useMatterMeta();
  const meta = metaQuery.data;
  const user = useAuthStore((s) => s.user);
  return (
    <div className="px-8 py-10 max-w-[720px]">
      {filter ? (
        <>
          <div className="mb-3 flex flex-wrap items-baseline gap-2 text-[12px] uppercase tracking-[0.06em] font-mono text-ink-faint">
            <span>Scoped to</span>
            <span className="rounded-sm bg-navy-soft px-2 py-0.5 text-navy-deep normal-case tracking-normal">
              {filter}
            </span>
            {onClearFilter && (
              <button
                type="button"
                onClick={onClearFilter}
                className="text-navy hover:underline normal-case tracking-normal"
              >
                clear scope
              </button>
            )}
          </div>
          <h1 className="text-[22px] font-display font-medium tracking-[-0.01em] text-ink mb-1">
            Matters filtered to {filter}
          </h1>
          <p className="text-[14px] text-ink-soft mb-6">
            The tree on the left shows only matters that match this scope.
            Pick one to open its fund flow, signals, decisions, and audit
            chain.
          </p>
        </>
      ) : (
        <>
          <h1 className="text-[22px] font-display font-medium tracking-[-0.01em] text-ink mb-1">
            Welcome{user?.name ? `, ${user.name.split(" ")[0]}` : ""}.
          </h1>
          <p className="text-[14px] text-ink-soft mb-6">
            Pick a matter from the tree on the left to see its fund flow,
            signals, decisions, and audit chain — or jump straight to{" "}
            <Link
              to="/inbox"
              className="text-navy underline underline-offset-2 hover:text-navy-deep"
            >
              your inbox
            </Link>
            .
          </p>
        </>
      )}
      {meta && (
        <div className="grid grid-cols-3 gap-0 border-[0.5px] border-rule rounded-md overflow-hidden">
          <OverviewStat label="Matters" value={meta.matters} />
          <OverviewStat
            label="Exposure"
            value={formatExposure(meta.exposure)}
          />
          <OverviewStat label="Open signals" value={meta.signals} />
        </div>
      )}
    </div>
  );
}

function OverviewStat({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div className="px-5 py-4 border-r-[0.5px] border-rule-faint last:border-r-0">
      <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint mb-1">
        {label}
      </div>
      <div className="text-[22px] font-display font-medium tracking-[-0.01em] text-ink">
        {value}
      </div>
    </div>
  );
}

/* ─── Section card helper ───────────────────────────────────────────── */

/* ─── Helpers ───────────────────────────────────────────────────────── */

type Program = {
  id: string;
  label: string;
  matters: MatterSummary[];
};

type Agency = {
  label: string;
  count: number;
  programs: Program[];
};

function groupTree(items: MatterSummary[], q: string): Agency[] {
  const needle = q.trim().toLowerCase();
  const passes = (b: MatterSummary) => {
    if (!needle) return true;
    // Hay includes:
    //  · awarding agency + program_id
    //  · search_labels (recipient display_names — also feeds matterLabel)
    //  · search_terms  (decision numbers)
    //  · every path_preview label (state names + federal + recipient) so
    //    "Georgia" or "Ohio" finds matters they touch even though those
    //    names aren't part of the recipient-name list.
    const hay = [
      b.awarding_agency,
      b.program_id,
      ...(b.search_labels ?? []),
      ...(b.search_terms ?? []),
      ...((b.path_preview ?? []).map((p) => p.label)),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(needle);
  };
  const filtered = items.filter(passes);
  const byAgency = new Map<string, Map<string, MatterSummary[]>>();
  for (const b of filtered) {
    const a = shortAgency(b.awarding_agency);
    const p = b.program_id;
    if (!byAgency.has(a)) byAgency.set(a, new Map());
    const programs = byAgency.get(a)!;
    if (!programs.has(p)) programs.set(p, []);
    programs.get(p)!.push(b);
  }
  return Array.from(byAgency.entries())
    .map(([agency, programs]) => ({
      label: agency,
      count: Array.from(programs.values()).reduce(
        (acc, m) => acc + m.length,
        0,
      ),
      programs: Array.from(programs.entries())
        .map(([id, matters]) => ({
          id,
          label: id.toUpperCase(),
          matters: matters.sort((a, b) =>
            (b.amount_obligated ?? "").localeCompare(
              a.amount_obligated ?? "",
            ),
          ),
        }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    }))
    .sort((a, b) => b.count - a.count);
}

function filterCases(
  items: RegistryDecisionSummary[],
  q: string,
): RegistryDecisionSummary[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((c) => {
    const hay = [
      c.decision_number,
      c.title,
      c.workflow_id,
      c.alert?.title ?? "",
      c.alert?.source ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(needle);
  });
}

function filterDisputes(items: Dispute[], q: string): Dispute[] {
  const needle = q.trim().toLowerCase();
  if (!needle) return items;
  return items.filter((d) => {
    const hay = [
      d.subject_name,
      d.notes ?? "",
      sourceOfCandidate(d.candidate_a),
      sourceOfCandidate(d.candidate_b),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(needle);
  });
}

/* ─── Facet option catalog + label helpers ────────────────────────── */

type StageDot = "muted" | "amber" | "green" | "flag";

const STAGE_OPTIONS: {
  value: StageFacet;
  label: string;
  dot: StageDot;
}[] = [
  { value: "awaiting_owner", label: "Awaiting owner", dot: "muted" },
  { value: "in_progress", label: "In progress", dot: "amber" },
  { value: "awaiting_response", label: "Awaiting response", dot: "amber" },
  { value: "cleared", label: "Cleared", dot: "green" },
];

const OWNER_OPTIONS: { value: OwnerFacet; label: string }[] = [
  { value: "mine", label: "Mine" },
  { value: "team", label: "Team" },
  { value: "unassigned", label: "Unassigned" },
];

function stageSummary(values: StageFacet[]): string {
  if (values.length === 1) {
    return STAGE_OPTIONS.find((o) => o.value === values[0])?.label ?? "";
  }
  return `${values.length} selected`;
}
function ownerSummary(values: OwnerFacet[]): string {
  if (values.length === 1) {
    return OWNER_OPTIONS.find((o) => o.value === values[0])?.label ?? "";
  }
  return `${values.length} selected`;
}
function stageLabel(value: StageFacet): string {
  return STAGE_OPTIONS.find((o) => o.value === value)?.label ?? value;
}
function ownerLabel(value: OwnerFacet): string {
  return OWNER_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

/** Two-letter initials from a display name, uppercase. "Jamie Kim" → "JK". */
function initialsOf(name: string | null | undefined): string {
  if (!name) return "";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const STAGE_DOT_CLASS: Record<StageFacet, string> = {
  awaiting_owner: "bg-ink-faint/40",
  in_progress: "bg-accent-warning",
  awaiting_response: "bg-accent-warning",
  cleared: "bg-cleared",
};

/* ─── Rail leaf + facet chip strip ────────────────────────────────── */

function MatterLeaf({
  matter,
  selected,
  onClick,
}: {
  matter: MatterSummary;
  selected: boolean;
  onClick: () => void;
}) {
  // Check ALL open signals — a matter can carry tier-skip alongside
  // other signals (identity, flow_graph), and the highest-severity
  // primary might be one of those. The chip means "this matter has a
  // tier-skip problem," which is true whenever any signal names it.
  const isTierSkip = (matter.signals ?? []).some(
    (s) => s.kind === "tier_skip" || s.source === "tier_skip",
  );
  const amount = formatExposure(matter.amount_obligated);
  const stage = (matter.stage ?? "awaiting_owner") as StageFacet;
  const stageText = stageLabel(stage).toUpperCase();
  const ownerInit = initialsOf(matter.owner_name);
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "w-full pr-3.5 py-1.5 text-left transition-colors",
        selected
          ? "pl-[40px] bg-navy-soft/40 border-l-2 border-navy"
          : "pl-[42px] hover:bg-bg-warm",
      )}
    >
      <div
        className={cn(
          "flex items-center gap-1.5 text-[12.5px]",
          selected ? "text-ink" : "text-ink-soft",
        )}
      >
        <span className="flex-1 truncate">{matterLabel(matter)}</span>
        {isTierSkip && (
          <span className="shrink-0 text-[9px] font-medium tracking-[0.08em] uppercase px-1.5 py-0.5 rounded-sm border-[0.5px] border-flag/60 bg-flag/10 text-flag">
            tier-skip
          </span>
        )}
      </div>
      <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[10.5px] text-ink-faint">
        <span
          aria-hidden
          className={cn("w-1.5 h-1.5 rounded-full", STAGE_DOT_CLASS[stage])}
        />
        <span className="uppercase tracking-[0.04em]">{stageText}</span>
        <span className="text-ink-faint/60">·</span>
        <span>{amount}</span>
        {ownerInit && (
          <>
            <span className="text-ink-faint/60">·</span>
            <span>{ownerInit}</span>
          </>
        )}
      </div>
    </button>
  );
}

function FacetChipStrip({
  stage,
  owner,
  onRemoveStage,
  onRemoveOwner,
  onClearAll,
}: {
  stage: StageFacet[];
  owner: OwnerFacet[];
  onRemoveStage: (v: StageFacet) => void;
  onRemoveOwner: (v: OwnerFacet) => void;
  onClearAll?: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 px-3.5 py-2 border-b-[0.5px] border-rule bg-navy-soft/30">
      {stage.map((v) => (
        <FacetChip
          key={`stage-${v}`}
          label="Stage"
          value={stageLabel(v)}
          onClear={() => onRemoveStage(v)}
        />
      ))}
      {owner.map((v) => (
        <FacetChip
          key={`owner-${v}`}
          label="Owner"
          value={ownerLabel(v)}
          onClear={() => onRemoveOwner(v)}
        />
      ))}
      {onClearAll && (
        <button
          type="button"
          onClick={onClearAll}
          className="ml-auto text-[10.5px] text-navy hover:text-navy-deep"
        >
          Clear
        </button>
      )}
    </div>
  );
}

function FacetChip({
  label,
  value,
  onClear,
}: {
  label: string;
  value: string;
  onClear: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border-[0.5px] border-navy/20 bg-paper px-1.5 py-0.5 text-[10.5px] text-navy">
      <span className="text-ink-faint">{label}</span>
      <span>{value}</span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onClear();
        }}
        aria-label={`Clear ${label} facet`}
        className="ml-0.5 rounded-full text-ink-faint hover:text-ink"
      >
        ×
      </button>
    </span>
  );
}

function matterLabel(b: MatterSummary): string {
  // Tree label — works on the summary shape. Use search_labels first
  // (every recipient name on the matter, prime + all subs) — the
  // deepest non-agency entry is the subject of the matter.
  const labels = (b.search_labels ?? []).filter(
    (s) => s && s !== b.awarding_agency,
  );
  if (labels.length > 0) return labels[labels.length - 1];
  // Fall back to path_preview's deepest non-federal node.
  const last = b.path_preview?.[b.path_preview.length - 1];
  if (last && last.tier !== "federal") return last.label;
  return b.awarding_agency;
}

function matterTitleFromMatter(b: Matter): string {
  // Detail title — has access to the full node list. Pick the deepest
  // active non-federal node's participant name. This is the "matter is
  // about" identity (the recipient or subrecipient receiving the money).
  const active = (b.nodes ?? []).filter((n) => !n.removed_at);
  // Walk tiers deepest-first: recipient > state > federal.
  for (const tier of ["recipient", "state"] as const) {
    const candidates = active.filter(
      (n) => n.tier === tier && n.participant_org_name,
    );
    if (candidates.length > 0) {
      // Deepest = node with no children in the active set.
      const childIds = new Set(active.map((n) => n.parent_node_id));
      const leaf = candidates.find((n) => !childIds.has(n.id));
      const pick = leaf ?? candidates[candidates.length - 1];
      if (pick.participant_org_name) return pick.participant_org_name;
    }
  }
  // No participant nodes — fall back to the summary heuristic.
  return matterLabel(b);
}

function buildSubtitle(b: Matter): string {
  // Award-identification-at-a-glance. Reads the details examiners want to
  // see without opening a card: agency · program · period · $ obligated ·
  // originating decision. CFDA + FAIN will slot in when those columns
  // land on the Matter model (tracked as P52).
  const parts: string[] = [shortAgency(b.awarding_agency), b.program_id.toUpperCase()];
  if (b.period_label) parts.push(b.period_label);
  if (b.amount_obligated) {
    const n = Number(b.amount_obligated);
    if (Number.isFinite(n)) {
      parts.push(
        `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })} obligated`,
      );
    }
  }
  const dec = b.originating_decision?.decision_number;
  if (dec) parts.push(`originating ${dec}`);
  return parts.join(" · ");
}


function shortAgency(name: string): string {
  if (!name) return "";
  // Strip "United States " prefix; clip very long names by major-word.
  const stripped = name.replace(/^United States /i, "");
  if (stripped.length <= 32) return stripped;
  // "Department of Health and Human Services" → "HHS" if we can shrink.
  const ABBR: Record<string, string> = {
    "Department of Housing and Urban Development": "HUD",
    "Department of Health and Human Services": "HHS",
    "Department of Agriculture": "USDA",
    "Department of Defense": "DoD",
    "Department of State": "Dept. of State",
  };
  return ABBR[stripped] ?? stripped;
}

function formatExposure(v: string | number | null): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "—";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1).replace(/\.0$/, "")}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

