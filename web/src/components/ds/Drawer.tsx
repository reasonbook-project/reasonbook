// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Right-side drawer primitive.
 *
 * Slides in from the right; backdrop dims the rest of the page. Used by
 * the dashboard's DecisionQueueDrawer (P17), but the primitive itself is
 * content-agnostic — pass any ReactNode as children.
 *
 * Behaviour:
 *   - 200ms ease-out slide transition (transform: translateX(100%) → 0)
 *   - Backdrop click + Esc + the consumer's × button all call onClose
 *   - Focus trap inside the drawer while open
 *   - Body scroll locked while open (reference-counted via useBodyScrollLock)
 *   - role="dialog" + aria-modal="true" + aria-label from props
 *   - Always-mounted; CSS transitions key off `data-open` so open/close
 *     state is reflected in the DOM for tests + transitions don't need
 *     an unmount step
 *
 * The consumer is responsible for rendering its own header — including the
 * close button — and wiring onClose. The Drawer itself only handles the
 * shell, the backdrop, the focus trap, and the keyboard handling. This
 * lets consumers compose the header however they want (filter chips,
 * count badges, etc.) without prop bloat.
 */

import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { useBodyScrollLock } from "@/hooks/useBodyScrollLock";
import { cn } from "@/lib/cn";

export type DrawerProps = {
  open: boolean;
  onClose: () => void;
  /** Pixel width on desktop. Default 480; the spec called for 720 but we
   *  override per D3 to leave dashboard context visible behind the drawer. */
  width?: number;
  /** Right-side offset in pixels. Non-zero when a persistent icon rail
   *  sits at the viewport's right edge and the drawer needs to slide in
   *  just to the left of it. */
  rightOffset?: number;
  ariaLabel: string;
  children: ReactNode;
};

const DEFAULT_WIDTH_PX = 480;

export function Drawer({
  open,
  onClose,
  width = DEFAULT_WIDTH_PX,
  rightOffset = 0,
  ariaLabel,
  children,
}: DrawerProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Capture the element that had focus when we opened so we can restore it
  // on close. Defer the restore by a tick so the dialog is fully gone.
  useEffect(() => {
    if (open && !triggerRef.current) {
      triggerRef.current = document.activeElement as HTMLElement | null;
    }
    if (!open && triggerRef.current) {
      const t = triggerRef.current;
      triggerRef.current = null;
      window.setTimeout(() => t.focus(), 0);
    }
  }, [open]);

  // Move focus into the dialog on open. Prefers the first focusable child
  // (typically the consumer's close button or filter toolbar); falls back
  // to the dialog container itself.
  useEffect(() => {
    if (!open || !dialogRef.current) return;
    const focusable = dialogRef.current.querySelector<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    (focusable ?? dialogRef.current).focus();
  }, [open]);

  useBodyScrollLock(open);

  // ESC + Tab-trap keyboard handling. Scoped to the dialog so it doesn't
  // fight with whatever the rest of the page is listening for.
  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (event.shiftKey && active === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && active === last) {
          event.preventDefault();
          first.focus();
        }
      }
    },
    [onClose],
  );

  return (
    <div
      aria-hidden={!open}
      data-open={open ? "true" : "false"}
      className="pointer-events-none fixed inset-0 z-40"
    >
      {/* Backdrop. tabIndex=-1 keeps it out of the Tab order; the click
          handler is for mouse / pointer dismissal. */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className={cn(
          "pointer-events-auto absolute inset-0 bg-ink/35 transition-opacity duration-200 ease-out",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      {/* Dialog — right-anchored, fixed pixel width, full height. Slides
          in via translateX transform. rightOffset pulls the OPEN drawer
          left so a persistent rail can sit at the viewport's right
          edge; the CLOSED drawer parks fully off-screen right so its
          bg-paper doesn't leak into the rail area. */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel}
        tabIndex={-1}
        onKeyDown={onKeyDown}
        style={{
          width: `${width}px`,
          right: 0,
          transform: open
            ? `translateX(-${rightOffset}px)`
            : `translateX(100%)`,
        }}
        className={cn(
          "pointer-events-auto absolute top-0 flex h-full max-w-full flex-col bg-paper border-l-[0.5px] border-rule",
          "transition-transform duration-200 ease-out",
        )}
      >
        {children}
      </div>
    </div>
  );
}
