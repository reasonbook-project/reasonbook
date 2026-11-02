// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";

import { Drawer } from "@/components/ds/Drawer";
import { HelpArticle } from "@/components/help/HelpArticle";
import {
  type HelpArticleMeta,
  type HelpSurface,
  getArticleById,
  groupArticles,
  searchArticles,
} from "@/lib/helpArticles";
import { cn } from "@/lib/cn";
import { useHelpStore } from "@/stores/help";

/**
 * In-product help drawer. Right-side drawer (480px) hosting an article
 * index + inline article reader.
 *
 * Open/close state is owned by `useHelpStore` so any component can
 * dispatch from anywhere — primarily `<HelpLink topic="…">` anchors,
 * the Rail's "Help" link, and the `?` keyboard shortcut bound in
 * AppShell.
 *
 * Index shape: articles are grouped by surface (Onboarding, Inbox,
 * Decisions, etc.) per HELP_SURFACE_ORDER. Each surface renders as a
 * collapsible category — click the header to toggle. Collapse state
 * persists across drawer open/close within a session via React state;
 * an empty search query restores the full grouped view, a non-empty
 * query expands every group with matches so results stay visible.
 *
 * Closing the drawer clears the article selection via the store so
 * the next open starts at the index. The selection is intentionally
 * not URL-routed — the help drawer should not interrupt the operator's
 * primary navigation context.
 */
export function HelpDrawer() {
  const open = useHelpStore((s) => s.open);
  const articleId = useHelpStore((s) => s.articleId);
  const closeDrawer = useHelpStore((s) => s.closeDrawer);

  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Per-surface collapse state. Surfaces not in the set are expanded
  // (default open). Collapsed surfaces appear in the set.
  const [collapsedSurfaces, setCollapsedSurfaces] = useState<Set<HelpSurface>>(
    () => new Set(),
  );

  useEffect(() => {
    if (open && articleId) {
      setSelectedId(articleId);
    }
  }, [open, articleId]);

  useEffect(() => {
    if (!open) {
      setSelectedId(null);
      setQuery("");
    }
  }, [open]);

  const filtered = useMemo(() => searchArticles(query), [query]);
  const grouped = useMemo(() => groupArticles(filtered), [filtered]);
  const isSearching = query.trim().length > 0;

  const selected: HelpArticleMeta | undefined = useMemo(() => {
    if (!selectedId) return undefined;
    return (
      filtered.find((a) => a.id === selectedId) ??
      getArticleById(selectedId) ??
      undefined
    );
  }, [filtered, selectedId]);

  const toggleSurface = (surface: HelpSurface) => {
    setCollapsedSurfaces((prev) => {
      const next = new Set(prev);
      if (next.has(surface)) next.delete(surface);
      else next.add(surface);
      return next;
    });
  };

  return (
    <Drawer open={open} onClose={closeDrawer} width={480} ariaLabel="Help">
      <header className="flex items-center justify-between border-b-[0.5px] border-rule-soft px-5 py-4">
        <div className="text-mono-label uppercase tracking-[0.16em] text-ink-soft">
          Help
        </div>
        <button
          type="button"
          onClick={closeDrawer}
          aria-label="Close help"
          className="text-[18px] leading-none text-ink-soft transition-colors hover:text-ink"
        >
          ×
        </button>
      </header>

      {selectedId && selected ? (
        <div className="flex-1 overflow-y-auto px-5 py-4">
          <button
            type="button"
            onClick={() => setSelectedId(null)}
            className="mb-4 inline-flex items-center text-[12px] text-ink-soft transition-colors hover:text-navy"
          >
            ← Back to help index
          </button>
          <HelpArticle article={selected} />
        </div>
      ) : (
        <>
          <div className="border-b-[0.5px] border-rule-soft px-5 py-3">
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search help…"
              aria-label="Search help articles"
              className="w-full rounded-md border-[0.5px] border-rule bg-paper px-3 py-2 text-[14px] text-ink placeholder:text-ink-faint focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
            />
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-3">
            {grouped.length === 0 ? (
              <p className="text-[13px] text-ink-soft">
                No articles match your search. Try a different term.
              </p>
            ) : (
              <div className="space-y-4">
                {grouped.map(({ surface, articles }) => {
                  // When the user is searching, override the per-session
                  // collapse state so matches stay visible — otherwise a
                  // collapsed group would silently hide hits.
                  const collapsed =
                    !isSearching && collapsedSurfaces.has(surface);
                  return (
                    <section key={surface}>
                      <button
                        type="button"
                        onClick={() => toggleSurface(surface)}
                        aria-expanded={!collapsed}
                        className="flex w-full items-center justify-between rounded-md px-1 py-1 text-left transition-colors hover:bg-rule-soft/40"
                      >
                        <span className="text-mono-label uppercase tracking-[0.16em] text-ink-soft">
                          {surface}
                          <span className="ml-2 normal-case tracking-normal text-ink-faint">
                            {articles.length}
                          </span>
                        </span>
                        <i
                          aria-hidden="true"
                          className={cn(
                            "ti text-[12px] leading-none text-ink-muted transition-transform",
                            collapsed ? "ti-chevron-right" : "ti-chevron-down",
                          )}
                        />
                      </button>
                      {!collapsed && (
                        <ul className="mt-1 space-y-0.5">
                          {articles.map((article) => (
                            <li key={article.id}>
                              <button
                                type="button"
                                onClick={() => setSelectedId(article.id)}
                                className={cn(
                                  "block w-full rounded-md px-3 py-1.5 text-left text-[14px] font-medium text-ink transition-colors",
                                  "hover:bg-navy-tint",
                                )}
                              >
                                {article.title}
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </Drawer>
  );
}
