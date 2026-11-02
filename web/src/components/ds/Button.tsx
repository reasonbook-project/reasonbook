// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type ButtonHTMLAttributes, forwardRef } from "react";

import { cn } from "@/lib/cn";

/**
 * Button primitives per the SaaS rebrand mockups (§3.9).
 *
 * Two variants:
 *   - primary: navy bg, white text. Use for action buttons across the
 *              platform. The design system authorizes
 *              multiple primary CTAs per page — topbar + hero + section
 *              CTAs commonly all wear the navy fill. Pick primary when
 *              the button represents an action the user is meant to
 *              take; pick ghost when the button is a passive option
 *              (filter, dismiss, navigate-back).
 *   - ghost:   transparent, ink text, rule border. Filter buttons,
 *              dismiss/cancel actions, breadcrumb back, secondary
 *              navigation that shouldn't compete with primary actions.
 *
 * `arrow` modifier appends a → glyph that translates 3px right on hover.
 * The arrow color follows the variant (white on primary, navy on ghost).
 *
 * `compact` reduces padding for inline use (e.g., comment-thread submit,
 * empty-state action rows). A compact primary button reads as more
 * visually saturated than a default-size primary even at identical
 * color — that's a size-density effect, not a bug.
 */
export type ButtonVariant = "primary" | "ghost";

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-navy text-paper hover:bg-navy-deep active:scale-[0.98] " +
    "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-navy-soft " +
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-navy disabled:active:scale-100",
  ghost:
    "bg-transparent text-ink border border-rule hover:border-navy hover:text-navy " +
    "focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-navy-soft " +
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:border-rule disabled:hover:text-ink",
};

const ARROW_COLOR: Record<ButtonVariant, string> = {
  primary: "text-paper",
  ghost: "text-navy",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    arrow?: boolean;
    compact?: boolean;
  }
>(function Button(
  {
    variant = "primary",
    arrow = false,
    compact = false,
    className,
    children,
    type = "button",
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "group inline-flex items-center gap-[6px] rounded-md text-[14px] font-medium leading-none transition-colors duration-150",
        compact ? "px-3 py-[6px]" : "px-[18px] py-2",
        VARIANT_CLASSES[variant],
        className,
      )}
      {...rest}
    >
      {children}
      {arrow && (
        <span
          aria-hidden
          className={cn(
            "transition-transform duration-150 ease-out group-hover:translate-x-[3px]",
            ARROW_COLOR[variant],
          )}
        >
          →
        </span>
      )}
    </button>
  );
});
