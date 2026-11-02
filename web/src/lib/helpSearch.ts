// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

// MiniSearch index over the help corpus. Lazily constructed on the
// first query — eager construction at module load would deadlock the
// circular import with helpArticles.ts (which imports this module to
// wire searchArticles()'s non-empty path while we're still loading the
// HELP_ARTICLES export).
//
// Queries return relevance-ranked HelpArticleMeta[] consumed by the
// HelpDrawer via searchArticles() in helpArticles.ts.
//
// Boost rationale: a title match almost always means the article is
// directly about the queried topic, so title >> tags > body. Surface
// gets a modest boost so "inbox" surfaces inbox-surface articles when
// no specific keyword hits stronger.
//
// Prefix + fuzzy: prefix lets "fina" match "finalize"; fuzzy adds
// typo tolerance for longer terms — but is suppressed for ≤3-char
// terms because at that length a 0.2 distance allows 1 edit which
// matches half the dictionary (SAR ~ BAR ~ CAR ~ SAT). Acronyms in
// this domain (SAR, CTR, CCO, EDD, CDD) are nearly always typed
// exactly; the cost of false positives on them outweighs the typo-
// tolerance value. `combineWith: "AND"` requires every query term to
// match — a query of "sar timeliness" only surfaces articles that
// match both terms across the indexed fields.

import MiniSearch, { type SearchResult } from "minisearch";

import { HELP_ARTICLES, type HelpArticleMeta } from "@/lib/helpArticles";

type IndexedDoc = {
  id: string;
  title: string;
  surface: string;
  tags: string;
  body: string;
};

let cachedIndex: MiniSearch<IndexedDoc> | null = null;
let cachedById: Map<string, HelpArticleMeta> | null = null;

function ensureIndex(): {
  index: MiniSearch<IndexedDoc>;
  byId: Map<string, HelpArticleMeta>;
} {
  if (cachedIndex && cachedById) {
    return { index: cachedIndex, byId: cachedById };
  }
  const byId = new Map<string, HelpArticleMeta>(
    HELP_ARTICLES.map((a) => [a.id, a]),
  );
  const index = new MiniSearch<IndexedDoc>({
    idField: "id",
    fields: ["title", "tags", "surface", "body"],
    storeFields: ["id"],
    searchOptions: {
      boost: { title: 5, tags: 3, surface: 2, body: 1 },
      prefix: true,
      fuzzy: (term) => (term.length > 3 ? 0.2 : 0),
      combineWith: "AND",
    },
  });
  index.addAll(
    HELP_ARTICLES.map((a) => ({
      id: a.id,
      title: a.title,
      surface: a.surface,
      tags: a.tags ? a.tags.join(" ") : "",
      body: a.body,
    })),
  );
  cachedIndex = index;
  cachedById = byId;
  return { index, byId };
}

/**
 * Run a MiniSearch query against the corpus and return matching
 * articles in descending relevance order. Callers go through
 * `searchArticles()` in helpArticles.ts, which short-circuits the
 * empty-query case before reaching this function.
 */
export function searchArticlesRanked(query: string): HelpArticleMeta[] {
  const { index, byId } = ensureIndex();
  const hits: SearchResult[] = index.search(query);
  const out: HelpArticleMeta[] = [];
  for (const hit of hits) {
    const article = byId.get(String(hit.id));
    if (article) out.push(article);
  }
  return out;
}
