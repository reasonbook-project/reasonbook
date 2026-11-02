// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { create } from "zustand";

/**
 * In-product help drawer state.
 *
 * Lifted out of AppShell so any component can open the drawer to a
 * specific article without prop-drilling — primarily used by
 * `<HelpLink topic="…">` anchors planted at empty-states, paywalls,
 * and confusing affordances, plus the `?` keyboard shortcut bound in
 * AppShell.
 *
 * `articleId` is null when the drawer should open to the index. When
 * set, the drawer renders that specific article directly. Closing
 * the drawer clears both fields so the next open starts fresh.
 */
type HelpState = {
  open: boolean;
  /** Article id to open directly. Null means show the index. */
  articleId: string | null;
  /** Open the drawer to the index. */
  openDrawer: () => void;
  /** Open the drawer scrolled to a specific article. */
  openArticle: (id: string) => void;
  /** Close the drawer and reset article selection. */
  closeDrawer: () => void;
};

export const useHelpStore = create<HelpState>((set) => ({
  open: false,
  articleId: null,
  openDrawer: () => set({ open: true, articleId: null }),
  openArticle: (id) => set({ open: true, articleId: id }),
  closeDrawer: () => set({ open: false, articleId: null }),
}));
