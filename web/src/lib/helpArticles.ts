// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

// Help corpus registry. Phase 6 (Sprint at ~33 articles) replaced the
// hand-curated registry with `import.meta.glob` auto-discovery — drop a
// new file under docs/help/{surface}/*.md with valid frontmatter and it
// appears in the drawer automatically.
//
// Frontmatter contract (see docs/help/README.md):
//
//   ---
//   id: surface/slug           # must match filepath under docs/help/
//   title: Human-readable title
//   surface: <one of ALLOWED_SURFACES below>
//   tags: [k1, k2, ...]        # optional, fed to MiniSearch
//   related: [other/slug, ...] # optional, sibling-article footer
//   summary: "1-3 sentences"   # optional, used by HelpLink popover
//   ---
//
// Bad surface values, missing required fields, or id/path mismatches
// throw at module load — better to fail loudly on `pnpm dev` startup
// than to ship a drawer that silently drops articles into the void.

import { searchArticlesRanked } from "@/lib/helpSearch";

export type HelpSurface =
  | "Onboarding"
  | "Inbox"
  | "Dashboard"
  | "Decisions"
  | "Governance"
  | "Roadmap"
  | "Apex"
  | "Catalog"
  | "Settings"
  | "Concepts";

const ALLOWED_SURFACES: readonly HelpSurface[] = [
  "Onboarding",
  "Inbox",
  "Dashboard",
  "Decisions",
  "Governance",
  "Roadmap",
  "Apex",
  "Catalog",
  "Settings",
  "Concepts",
];

/**
 * Display order for the surface groups in the drawer index. Articles
 * within a surface render in registry order (alphabetical by id within
 * the surface), unless overridden by an explicit `order:` integer field
 * in frontmatter (lower numbers sort first; ties fall back to title).
 */
export const HELP_SURFACE_ORDER: readonly HelpSurface[] = ALLOWED_SURFACES;

export type HelpArticleMeta = {
  /** Stable id used for routing within the drawer + by <HelpLink topic="…">. */
  id: string;
  /** Display title shown in the index + article header. */
  title: string;
  /** Surface group label for visual grouping in the index. */
  surface: HelpSurface;
  /** Raw markdown body with frontmatter stripped, rendered by react-markdown. */
  body: string;
  /**
   * Short inline summary (2–4 sentences, plain text) shown by HelpLink's
   * popover variant — the help affordance used inside other drawers,
   * where opening a second drawer to read the full article doesn't
   * work. Optional: callers without a summary fall back to a "View full
   * article" link that closes the parent drawer.
   */
  summary?: string;
  /** Search keywords beyond title + body. Fed to MiniSearch with field boost. */
  tags?: readonly string[];
  /** Sibling-article ids surfaced in the article footer. */
  related?: readonly string[];
  /** Optional explicit ordering within a surface; lower numbers sort first. */
  order?: number;
};

// Raw glob: { '/docs/legacy/help/inbox/foo.md': '<full markdown text>' }
// Help corpus lives under docs/legacy/help/ while the DGP-era articles
// are still in use; Reasonbook-specific help will land at docs/help/
// once it's authored. `query: '?raw', import: 'default'` is the v6 API
// equivalent of the older `as: 'raw'` shorthand.
const RAW_MODULES = import.meta.glob("../../../docs/legacy/help/**/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

/**
 * Tiny YAML-frontmatter parser tailored to the actual subset our help
 * docs use. Replaces `gray-matter`, which depended on Node's `Buffer`
 * global and broke the browser matter (vitest's jsdom polyfilled it,
 * masking the issue in unit tests; Playwright surfaced it).
 *
 * Supported shapes (everything the existing corpus uses, nothing more):
 *
 *   key: bare value           → string
 *   key: "quoted value"       → string (double or single quotes)
 *   key: [a, b, c]            → string[]
 *   key: 3                    → number (integers only)
 *
 * No nested objects, no block scalars, no anchors, no multi-doc. If a
 * file ever needs anything richer, expand this — don't reach for a
 * Node-shaped YAML library again.
 */
type Frontmatter = { data: Record<string, unknown>; content: string };

function parseFrontmatter(raw: string): Frontmatter {
  // Frontmatter starts at line 1 with --- and ends at the next ---
  // also on its own line. Accept LF and CRLF line endings.
  if (!/^---\r?\n/.test(raw)) {
    return { data: {}, content: raw };
  }
  const closer = raw.search(/\r?\n---\r?\n/);
  if (closer === -1) {
    return { data: {}, content: raw };
  }
  const block = raw.slice(raw.indexOf("\n") + 1, closer);
  // Find the position right after the closing `\n---\n` (or `\r\n---\r\n`).
  const afterMatch = raw.slice(closer).match(/^\r?\n---\r?\n/);
  const content = raw.slice(closer + (afterMatch ? afterMatch[0].length : 0));

  const data: Record<string, unknown> = {};
  for (const line of block.split(/\r?\n/)) {
    if (line.trim().length === 0 || line.trimStart().startsWith("#")) continue;
    const colon = line.indexOf(":");
    if (colon === -1) continue;
    const key = line.slice(0, colon).trim();
    const rawValue = line.slice(colon + 1).trim();
    data[key] = coerceScalar(rawValue);
  }
  return { data, content };
}

function coerceScalar(raw: string): unknown {
  if (raw.length === 0) return "";
  // Inline array: [a, b, c]
  if (raw.startsWith("[") && raw.endsWith("]")) {
    const inner = raw.slice(1, -1).trim();
    if (inner.length === 0) return [];
    return inner.split(",").map((item) => stripQuotes(item.trim()));
  }
  // Integer
  if (/^-?\d+$/.test(raw)) return Number(raw);
  // Quoted string
  return stripQuotes(raw);
}

function stripQuotes(raw: string): string {
  if (raw.length >= 2) {
    const first = raw[0];
    const last = raw[raw.length - 1];
    if ((first === '"' && last === '"') || (first === "'" && last === "'")) {
      return raw.slice(1, -1);
    }
  }
  return raw;
}

function pathToId(path: string): string {
  // Drop the '../../../docs/(legacy/)?help/' prefix and the '.md' suffix,
  // keeping the surface/slug shape: 'docs/legacy/help/inbox/foo.md' →
  // 'inbox/foo'. Both the inherited corpus (docs/legacy/help/) and any
  // future Reasonbook-fresh corpus (docs/help/) feed in here.
  const markers = ["/docs/legacy/help/", "/docs/help/"];
  for (const marker of markers) {
    const idx = path.indexOf(marker);
    if (idx !== -1) {
      const trimmed = path.slice(idx + marker.length);
      if (!trimmed.endsWith(".md")) {
        throw new Error(`Help loader: expected .md, got "${path}"`);
      }
      return trimmed.slice(0, -3);
    }
  }
  throw new Error(`Help loader: unexpected path shape "${path}"`);
}

function isAllowedSurface(s: unknown): s is HelpSurface {
  return typeof s === "string" && (ALLOWED_SURFACES as readonly string[]).includes(s);
}

function loadArticles(): HelpArticleMeta[] {
  const articles: HelpArticleMeta[] = [];
  for (const [path, raw] of Object.entries(RAW_MODULES)) {
    // README.md and any non-article docs in docs/help/ get skipped.
    if (path.toLowerCase().endsWith("/readme.md")) continue;

    const expectedId = pathToId(path);
    const parsed = parseFrontmatter(raw);
    const fm = parsed.data;

    // Required-field validation — fail loudly at boot.
    if (typeof fm.id !== "string") {
      throw new Error(`Help loader: missing "id" in frontmatter of ${path}`);
    }
    if (fm.id !== expectedId) {
      throw new Error(
        `Help loader: id "${fm.id}" in ${path} does not match expected "${expectedId}" derived from filepath. ` +
          `Rename the file or fix the id so they match.`,
      );
    }
    if (typeof fm.title !== "string" || fm.title.length === 0) {
      throw new Error(`Help loader: missing "title" in frontmatter of ${path}`);
    }
    if (!isAllowedSurface(fm.surface)) {
      throw new Error(
        `Help loader: invalid surface "${String(fm.surface)}" in ${path}. ` +
          `Allowed values: ${ALLOWED_SURFACES.join(", ")}.`,
      );
    }

    articles.push({
      id: fm.id,
      title: fm.title,
      surface: fm.surface,
      body: parsed.content.trimStart(),
      summary: typeof fm.summary === "string" ? fm.summary : undefined,
      tags: Array.isArray(fm.tags) ? (fm.tags as string[]) : undefined,
      related: Array.isArray(fm.related)
        ? (fm.related as string[])
        : undefined,
      order: typeof fm.order === "number" ? fm.order : undefined,
    });
  }

  // Cross-validate `related:` references — every named id must exist.
  // Catches typos and rename drift.
  const idSet = new Set(articles.map((a) => a.id));
  for (const a of articles) {
    if (!a.related) continue;
    for (const rid of a.related) {
      if (!idSet.has(rid)) {
        throw new Error(
          `Help loader: related id "${rid}" referenced by "${a.id}" does not exist. ` +
            `Fix the related: list or restore the missing article.`,
        );
      }
    }
  }

  // Stable in-surface ordering: explicit `order:` ascending, then title.
  articles.sort((a, b) => {
    if (a.surface !== b.surface) {
      return (
        HELP_SURFACE_ORDER.indexOf(a.surface) -
        HELP_SURFACE_ORDER.indexOf(b.surface)
      );
    }
    const ao = a.order ?? Number.POSITIVE_INFINITY;
    const bo = b.order ?? Number.POSITIVE_INFINITY;
    if (ao !== bo) return ao - bo;
    return a.title.localeCompare(b.title);
  });

  return articles;
}

export const HELP_ARTICLES: readonly HelpArticleMeta[] = loadArticles();

/**
 * Articles grouped by surface in `HELP_SURFACE_ORDER` order, then
 * registry order within each surface. Used by the drawer index to
 * render one collapsible category per surface. Surfaces with zero
 * articles in the input list are dropped from the output — useful when
 * a search query filters the corpus.
 */
export function groupArticles(
  articles: readonly HelpArticleMeta[],
): { surface: HelpSurface; articles: HelpArticleMeta[] }[] {
  const buckets = new Map<HelpSurface, HelpArticleMeta[]>();
  for (const article of articles) {
    const bucket = buckets.get(article.surface);
    if (bucket) {
      bucket.push(article);
    } else {
      buckets.set(article.surface, [article]);
    }
  }
  return HELP_SURFACE_ORDER.filter((s) => buckets.has(s)).map((surface) => ({
    surface,
    articles: buckets.get(surface)!,
  }));
}

/**
 * Search the corpus. Empty query returns the full corpus in registry
 * order; non-empty queries return relevance-ranked results from
 * MiniSearch (title boost > tags boost > body), with prefix and
 * fuzzy-tolerant matching.
 */
export function searchArticles(query: string): HelpArticleMeta[] {
  const q = query.trim();
  if (!q) return [...HELP_ARTICLES];
  return searchArticlesRanked(q);
}

export function getArticleById(id: string): HelpArticleMeta | undefined {
  return HELP_ARTICLES.find((a) => a.id === id);
}
