// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * 404 page rendered for unknown routes.
 *
 * Critical: this renders OUTSIDE the authenticated ``AppShell`` so a stale
 * deep-link (e.g. a legacy URL renamed in the rebrand)
 * doesn't show the rail + topbar with a "Not Found" body — that combination
 * reads as "the app is broken" rather than "this URL doesn't exist".
 *
 * Wired into the router via ``defaultNotFoundComponent`` in router.ts.
 */

import { Link } from "@tanstack/react-router";

import { useAuthStore } from "@/stores/auth";

export function NotFoundPage() {
  const status = useAuthStore((s) => s.status);
  const isAuthed = status === "authenticated";

  return (
    <div
      role="main"
      data-testid="not-found-page"
      className="flex min-h-screen flex-col items-center justify-center bg-paper px-6 text-center"
    >
      <p className="text-mono-num uppercase tracking-widest text-ink-faint">
        404
      </p>
      <h1 className="mt-3 text-page font-semibold tracking-tight text-ink">
        That page doesn&rsquo;t exist.
      </h1>
      <p className="mt-3 max-w-md text-[14px] leading-relaxed text-ink-soft">
        The URL may have been renamed or removed. If you reached this from a
        bookmark or a link inside the product, it&rsquo;s safe to head back to
        the {isAuthed ? "Inbox" : "sign-in screen"}.
      </p>
      <Link
        to={isAuthed ? "/inbox" : "/login"}
        className="mt-6 inline-block rounded-md bg-navy px-5 py-2 text-[13px] font-medium text-white hover:bg-navy-deep"
      >
        {isAuthed ? "Back to Inbox →" : "Go to sign in →"}
      </Link>
    </div>
  );
}
