// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { create } from "zustand";

/**
 * Multi-select state for the Inbox per Phase 8.5 bulk-ops.
 *
 * Lives outside the Inbox component so the BulkActionBar (rendered as a
 * sticky banner near the top) shares the same selection set without
 * prop-drilling. Selections clear automatically when the user changes
 * the workflow filter or scope — keeping a stale selection across a
 * filter change creates the worst class of bulk-ops bug.
 *
 * `Set<string>` for O(1) toggle/has lookups; React re-renders by
 * replacing the whole set so referential equality stays correct.
 */
type InboxSelectionState = {
  selected: Set<string>;
  toggle: (id: string) => void;
  add: (id: string) => void;
  remove: (id: string) => void;
  clear: () => void;
  setMany: (ids: string[]) => void;
};

export const useInboxSelectionStore = create<InboxSelectionState>((set) => ({
  selected: new Set<string>(),
  toggle: (id) =>
    set((state) => {
      const next = new Set(state.selected);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selected: next };
    }),
  add: (id) =>
    set((state) => {
      if (state.selected.has(id)) return state;
      const next = new Set(state.selected);
      next.add(id);
      return { selected: next };
    }),
  remove: (id) =>
    set((state) => {
      if (!state.selected.has(id)) return state;
      const next = new Set(state.selected);
      next.delete(id);
      return { selected: next };
    }),
  clear: () => set({ selected: new Set<string>() }),
  setMany: (ids) => set({ selected: new Set(ids) }),
}));
