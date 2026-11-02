// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type PayloadViewProps } from "..";

/**
 * Apex-specific payload visualiser.
 *
 * Apex payloads carry strategic-decision substance — capital impacts,
 * portfolio targets, risk limit changes, governance paths. The
 * fields are heterogeneous across the 17 decision types; this view
 * renders whatever's present, falling back gracefully when fields
 * are absent.
 */
export function OversightPayloadView({ decision }: PayloadViewProps) {
  const payload = (decision.decision_payload ??
    decision.trigger_data ??
    {}) as Record<string, unknown>;

  const portfolioName = stringish(payload.portfolio_name);
  const productName = stringish(payload.product_name);
  const programName = stringish(payload.program_name);
  const policyName = stringish(payload.policy_name);
  const investmentName = stringish(payload.investment_name);
  const role = stringish(payload.role);
  const actionType = stringish(payload.action_type);
  const direction = stringish(payload.direction);

  const targetIncrease = payload.target_increase as
    | { amount?: number; unit?: string }
    | undefined;
  const targetDecrease = payload.target_decrease as
    | { amount?: number; unit?: string }
    | undefined;
  const capitalImpact = payload.capital_impact as
    | { rwa_change?: number; ratio_bps?: number; rwa_increase?: number }
    | undefined;
  const timeHorizon = payload.time_horizon as
    | { months?: number; start_date?: string; end_date?: string }
    | undefined;
  const launchWindow = payload.launch_window as
    | { start?: string; end?: string }
    | undefined;

  const rationale =
    stringish(payload.primary_rationale) ??
    stringish(payload.rationale) ??
    stringish(payload.commitment_summary) ??
    stringish(payload.change_summary) ??
    stringish(payload.impact_assessment);

  const governancePath = Array.isArray(payload.governance_path)
    ? (payload.governance_path as Array<Record<string, unknown>>)
    : [];

  // facet_advancement_review payload (governance_improvement domain).
  // Renders the floor change + the facets at / above the new floor.
  const previousFloor =
    typeof payload.previous_floor === "number" ? payload.previous_floor : null;
  const newFloor =
    typeof payload.new_floor === "number" ? payload.new_floor : null;
  const facetsAtNewFloor = Array.isArray(payload.facets_at_new_floor)
    ? (payload.facets_at_new_floor as string[])
    : [];
  const facetsAboveNewFloor = Array.isArray(payload.facets_above_new_floor)
    ? (payload.facets_above_new_floor as Array<{
        facet_id: string;
        level: number;
      }>)
    : [];

  const empty =
    !portfolioName &&
    !productName &&
    !programName &&
    !policyName &&
    !investmentName &&
    !role &&
    !actionType &&
    !direction &&
    !rationale &&
    governancePath.length === 0 &&
    previousFloor === null &&
    newFloor === null;

  if (empty) {
    return (
      <p className="text-body-sm text-ink-muted">
        No structured apex payload captured for this decision yet.
      </p>
    );
  }

  return (
    <dl className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-3 text-body-sm">
      {previousFloor !== null && newFloor !== null && (
        <Row label="Floor change">
          <span className="font-mono">
            L{previousFloor} → L{newFloor}
          </span>
        </Row>
      )}
      {facetsAtNewFloor.length > 0 && (
        <Row label="Facets at new floor">
          <span>
            {facetsAtNewFloor
              .map((id) => formatFacet(id))
              .join(", ")}
          </span>
        </Row>
      )}
      {facetsAboveNewFloor.length > 0 && (
        <Row label="Facets above floor">
          <span>
            {facetsAboveNewFloor
              .map((f) => `${formatFacet(f.facet_id)} at L${f.level}`)
              .join(", ")}
          </span>
        </Row>
      )}
      {portfolioName && (
        <Row label="Portfolio">
          <span>{portfolioName}</span>
        </Row>
      )}
      {productName && (
        <Row label="Product">
          <span>{productName}</span>
        </Row>
      )}
      {programName && (
        <Row label="Program">
          <span>{programName}</span>
        </Row>
      )}
      {policyName && (
        <Row label="Policy">
          <span>{policyName}</span>
        </Row>
      )}
      {investmentName && (
        <Row label="Investment">
          <span>{investmentName}</span>
        </Row>
      )}
      {role && (
        <Row label="Role">
          <span>{role}</span>
        </Row>
      )}
      {actionType && (
        <Row label="Action type">
          <span>{actionType.replace(/_/g, " ")}</span>
        </Row>
      )}
      {direction && (
        <Row label="Direction">
          <span>{direction}</span>
        </Row>
      )}
      {targetIncrease?.amount !== undefined && (
        <Row label="Target increase">
          <span className="font-mono">
            {formatNumber(targetIncrease.amount)}{" "}
            <span className="text-ink-muted">
              {targetIncrease.unit?.replace(/_/g, " ") ?? ""}
            </span>
          </span>
        </Row>
      )}
      {targetDecrease?.amount !== undefined && (
        <Row label="Target decrease">
          <span className="font-mono">
            {formatNumber(targetDecrease.amount)}{" "}
            <span className="text-ink-muted">
              {targetDecrease.unit?.replace(/_/g, " ") ?? ""}
            </span>
          </span>
        </Row>
      )}
      {timeHorizon && (timeHorizon.months || timeHorizon.start_date) && (
        <Row label="Time horizon">
          <span className="font-mono">
            {timeHorizon.months ? `${timeHorizon.months} mo` : ""}
            {timeHorizon.start_date && timeHorizon.end_date && (
              <span className="text-ink-muted">
                {" "}
                ({formatDate(timeHorizon.start_date)} →{" "}
                {formatDate(timeHorizon.end_date)})
              </span>
            )}
          </span>
        </Row>
      )}
      {launchWindow?.start && launchWindow?.end && (
        <Row label="Launch window">
          <span className="font-mono">
            {formatDate(launchWindow.start)} → {formatDate(launchWindow.end)}
          </span>
        </Row>
      )}
      {capitalImpact && (
        <Row label="Capital impact">
          <span className="font-mono">
            {capitalImpact.rwa_increase !== undefined &&
              `+RWA ${formatNumber(capitalImpact.rwa_increase)}`}
            {capitalImpact.rwa_change !== undefined &&
              `RWA Δ ${formatNumber(capitalImpact.rwa_change)}`}
            {capitalImpact.ratio_bps !== undefined && (
              <span className="text-ink-muted">
                {" "}
                · {capitalImpact.ratio_bps} bps
              </span>
            )}
          </span>
        </Row>
      )}
      {rationale && (
        <Row label="Rationale">
          <p className="italic text-ink">{rationale}</p>
        </Row>
      )}
      {governancePath.length > 0 && (
        <Row label="Governance path">
          <ul className="space-y-1">
            {governancePath.map((step, idx) => {
              const action = stringish(step.action);
              const stepDate = stringish(step.date);
              return (
              <li key={idx} className="text-body-sm">
                <span className="font-mono text-[11px] text-ink-faint">
                  {stringish(step.body)?.replace(/_/g, " ")}
                </span>
                {action && (
                  <>
                    {" "}
                    <span>{action}</span>
                  </>
                )}
                {stepDate && (
                  <span className="text-ink-muted">
                    {" "}
                    · {formatDate(stepDate)}
                  </span>
                )}
              </li>
              );
            })}
          </ul>
        </Row>
      )}
    </dl>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-tracked uppercase text-ink-soft">
        {label}
      </dt>
      <dd className="text-ink">{children}</dd>
    </>
  );
}

function stringish(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}

/** Friendly facet display name from the canonical facet_id. */
const FACET_DISPLAY: Record<string, string> = {
  ownership: "Ownership",
  timeliness: "Timeliness",
  reconstructability: "Reconstructability",
  "override-discipline": "Override Discipline",
  authority: "Authority",
  "apex-linkage": "Apex Linkage",
};

function formatFacet(id: string): string {
  return FACET_DISPLAY[id] ?? id;
}
