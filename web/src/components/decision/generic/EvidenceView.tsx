// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { Decision } from "@/api/decisions";

/**
 * Generic evidence renderer — the fallback when a workflow doesn't ship its
 * own EvidenceView. Iterates the JSON evidence_refs array and prints each
 * entry as a labeled key/value pair.
 */
export function GenericEvidenceView({ decision }: { decision: Decision }) {
  const evidence = decision.evidence_refs;
  if (!Array.isArray(evidence) || evidence.length === 0) {
    return (
      <p className="text-body-sm text-ink-muted">
        No evidence captured yet.
      </p>
    );
  }
  return (
    <ul className="space-y-2">
      {evidence.map((entry, idx) => (
        <li
          key={idx}
          className="rounded-md border-[0.5px] border-rule-soft bg-rule-faint px-3 py-2"
        >
          <pre className="whitespace-pre-wrap font-mono text-[11px] text-ink-soft">
            {JSON.stringify(entry, null, 2)}
          </pre>
        </li>
      ))}
    </ul>
  );
}
