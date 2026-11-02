// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import ReactMarkdown from "react-markdown";

import { type HelpArticleMeta, getArticleById } from "@/lib/helpArticles";
import { useHelpStore } from "@/stores/help";

/**
 * Resolve a relative markdown link href to a topic id usable with
 * getArticleById. Handles the three patterns articles use:
 *
 *   `claim.md`                         → `{currentSurface}/claim`
 *   `../decisions/claim.md`            → `decisions/claim`
 *   `decisions/claim` (no .md)         → returned unchanged
 *
 * Returns null when the href isn't an internal cross-reference
 * (external URL, mailto, anchor link). The caller falls back to a
 * plain-link or external-anchor render in that case.
 */
function resolveInternalTopicId(
  currentTopicId: string,
  href: string,
): string | null {
  // External and protocol links — never internal cross-references.
  if (/^([a-z][a-z0-9+.-]*:|#|\/)/i.test(href)) return null;

  // Topic-id form: `surface/slug` without an extension.
  if (!href.endsWith(".md")) {
    if (href.includes("/") && !href.includes("..")) return href;
    return null;
  }

  const path = href.slice(0, -3); // strip `.md`
  // Walk leading `../` segments off the path. Each `../` moves up one
  // directory; since topics are always one level deep (surface/slug),
  // a single `../` effectively means "topic id is the rest as-is."
  let cleaned = path;
  while (cleaned.startsWith("../")) cleaned = cleaned.slice(3);

  if (cleaned.includes("/")) {
    // Already in `surface/slug` shape.
    return cleaned;
  }

  // Sibling path — prepend the current article's surface.
  const surface = currentTopicId.split("/")[0];
  return `${surface}/${cleaned}`;
}

/**
 * Single help article renderer. Strips the first H1 (we render the title
 * from the meta) and renders the rest of the markdown with design-system
 * typography.
 *
 * Internal markdown links resolve to other registered help articles via
 * `resolveInternalTopicId` and dispatch `openArticle` to the help store
 * on click — same behavior as `<HelpLink>` anchors elsewhere in the
 * product. Unresolved markdown links (architecture doc references and
 * the like) render as plain dotted-underline text so they don't read as
 * broken affordances. External URLs render as standard links opening
 * in a new tab.
 */
export function HelpArticle({ article }: { article: HelpArticleMeta }) {
  const openArticle = useHelpStore((s) => s.openArticle);

  // Drop the first H1 from the body — the drawer header already shows
  // the title, and react-markdown would otherwise render a duplicate.
  const bodyWithoutH1 = article.body.replace(/^#\s.+\n+/, "");

  return (
    <article className="prose-help">
      <header className="mb-4 border-b-[0.5px] border-rule-soft pb-3">
        <div className="text-mono-label uppercase tracking-[0.16em] text-ink-faint">
          {article.surface}
        </div>
        <h2 className="mt-1 text-[18px] font-semibold tracking-tight text-ink">
          {article.title}
        </h2>
      </header>
      <div className="space-y-3 text-[14px] leading-[1.6] text-ink">
        <ReactMarkdown
          components={{
            h2: ({ children }) => (
              <h3 className="mt-5 text-[15px] font-semibold text-ink">
                {children}
              </h3>
            ),
            h3: ({ children }) => (
              <h4 className="mt-4 text-[14px] font-medium text-ink">
                {children}
              </h4>
            ),
            p: ({ children }) => <p className="text-ink">{children}</p>,
            ul: ({ children }) => (
              <ul className="list-disc space-y-1 pl-5 text-ink">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal space-y-1 pl-5 text-ink">{children}</ol>
            ),
            li: ({ children }) => <li className="text-ink">{children}</li>,
            strong: ({ children }) => (
              <strong className="font-medium text-ink">{children}</strong>
            ),
            em: ({ children }) => <em className="italic text-ink">{children}</em>,
            code: ({ children }) => (
              <code className="rounded bg-paper-shade px-1 py-px font-mono text-[12px] text-ink">
                {children}
              </code>
            ),
            a: ({ children, href }) => {
              // Internal cross-reference → resolves to another help
              // article and navigates within the drawer.
              const topicId = href
                ? resolveInternalTopicId(article.id, href)
                : null;
              if (topicId && getArticleById(topicId)) {
                return (
                  <button
                    type="button"
                    onClick={() => openArticle(topicId)}
                    className="text-navy underline decoration-navy/40 underline-offset-2 transition-colors hover:decoration-navy"
                  >
                    {children}
                  </button>
                );
              }
              // External link — opens in a new tab.
              if (href && /^https?:/i.test(href)) {
                return (
                  <a
                    href={href}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-navy underline decoration-navy/40 underline-offset-2 transition-colors hover:decoration-navy"
                  >
                    {children}
                  </a>
                );
              }
              // Mailto and other protocols.
              if (href && /^[a-z][a-z0-9+.-]*:/i.test(href)) {
                return (
                  <a
                    href={href}
                    className="text-navy underline decoration-navy/40 underline-offset-2 transition-colors hover:decoration-navy"
                  >
                    {children}
                  </a>
                );
              }
              // Unresolved reference (architecture doc, etc.) — render
              // as plain dotted-underline text so it doesn't read as a
              // broken affordance.
              return (
                <span className="text-ink underline decoration-rule decoration-dotted underline-offset-2">
                  {children}
                </span>
              );
            },
            blockquote: ({ children }) => (
              <blockquote className="border-l-2 border-rule pl-3 italic text-ink-soft">
                {children}
              </blockquote>
            ),
          }}
        >
          {bodyWithoutH1}
        </ReactMarkdown>
      </div>
    </article>
  );
}
