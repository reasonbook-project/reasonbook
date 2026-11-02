// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * useDrawer — drawer open/close + URL sync for the dashboard queue drawer.
 *
 * Reads the queue + category from the dashboard route's search params
 * (?queue=at_risk&category=compliance) so an open-drawer URL is shareable
 * and the back button does what the user expects. All writes use
 * ``replace: true`` so opening / closing / changing filters doesn't
 * pollute browser history with one entry per click.
 *
 * Scoped to ``dashboardRoute`` because that's the only surface that
 * mounts the queue drawer in Phase 3. If a future surface (e.g. an
 * inbox-level "review queue" affordance) wants the same drawer it gets
 * its own thin hook against its own route id.
 */

import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback } from "react";

import { dashboardRoute } from "@/routes/dashboard";

import type { QueueCategory, QueueStatus } from "@/api/decisionQueue";

export type DrawerFilter = {
  status: QueueStatus;
  category?: QueueCategory;
};

export type UseDrawerReturn = {
  isOpen: boolean;
  filter: DrawerFilter | null;
  open: (filter: DrawerFilter) => void;
  close: () => void;
  setFilter: (filter: DrawerFilter) => void;
};

export function useDrawer(): UseDrawerReturn {
  const search = useSearch({ from: dashboardRoute.id });
  const navigate = useNavigate();

  const filter: DrawerFilter | null = search.queue
    ? {
        status: search.queue,
        ...(search.category ? { category: search.category } : {}),
      }
    : null;

  const open = useCallback(
    (next: DrawerFilter) => {
      void navigate({
        to: dashboardRoute.to,
        search: {
          queue: next.status,
          category: next.category,
        },
        replace: true,
      });
    },
    [navigate],
  );

  const close = useCallback(() => {
    void navigate({
      to: dashboardRoute.to,
      search: {
        queue: undefined,
        category: undefined,
      },
      replace: true,
    });
  }, [navigate]);

  // Swap filter without opening / closing — used by the in-drawer category
  // toolbar (Flow 3: content swap, no drawer reopen).
  const setFilter = open;

  return {
    isOpen: filter !== null,
    filter,
    open,
    close,
    setFilter,
  };
}
