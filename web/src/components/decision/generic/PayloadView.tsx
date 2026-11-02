// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { Decision } from "@/api/decisions";

/**
 * Generic decision-payload renderer. Walks the JSONB payload and lists each
 * key/value pair. Per-workflow PayloadViews can do something visual; this
 * is the safe fallback.
 */
export function GenericPayloadView({ decision }: { decision: Decision }) {
  const payload = decision.decision_payload ?? decision.trigger_data;
  if (!payload || typeof payload !== "object") {
    return (
      <p className="text-body-sm text-ink-muted">
        No structured payload captured for this decision.
      </p>
    );
  }
  const entries = Object.entries(payload);
  if (entries.length === 0) {
    return (
      <p className="text-body-sm text-ink-muted">
        No structured payload captured for this decision.
      </p>
    );
  }
  return (
    <dl className="grid grid-cols-[160px_1fr] gap-x-4 gap-y-2 text-body-sm">
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-tracked uppercase text-ink-soft">
            {key}
          </dt>
          <dd className="font-mono text-ink">
            {typeof value === "string" ? value : JSON.stringify(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}
