// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { Popover } from "@/components/ds/Popover";
import { Tooltip } from "@/components/ds/Tooltip";
import { getArticleById } from "@/lib/helpArticles";
import { cn } from "@/lib/cn";
import { useHelpStore } from "@/stores/help";

/**
 * Contextual anchor that opens the help drawer to a specific article.
 *
 * Drop these next to empty-states, paywalls, and any affordance whose
 * purpose isn't self-evident. The article opens in the drawer — primary
 * navigation context is preserved.
 *
 * Three variants:
 *
 * - `link` (default) — "Need help?" text link with a `?` glyph. Use
 *   inline beneath the primary content of an empty state, or next to
 *   a section heading where text reads better than a bare icon.
 *
 * - `icon` — `?`-in-a-circle button (Tabler `ti-help-circle`). Use next
 *   to a field label, table column header, or section heading. Rendered
 *   in navy so the affordance reads as interactive; a tooltip showing
 *   the article title surfaces on hover so the user can see what
 *   clicking will open before they commit.
 *
 * - `popover` — same `?`-in-a-circle button, but click opens an inline
 *   popover (Popover primitive) rather than dispatching the help
 *   Drawer. Use inside other Drawers and Modals where a second right-
 *   side Drawer would conflict (z-stacking, focus trap, body scroll).
 *   The popover shows the article's `summary` field; if the user needs
 *   the full article, the popover's footer "View full article" link
 *   calls `onLaunchFullArticle` (the parent's chance to close itself
 *   gracefully) before dispatching the help Drawer.
 *
 * Topic ids are the `id` field in `web/src/lib/helpArticles.ts` (and
 * the matching frontmatter id in the markdown file under `docs/help/`).
 * In dev mode an unknown topic logs a warning so typos surface fast.
 */
type HelpLinkProps = {
  /** Article id from helpArticles.ts (e.g. "decisions/finalize"). */
  topic: string;
  /** Visual treatment. Defaults to "link". */
  variant?: "link" | "icon" | "popover";
  /** Override the link variant's text. Ignored by `icon` and `popover`. */
  label?: string;
  /** Override the icon/popover variant's aria-label and tooltip content. */
  ariaLabel?: string;
  /** Optional className for layout positioning. */
  className?: string;
  /**
   * `popover` variant only. Called when the user clicks "View full
   * article" — the parent's opportunity to close its own Drawer/Modal
   * before the help Drawer opens. If omitted, the help Drawer still
   * opens, but the parent Drawer remains and the rendering conflicts
   * described above will occur.
   */
  onLaunchFullArticle?: () => void;
};

export function HelpLink({
  topic,
  variant = "link",
  label = "Need help?",
  ariaLabel,
  className,
  onLaunchFullArticle,
}: HelpLinkProps) {
  const openArticle = useHelpStore((s) => s.openArticle);
  const article = getArticleById(topic);

  // Dev-only typo guard. The drawer falls back to the registry when the
  // article exists; this warning catches the case where a HelpLink
  // references an id that was renamed or never authored.
  if (import.meta.env.DEV && !article) {
    console.warn(
      `<HelpLink topic="${topic}"> — no article with this id in helpArticles.ts. ` +
        `Either author it under docs/help/{surface}/ and register it, or fix the topic prop.`,
    );
  }

  // Dev-only summary guard for the popover variant — the popover renders
  // empty if the article lacks a summary, so surface that loudly.
  if (
    import.meta.env.DEV &&
    variant === "popover" &&
    article &&
    !article.summary
  ) {
    console.warn(
      `<HelpLink topic="${topic}" variant="popover"> — article has no summary. ` +
        `Add a summary field to the registry entry in web/src/lib/helpArticles.ts.`,
    );
  }

  const handleClick = () => openArticle(topic);

  if (variant === "popover") {
    const tooltipText = ariaLabel ?? article?.title ?? `Help: ${topic}`;
    const handleLaunchFull = () => {
      if (onLaunchFullArticle) onLaunchFullArticle();
      openArticle(topic);
    };
    const trigger = (
      <button
        type="button"
        aria-label={tooltipText}
        className={cn(
          "inline-flex h-[20px] w-[20px] items-center justify-center rounded-full text-navy transition-colors",
          "hover:bg-navy-tint hover:text-navy-deep",
          "focus-visible:bg-navy-tint focus-visible:text-navy-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-soft",
          className,
        )}
      >
        <i
          aria-hidden="true"
          className="ti ti-help-circle"
          style={{ fontSize: "16px", lineHeight: 1 }}
        />
      </button>
    );
    return (
      <Popover trigger={trigger} ariaLabel={tooltipText}>
        {article?.title && (
          <div className="mb-2 text-[14px] font-medium text-ink">
            {article.title}
          </div>
        )}
        {article?.summary ? (
          <p className="text-[13px] leading-[1.55] text-ink-soft">
            {article.summary}
          </p>
        ) : (
          <p className="text-[13px] leading-[1.55] text-ink-soft">
            No inline summary yet — open the full article for detail.
          </p>
        )}
        <button
          type="button"
          onClick={handleLaunchFull}
          className="mt-3 inline-flex items-center gap-1 text-[12px] font-medium text-navy underline decoration-navy/40 decoration-dotted underline-offset-2 transition-colors hover:text-navy-deep hover:decoration-navy-deep"
        >
          View full article
          <span aria-hidden="true">→</span>
        </button>
      </Popover>
    );
  }

  if (variant === "icon") {
    // Tooltip surfaces the article title so the affordance isn't
    // mysterious. Falls back to the ariaLabel / topic id when the
    // article isn't registered yet (typo guard rendered above).
    const tooltipText = ariaLabel ?? article?.title ?? `Help: ${topic}`;
    const button = (
      <button
        type="button"
        onClick={handleClick}
        aria-label={tooltipText}
        className={cn(
          "inline-flex h-[20px] w-[20px] items-center justify-center rounded-full text-navy transition-colors",
          "hover:bg-navy-tint hover:text-navy-deep",
          "focus-visible:bg-navy-tint focus-visible:text-navy-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-soft",
          className,
        )}
      >
        <i
          aria-hidden="true"
          className="ti ti-help-circle"
          style={{ fontSize: "16px", lineHeight: 1 }}
        />
      </button>
    );
    return <Tooltip content={tooltipText}>{button}</Tooltip>;
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn(
        "inline-flex items-center gap-1 text-[13px] text-navy underline decoration-navy/40 decoration-dotted underline-offset-2 transition-colors",
        "hover:text-navy-deep hover:decoration-navy-deep focus-visible:text-navy-deep focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy-soft",
        className,
      )}
    >
      <i
        aria-hidden="true"
        className="ti ti-help-circle"
        style={{ fontSize: "13px", lineHeight: 1 }}
      />
      <span>{label}</span>
    </button>
  );
}
