// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useMemo } from "react";

import { Button } from "@/components/ds/Button";
import { cn } from "@/lib/cn";

/**
 * Threshold visualisation per `dgp-schema-explorer-spec-v1_0.md` §7.
 *
 * Renders a metric's thresholds as a horizontal bar with coloured regions
 * between consecutive stops. Each stop sits below the bar with its name
 * and value. The component is mode-aware:
 *
 *   - `read`: display only. Used by the Schema Explorer's metric cards.
 *   - `edit`: same visual rendering plus a small grid of numeric inputs
 *     so the user can override any stop. A "Reset" affordance appears
 *     when the current values diverge from the platform defaults.
 *
 * Tolerant of which subset of stops is defined — most metrics carry 3-4,
 * not all 6. Direction reverses the color order: `higher_is_better`
 * reads left-to-right as bad-to-good; `lower_is_better` reverses;
 * `neutral` uses a range-around-target palette.
 */

/**
 * Field names match the workflow YAML schema (`MetricThresholds` Pydantic
 * model in `dgp/semantic/schema.py`). The schema-explorer spec used
 * abbreviated forms (`crit_low/warn_low/...`) but the data model is
 * spelled out — we match the data model so this drops in over the API
 * payload without renaming.
 */
export type Thresholds = {
  critical_low?: number | null;
  warning_low?: number | null;
  target?: number | null;
  stretch?: number | null;
  warning_high?: number | null;
  critical_high?: number | null;
};

export type ThresholdDirection =
  | "higher_is_better"
  | "lower_is_better"
  | "neutral";

export type ThresholdMode = "read" | "edit";

type StopKey = keyof Thresholds;

type StopColor = "critical" | "warning" | "info" | "resolved" | "neutral";

const STOP_LABEL: Record<StopKey, string> = {
  critical_low: "Crit low",
  warning_low: "Warn low",
  target: "Target",
  stretch: "Stretch",
  warning_high: "Warn high",
  critical_high: "Crit high",
};

const COLOR_BG: Record<StopColor, string> = {
  critical: "bg-critical-bg",
  warning: "bg-warning-bg",
  info: "bg-info-bg",
  resolved: "bg-resolved-bg",
  neutral: "bg-rule-faint",
};

const COLOR_DOT: Record<StopColor, string> = {
  critical: "bg-critical-dot",
  warning: "bg-warning-dot",
  info: "bg-info-dot",
  resolved: "bg-resolved-dot",
  neutral: "bg-ink-faint",
};

/**
 * The stop ordering on a number line is fixed regardless of direction:
 *   crit_low < warn_low < target < stretch | warn_high < crit_high
 *
 * (For metrics that only have one side, e.g. lower_is_better with
 * crit_high/warn_high, the missing left-hand stops are simply omitted.)
 */
const NUMBER_LINE_ORDER: StopKey[] = [
  "critical_low",
  "warning_low",
  "target",
  "stretch",
  "warning_high",
  "critical_high",
];

/**
 * Color the segment between two adjacent stops based on direction +
 * which side of `target` the segment falls on.
 */
function colorForSegment(
  leftStop: StopKey | null,
  rightStop: StopKey | null,
  direction: ThresholdDirection,
): StopColor {
  // Outermost regions (no stop on one side) inherit the adjacent stop's
  // semantic — left of crit_low is "below critical", right of crit_high
  // is "above critical".
  const inferredLeft = leftStop ?? rightStop;
  const inferredRight = rightStop ?? leftStop;
  if (!inferredLeft || !inferredRight) return "neutral";

  // Map each stop name to its "danger weight". target is 0 (good),
  // warn is 1, crit is 2. stretch is -1 (best).
  const weight = (k: StopKey): number => {
    if (k === "target") return 0;
    if (k === "stretch") return -1;
    if (k === "warning_low" || k === "warning_high") return 1;
    return 2; // critical_low | critical_high
  };

  const w = Math.max(weight(inferredLeft), weight(inferredRight));

  // For neutral metrics, anything within target/warn band is "ok"; outer
  // is just "neutral-bad" — we use the same palette but no left/right
  // semantic difference.
  if (direction === "neutral") {
    if (w <= 0) return "resolved";
    if (w === 1) return "warning";
    return "critical";
  }

  // For oriented metrics, segment color follows danger weight directly.
  // The visual "direction" reversal is handled by where the stops land
  // on the number line — higher_is_better metrics put critical_low on the
  // left (because low values are bad), lower_is_better puts critical_high
  // on the right (high values are bad). Same color rule applies.
  if (w <= -1) return "info"; // stretch zone
  if (w === 0) return "resolved";
  if (w === 1) return "warning";
  return "critical";
}

type Stop = { key: StopKey; value: number; pct: number };

function buildStops(thresholds: Thresholds): Stop[] {
  const present: { key: StopKey; value: number }[] = [];
  for (const key of NUMBER_LINE_ORDER) {
    const v = thresholds[key];
    if (v !== undefined && v !== null) {
      present.push({ key, value: v });
    }
  }
  if (present.length === 0) return [];
  // Sort by value to be safe — YAML-authored thresholds shouldn't violate
  // this but defensive sorting keeps the bar visually sane.
  present.sort((a, b) => a.value - b.value);
  const min = present[0].value;
  const max = present[present.length - 1].value;
  const range = max - min || 1;
  // Pad 8% on each side so stops aren't pinned to the bar's edges.
  const padded_min = min - range * 0.08;
  const padded_range = range * 1.16;
  return present.map((s) => ({
    ...s,
    pct: ((s.value - padded_min) / padded_range) * 100,
  }));
}

function formatStopValue(value: number, format?: string | null): string {
  if (!format) return String(value);
  // Python-style format strings appear in workflow YAMLs (e.g. "{value:.1f}%").
  // For the threshold bar the simplest fidelity check is: extract the
  // precision specifier and apply it.
  const m = format.match(/\{value:[^}]*\.(\d+)f[^}]*\}/);
  if (m) {
    const places = parseInt(m[1], 10);
    return value.toFixed(places);
  }
  // Currency-ish format ("$%.1fM" or similar) — fall back to one decimal.
  if (format.includes("$") || format.includes(":,")) {
    return value.toLocaleString();
  }
  return String(value);
}

export function ThresholdBar({
  thresholds,
  direction,
  unit,
  format,
  mode = "read",
  defaultThresholds,
  onChange,
  onReset,
}: {
  thresholds: Thresholds;
  direction: ThresholdDirection;
  unit?: string;
  format?: string | null;
  mode?: ThresholdMode;
  /** Platform default values — used by edit mode to indicate divergence. */
  defaultThresholds?: Thresholds;
  /** Edit mode — called on every input change. */
  onChange?: (next: Thresholds) => void;
  /** Edit mode — called when the user clicks "Reset to default". */
  onReset?: () => void;
}) {
  const stops = useMemo(() => buildStops(thresholds), [thresholds]);

  // Build the segments between consecutive stops, plus the two outer
  // bookends (left of leftmost, right of rightmost). Each segment gets a
  // color and a width-percent.
  const segments = useMemo(() => {
    if (stops.length === 0) return [];
    const out: { color: StopColor; widthPct: number }[] = [];
    const firstStop = stops[0];
    const lastStop = stops[stops.length - 1];
    if (firstStop.pct > 0) {
      out.push({
        color: colorForSegment(null, firstStop.key, direction),
        widthPct: firstStop.pct,
      });
    }
    for (let i = 0; i < stops.length - 1; i++) {
      const left = stops[i];
      const right = stops[i + 1];
      out.push({
        color: colorForSegment(left.key, right.key, direction),
        widthPct: right.pct - left.pct,
      });
    }
    if (lastStop.pct < 100) {
      out.push({
        color: colorForSegment(lastStop.key, null, direction),
        widthPct: 100 - lastStop.pct,
      });
    }
    return out;
  }, [stops, direction]);

  const isOverridden = useMemo(() => {
    if (!defaultThresholds) return false;
    return NUMBER_LINE_ORDER.some(
      (k) => thresholds[k] !== defaultThresholds[k],
    );
  }, [defaultThresholds, thresholds]);

  if (stops.length === 0) {
    return (
      <p className="text-body-sm text-ink-muted">
        No thresholds configured.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {/* Bar */}
      <div
        className="relative h-2 w-full overflow-hidden rounded-sm"
        role="img"
        aria-label={
          direction === "higher_is_better"
            ? "Threshold bar — higher is better, left-to-right reads bad-to-good"
            : direction === "lower_is_better"
              ? "Threshold bar — lower is better, left-to-right reads good-to-bad"
              : "Threshold bar — neutral, target band centred"
        }
      >
        <div className="flex h-full">
          {segments.map((s, idx) => (
            <div
              key={idx}
              className={cn("h-full", COLOR_BG[s.color])}
              style={{ width: `${s.widthPct}%` }}
            />
          ))}
        </div>
        {/* Stop tick marks */}
        {stops.map((s) => (
          <div
            key={s.key}
            className="absolute top-0 h-full w-px bg-ink/40"
            style={{ left: `${s.pct}%` }}
            aria-hidden
          />
        ))}
      </div>

      {/* Stop labels under the bar */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] font-mono sm:grid-cols-3 lg:grid-cols-4">
        {stops.map((s) => {
          const isDefault =
            defaultThresholds && defaultThresholds[s.key] === s.value;
          return (
            <div key={s.key} className="flex items-center gap-1.5">
              <span
                aria-hidden
                className={cn(
                  "inline-block h-[6px] w-[6px] shrink-0 rounded-full",
                  COLOR_DOT[colorForStop(s.key)],
                )}
              />
              <span className="text-ink-faint">
                {STOP_LABEL[s.key]}
              </span>
              <span className="text-ink">
                {formatStopValue(s.value, format)}
                {unit === "percent" && "%"}
              </span>
              {!isDefault && defaultThresholds && (
                <span
                  className="text-navy"
                  title={`Platform default: ${formatStopValue(
                    defaultThresholds[s.key] as number,
                    format,
                  )}`}
                >
                  •
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* Edit-mode inputs */}
      {mode === "edit" && (
        <div className="border-t border-rule-soft pt-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {NUMBER_LINE_ORDER.filter(
              (k) =>
                thresholds[k] !== undefined ||
                (defaultThresholds && defaultThresholds[k] !== undefined),
            ).map((k) => {
              const value = thresholds[k];
              return (
                <label key={k} className="block text-body-sm">
                  <span className="block text-tracked uppercase text-ink-soft">
                    {STOP_LABEL[k]}
                  </span>
                  <input
                    type="number"
                    step="any"
                    value={value === undefined || value === null ? "" : value}
                    onChange={(e) => {
                      if (!onChange) return;
                      const raw = e.target.value;
                      const next: Thresholds = { ...thresholds };
                      if (raw === "") {
                        next[k] = null;
                      } else {
                        const parsed = parseFloat(raw);
                        if (!Number.isNaN(parsed)) next[k] = parsed;
                      }
                      onChange(next);
                    }}
                    className="mt-1 w-full rounded-md border border-rule bg-paper px-2 py-1 text-body-sm font-mono focus:border-navy focus:outline-none focus:ring-2 focus:ring-navy-soft"
                  />
                </label>
              );
            })}
          </div>
          {isOverridden && onReset && (
            <div className="mt-3 flex items-center justify-between">
              <span className="text-body-sm text-navy">
                One or more values diverge from the platform default.
              </span>
              <Button variant="ghost" compact onClick={onReset}>
                Reset to default
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Color of an individual stop dot — same scheme as segments but per-stop. */
function colorForStop(key: StopKey): StopColor {
  if (key === "target") return "resolved";
  if (key === "stretch") return "info";
  if (key === "warning_low" || key === "warning_high") return "warning";
  return "critical";
}
