// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Reference-counted body scroll lock.
 *
 * Two overlay surfaces in the app currently lock body scroll while open:
 * the `FacetDetailPanel` and the dashboard `Drawer`. Either component
 * could in principle render concurrently on a future surface that hosts
 * both; if both wrote `document.body.style.overflow` directly, the second
 * one's mount would save "hidden" (the value the first set) and a later
 * unmount would never restore the original value.
 *
 * This hook owns the body lock through a process-global ref-count so the
 * save/restore is correct regardless of how many consumers are open at
 * once. The original `overflow` value is captured exactly once — when the
 * count rises from 0 to 1 — and restored when it falls back to 0.
 *
 * Usage:
 *   useBodyScrollLock(open);
 *
 * Pass `true` while the consumer wants the lock; pass `false` to release.
 * Unmounting while `true` is fine: cleanup decrements the count.
 */

import { useEffect } from "react";

let lockCount = 0;
let savedOverflow: string | null = null;

export function useBodyScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    if (lockCount === 0) {
      savedOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    lockCount += 1;
    return () => {
      lockCount -= 1;
      if (lockCount === 0) {
        document.body.style.overflow = savedOverflow ?? "";
        savedOverflow = null;
      }
    };
  }, [active]);
}
