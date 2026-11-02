// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type EvidenceViewProps } from "..";

/**
 * Apex evidence renderer.
 *
 * Apex evidence isn't an attachment list — it's a structured citation of
 * operational decisions across other workflows. The full evidence tree
 * (with role grouping, supersession audit, search modal) renders inside
 * the dedicated <ApexEvidenceSection /> on the Decision Detail page.
 * This view exists so the generic spine can show a brief "see evidence
 * panel" affordance and any unstructured evidence the executive
 * attached as free-form notes.
 */
export function OversightEvidenceView({ decision }: EvidenceViewProps) {
  const evidence = (decision.evidence_refs ?? []) as Array<
    Record<string, unknown>
  >;
  return (
    <div className="space-y-3">
      <p className="text-body-sm text-ink-soft">
        Apex decisions cite operational decisions as structured evidence.
        See the Evidence panel below for the full citation tree, including
        role grouping (primary, supporting, counter-evidence) and
        supersession history.
      </p>
      {evidence.length > 0 && (
        <ul className="space-y-2">
          {evidence.map((entry, idx) => {
            const note = stringish(entry.note) ?? stringish(entry.text);
            const url = stringish(entry.url);
            return (
              <li
                key={idx}
                className="rounded-md border-[0.5px] border-rule-soft bg-paper px-3 py-2 text-body-sm"
              >
                {note && <p className="text-ink">{note}</p>}
                {url && (
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-body-sm text-navy hover:underline"
                  >
                    {url}
                  </a>
                )}
                {!note && !url && (
                  <pre className="whitespace-pre-wrap font-mono text-[11px] text-ink-soft">
                    {JSON.stringify(entry, null, 2)}
                  </pre>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function stringish(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}
