// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type EvidenceViewProps } from "..";

/**
 * Regulatory-Compliance-specific evidence renderer.
 *
 * Reg Compliance decisions cite call-report extracts, NCUA exam findings,
 * board-meeting minutes, and policy documents. The evidence shape is more
 * narrative than BSA's transaction-log format — surface a doc title,
 * source, and date when present, then fall back to JSON.
 */
export function RegEvidenceView({ decision }: EvidenceViewProps) {
  const evidence = (decision.evidence_refs ?? []) as Array<
    Record<string, unknown>
  >;
  if (evidence.length === 0) {
    return (
      <p className="text-body-sm text-ink-muted">
        No evidence captured yet. Capital actions and exam-prep decisions
        cite call-report extracts, board minutes, and policy documents
        once recorded.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {evidence.map((entry, idx) => {
        const type = String(entry.type ?? "evidence");
        const id = stringish(entry.id);
        const title = stringish(entry.title);
        const source = stringish(entry.source);
        const dated = stringish(entry.dated_at) ?? stringish(entry.date);
        const url = stringish(entry.url);

        return (
          <li
            key={idx}
            className="rounded-md border-[0.5px] border-rule-soft bg-paper px-4 py-3"
          >
            <div className="flex flex-wrap items-baseline gap-3 text-tracked uppercase text-ink-soft">
              <span>{type.replace(/_/g, " ")}</span>
              {id && (
                <span className="font-mono text-[11px] text-ink-faint">
                  {id}
                </span>
              )}
              {dated && (
                <span className="font-mono text-[11px] text-ink-faint">
                  {formatDate(dated)}
                </span>
              )}
            </div>
            {title && (
              <p className="mt-1 text-body text-ink">{title}</p>
            )}
            {source && (
              <p className="text-body-sm text-ink-soft">
                Source: {source}
              </p>
            )}
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="text-body-sm text-navy hover:underline"
              >
                Open document
              </a>
            )}
            {!title && !source && !url && (
              <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] text-ink-soft">
                {JSON.stringify(entry, null, 2)}
              </pre>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function stringish(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}
