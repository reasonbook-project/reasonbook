// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { type PayloadViewProps } from "..";

/**
 * Regulatory-Compliance-specific payload visualiser.
 *
 * The Reg Compliance YAML defines distinct payload_schema fields per
 * decision type — capital ratios, exam dates, filing periods, CAMELS
 * components, concentration breakdowns. Render each shape with its
 * native units (percent for ratios, ISO dates for deadlines, etc.).
 */
export function RegPayloadView({ decision }: PayloadViewProps) {
  const payload = (decision.decision_payload ??
    decision.trigger_data ??
    {}) as Record<string, unknown>;

  // capital_action / camel_threshold_breach share ratio_name + current_value.
  const ratioName = stringish(payload.ratio_name);
  const currentValue = numberish(payload.current_value);
  const threshold = numberish(payload.threshold);
  const regClass = stringish(payload.regulatory_classification);

  // exam_preparation
  const examDate = stringish(payload.exam_date);
  const focusAreas = Array.isArray(payload.focus_areas)
    ? (payload.focus_areas as string[])
    : [];

  // liquidity_management
  const fundingPressure = stringish(payload.funding_pressure);

  // asset_quality_review
  const portfolioSegment = stringish(payload.portfolio_segment);
  const delinquencyTrend = stringish(payload.delinquency_trend);

  // call_report_filing
  const filingPeriod = stringish(payload.filing_period);
  const deadline = stringish(payload.deadline);
  const validationErrors = numberish(payload.validation_errors);

  // camel_threshold_breach
  const componentName = stringish(payload.component_name);
  const componentScore = numberish(payload.component_score);
  const previousScore = numberish(payload.previous_score);

  // concentration_risk_response
  const concentrationType = stringish(payload.concentration_type);
  const currentPct = numberish(payload.current_pct);
  const thresholdPct = numberish(payload.threshold_pct);

  const empty =
    !ratioName &&
    currentValue === null &&
    !examDate &&
    focusAreas.length === 0 &&
    !fundingPressure &&
    !portfolioSegment &&
    !filingPeriod &&
    !componentName &&
    !concentrationType;

  if (empty) {
    return (
      <p className="text-body-sm text-ink-muted">
        No structured regulatory payload captured for this decision yet.
      </p>
    );
  }

  return (
    <dl className="grid grid-cols-[180px_1fr] gap-x-4 gap-y-3 text-body-sm">
      {ratioName && (
        <Row label="Ratio">
          <span>{ratioName.replace(/_/g, " ")}</span>
        </Row>
      )}
      {currentValue !== null && (
        <Row label="Current value">
          <span className="font-mono">{formatPercent(currentValue)}</span>
        </Row>
      )}
      {threshold !== null && (
        <Row label="Threshold">
          <span className="font-mono">{formatPercent(threshold)}</span>
        </Row>
      )}
      {regClass && (
        <Row label="Classification">
          <span>{regClass.replace(/_/g, " ")}</span>
        </Row>
      )}
      {examDate && (
        <Row label="Exam date">
          <span className="font-mono">{formatDate(examDate)}</span>
        </Row>
      )}
      {focusAreas.length > 0 && (
        <Row label="Focus areas">
          <div className="flex flex-wrap gap-1.5">
            {focusAreas.map((area) => (
              <span
                key={area}
                className="rounded-sm border-[0.5px] border-rule-soft bg-rule-faint px-2 py-px text-[11px] text-ink-soft"
              >
                {area.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </Row>
      )}
      {fundingPressure && (
        <Row label="Funding pressure">
          <span>{fundingPressure}</span>
        </Row>
      )}
      {portfolioSegment && (
        <Row label="Portfolio segment">
          <span>{portfolioSegment.replace(/_/g, " ")}</span>
        </Row>
      )}
      {delinquencyTrend && (
        <Row label="Delinquency trend">
          <span>{delinquencyTrend}</span>
        </Row>
      )}
      {filingPeriod && (
        <Row label="Filing period">
          <span className="font-mono">{filingPeriod}</span>
        </Row>
      )}
      {deadline && (
        <Row label="Deadline">
          <span className="font-mono">{formatDate(deadline)}</span>
        </Row>
      )}
      {validationErrors !== null && (
        <Row label="Validation errors">
          <span className="font-mono">{validationErrors}</span>
        </Row>
      )}
      {componentName && (
        <Row label="CAMELS component">
          <span>{componentName}</span>
        </Row>
      )}
      {componentScore !== null && (
        <Row label="Component score">
          <span className="font-mono">
            {componentScore.toFixed(1)}
            {previousScore !== null && (
              <span className="text-ink-muted">
                {" "}
                (was {previousScore.toFixed(1)})
              </span>
            )}
          </span>
        </Row>
      )}
      {concentrationType && (
        <Row label="Concentration type">
          <span>{concentrationType.replace(/_/g, " ")}</span>
        </Row>
      )}
      {currentPct !== null && (
        <Row label="Current concentration">
          <span className="font-mono">
            {formatPercent(currentPct)}
            {thresholdPct !== null && (
              <span className="text-ink-muted">
                {" "}
                (threshold {formatPercent(thresholdPct)})
              </span>
            )}
          </span>
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

function numberish(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function stringish(value: unknown): string | null {
  if (typeof value === "string" && value.length > 0) return value;
  return null;
}

function formatPercent(value: number): string {
  return `${value.toFixed(2)}%`;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}
