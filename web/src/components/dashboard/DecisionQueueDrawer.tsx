// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * DecisionQueueDrawer — composite over <Drawer> + queue endpoint.
 *
 * Owns:
 *   - The header (title + active filter chips + count badge + close)
 *   - The body (filter toolbar + row list OR All-clear empty state)
 *   - The category filter swap (no drawer close/reopen per Flow 3)
 *   - Row click → navigate to /workflows/{wid}/decisions/{id} + close
 *
 * Stays narrow on purpose: the underlying <Drawer> primitive handles
 * focus trap, scroll lock, ESC / backdrop dismissal, and aria wiring.
 * The data layer (filter state + URL sync) is in useDrawer. The fetch
 * layer is useDecisionQueue. This file is glue.
 */

import { useNavigate } from "@tanstack/react-router";
import { useCallback } from "react";

import { Drawer } from "@/components/ds/Drawer";
import { HelpLink } from "@/components/help/HelpLink";
import { useDecisionQueue } from "@/hooks/useDecisionQueue";
import { cn } from "@/lib/cn";

import { DecisionQueueEmpty } from "./DecisionQueueEmpty";
import { DecisionQueueList } from "./DecisionQueueList";

import type { QueueCategory, QueueDecision } from "@/api/decisionQueue";
import type { DrawerFilter } from "@/hooks/useDrawer";

export type DecisionQueueDrawerProps = {
  open: boolean;
  onClose: () => void;
  /** Current filter when open; null when closed. */
  filter: DrawerFilter | null;
  /** Called by the in-drawer category toolbar — swaps content in-place. */
  onChangeFilter: (filter: DrawerFilter) => void;
};

const CATEGORY_LABEL: Record<QueueCategory, string> = {
  compliance: "Compliance",
  credit: "Credit",
  ops: "Ops",
};

export function DecisionQueueDrawer({
  open,
  onClose,
  filter,
  onChangeFilter,
}: DecisionQueueDrawerProps) {
  const navigate = useNavigate();

  // Only fetch when the drawer is actually open. When `filter` is null
  // we pass a placeholder so the hook's queryKey is stable; `enabled`
  // guards the network call.
  const effectiveFilter: DrawerFilter = filter ?? { status: "at_risk" };
  const query = useDecisionQueue(effectiveFilter, { enabled: open });

  const handleSelectDecision = useCallback(
    (decision: QueueDecision) => {
      onClose();
      void navigate({
        to: "/workflows/$workflowId/decisions/$decisionId",
        params: {
          workflowId: decision.workflow_id,
          decisionId: decision.id,
        },
      });
    },
    [navigate, onClose],
  );

  const handleCategoryChange = useCallback(
    (category: QueueCategory | null) => {
      onChangeFilter({
        status: effectiveFilter.status,
        ...(category ? { category } : {}),
      });
    },
    [effectiveFilter.status, onChangeFilter],
  );

  const handleShowAllOpen = useCallback(() => {
    // Empty-state CTA per spec §"Flow 5" — widens to status=open and
    // clears the category. Keeps the user in the drawer (D5 + open
    // question 4 answer).
    onChangeFilter({ status: "open" });
  }, [onChangeFilter]);

  const titleId = "decision-queue-drawer-title";
  const ariaLabel = filter?.category
    ? `Decision queue — ${filter.status === "at_risk" ? "at risk" : "open"}, ${CATEGORY_LABEL[filter.category]}`
    : `Decision queue — ${filter?.status === "open" ? "open" : "at risk"}`;

  const isAtRisk = effectiveFilter.status === "at_risk";
  const data = query.data;
  const showEmpty = Boolean(
    data && isAtRisk && data.filtered_count === 0 && data.posture_context,
  );

  return (
    <Drawer open={open} onClose={onClose} ariaLabel={ariaLabel}>
      <DrawerHeader
        titleId={titleId}
        status={effectiveFilter.status}
        category={effectiveFilter.category ?? null}
        onClearCategory={() =>
          onChangeFilter({ status: effectiveFilter.status })
        }
        onClose={onClose}
      />

      {showEmpty && data?.posture_context ? (
        <DecisionQueueEmpty
          posture={data.posture_context}
          category={effectiveFilter.category ?? null}
          onShowAllOpen={handleShowAllOpen}
        />
      ) : (
        <DecisionQueueList
          decisions={data?.decisions ?? []}
          filteredCount={data?.filtered_count ?? 0}
          totalCount={data?.total_count ?? 0}
          activeCategory={effectiveFilter.category ?? null}
          onCategoryChange={handleCategoryChange}
          onSelectDecision={handleSelectDecision}
          isLoading={query.isLoading}
          errorMessage={query.error ? (query.error as Error).message : null}
        />
      )}
    </Drawer>
  );
}

function DrawerHeader({
  titleId,
  status,
  category,
  onClearCategory,
  onClose,
}: {
  titleId: string;
  status: "at_risk" | "open";
  category: QueueCategory | null;
  onClearCategory: () => void;
  onClose: () => void;
}) {
  return (
    <header className="flex items-start justify-between gap-3 border-b border-rule-soft px-5 py-4">
      <div className="min-w-0 flex-1">
        <div className="text-[10px] uppercase tracking-[0.08em] text-ink-faint">
          Decision queue
        </div>
        <div className="mt-1 flex items-center gap-2">
          <h2
            id={titleId}
            className="text-[16px] font-medium text-ink"
          >
            {status === "at_risk" ? "At risk" : "All open"}
          </h2>
          <HelpLink
            topic="dashboard/at-risk-drilldown"
            variant="popover"
            ariaLabel="Help: at-risk drilldown"
            onLaunchFullArticle={onClose}
          />
        </div>
        {category && (
          <span className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-navy bg-navy-tint px-2.5 py-0.5 text-[11px] font-medium text-navy-deep">
            {CATEGORY_LABEL[category]}
            <button
              type="button"
              onClick={onClearCategory}
              aria-label={`Clear ${CATEGORY_LABEL[category]} filter`}
              className="text-navy-deep/70 hover:text-navy-deep"
            >
              ×
            </button>
          </span>
        )}
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close decision queue"
        className={cn(
          "grid h-8 w-8 shrink-0 place-items-center rounded-md text-ink-faint transition-colors",
          "hover:bg-rule-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-navy",
        )}
      >
        <span aria-hidden="true" className="text-[22px] leading-none">
          ×
        </span>
      </button>
    </header>
  );
}
