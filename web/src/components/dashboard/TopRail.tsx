// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';
import { semantic, type, radius, border, ramps } from '@/design/tokens';
import { MetricCard } from '@/components/ds/MetricCard';
import { PostureHeadline } from '@/components/ds/PostureHeadline';
import { CategoryPill } from '@/components/ds/CategoryPill';

interface PostureData {
  open: { value: number; delta: number | null };
  decidedToday: { value: number; delta: number | null; avgCycleDays: number | null };
  atRisk: {
    value: number;
    deltaSinceYesterday: number | null;
    slaWindow: string;
    breakdown: { credit: number; compliance: number; ops: number };
  };
}

interface TopRailProps {
  agencyName: string;
  agencySubtitle: string;
  posture: PostureData;
  onReviewAtRisk: () => void;
  onFilterCategory: (cat: 'credit' | 'compliance' | 'ops') => void;
  /**
   * Optional content appended below the Open card's value/footnote. Typical
   * use: a sparkline. Omit → Open card renders with no extra slot content
   * (current default behavior).
   */
  openExtra?: ReactNode;
  /** Optional content appended to the Decided card. Omit → no extra slot. */
  decidedExtra?: ReactNode;
  /**
   * Optional content appended AFTER the existing breakdown pills inside the
   * At Risk card. Omit → only the existing delta + pills render
   * (current default behavior).
   */
  atRiskExtra?: ReactNode;
}

/**
 * Placeholder rendered in place of an Open-tile sparkline when no trend
 * data is available. Dashed mid-gray line communicates "no data yet"
 * without text clutter. Full-width inside the tile so the three top-rail
 * cards stay visually balanced even when one's secondary content is
 * empty.
 *
 * Token choices:
 * - ``ramps.gray[400]`` (#888780) — same color as ``semantic.text.tertiary``;
 *   referencing the ramp directly is a deliberate "this is a structural
 *   element, not text" signal per the design rules.
 * - opacity 0.7 + dash pattern — visible enough to read as a reserved
 *   slot, subtle enough not to compete with real data when it lands.
 */
function SparklinePlaceholder() {
  return (
    <svg
      width="100%"
      height="20"
      viewBox="0 0 120 20"
      style={{ marginTop: '6px', opacity: 0.7 }}
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <line
        x1="0"
        y1="10"
        x2="120"
        y2="10"
        stroke={ramps.gray[400]}
        strokeWidth="1.2"
        strokeDasharray="2 3"
      />
    </svg>
  );
}

export function TopRail({
  agencyName,
  agencySubtitle,
  posture,
  onReviewAtRisk,
  onFilterCategory,
  openExtra,
  decidedExtra,
  atRiskExtra,
}: TopRailProps) {
  const { open, decidedToday, atRisk } = posture;

  // Build category breakdown array, sorted by count desc
  const breakdownEntries = Object.entries(atRisk.breakdown)
    .map(([category, count]) => ({ category: category as 'credit' | 'compliance' | 'ops', count }))
    .filter((entry) => entry.count > 0)
    .sort((a, b) => b.count - a.count);

  // Layout polish (post-Phase-4b visual review). Each tile's secondary
  // content is always rendered so the three cards read at similar
  // density even when data is missing:
  //   - Open: sparkline OR a faint horizontal placeholder line
  //   - Decided: "avg cycle X.Xd" OR "avg cycle —"
  //   - At Risk: already populated via the existing breakdown pills
  // The wrappers carry `min-h-[120px]` so all three align to a common
  // baseline regardless of content height (At Risk usually drives the
  // row height via its delta + pills; the floor keeps Open/Decided
  // visually substantial when the row would otherwise feel "short").
  const openSlot = openExtra ?? <SparklinePlaceholder />;
  const decidedFootnote =
    decidedToday.avgCycleDays !== null && decidedToday.avgCycleDays >= 0
      ? `avg cycle ${decidedToday.avgCycleDays.toFixed(1)}d`
      : 'avg cycle —';

  // Defensive UI guard (mirrors At Risk's pattern at the breakdown line
  // below): suppress the delta indicator when ``delta === value``. That
  // shape is almost always a fresh seed or a regression in delta
  // semantics — rendering "▲ 56 / 56" is noise either way. Backend
  // invariant warnings (route handler) catch the same condition for
  // ops visibility.
  const openDeltaProp =
    open.delta !== null && open.delta !== open.value
      ? {
          value: open.delta,
          direction: (open.delta >= 0 ? 'up' : 'down') as 'up' | 'down',
          tone: 'neutral' as const,
        }
      : undefined;
  const decidedDeltaProp =
    decidedToday.delta !== null && decidedToday.delta !== decidedToday.value
      ? {
          value: decidedToday.delta,
          direction: (decidedToday.delta >= 0 ? 'up' : 'down') as 'up' | 'down',
          tone: 'neutral' as const,
        }
      : undefined;

  return (
    <div style={{ padding: '1.25rem 1.5rem', background: semantic.surface.primary, borderRadius: radius.lg, border: border.default }}>
      {/* Eyebrow + de-emphasised tenant line — this card is the agency's
          own posture readout, not a matter on its desk. Lead with the
          frame ("you are here") so the eye drops to the data rows below
          instead of mistaking the agency name for a matter title. */}
      <div style={{
        margin: '0 0 4px',
        fontSize: type.size.xs,
        letterSpacing: type.letterSpacing.label,
        color: semantic.text.tertiary,
        fontWeight: 500,
        textTransform: 'uppercase',
      }}>
        Agency posture
      </div>
      <div style={{ margin: '0 0 16px', display: 'flex', alignItems: 'baseline', gap: '10px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: type.size.lg, fontWeight: type.weight.bold, color: semantic.text.primary }}>
          {agencyName}
        </span>
        <span style={{ fontSize: type.size.sm, color: semantic.text.secondary }}>
          {agencySubtitle}
        </span>
      </div>

      <PostureHeadline
        atRiskCount={atRisk.value}
        slaWindow={atRisk.slaWindow}
        onReview={onReviewAtRisk}
      />

      <h2 style={{
        margin: 0,
        marginBottom: '10px',
        fontSize: type.size.xs,
        letterSpacing: type.letterSpacing.label,
        color: semantic.text.tertiary,
        fontWeight: 500,
        textTransform: 'uppercase',
      }}>
        Decisions in flight
      </h2>

      {/*
        Mobile-first responsive grid. Source order is [At Risk, Open, Decided]
        so the most urgent card surfaces first on narrow viewports (single
        column). Tailwind `md:order-*` reorders to [Open, Decided, At Risk]
        at ≥768px (the desktop layout matching the executive scan mockup).
        Hybrid pattern: Tailwind for media queries, inline-style for token-
        driven color/typography/spacing throughout the rest of the file.
      */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_1fr_1.6fr]">
        <div className="md:order-3 min-h-[120px]">
          <MetricCard
            label="At risk"
            value={atRisk.value}
            variant="alert"
            rightLabel={`SLA < ${atRisk.slaWindow}`}
          >
            {atRisk.deltaSinceYesterday !== null && atRisk.deltaSinceYesterday !== atRisk.value && (
              <div style={{ fontSize: type.size.sm, color: ramps.red[600], marginBottom: '8px' }}>
                {atRisk.deltaSinceYesterday >= 0 ? '▲' : '▼'} {Math.abs(atRisk.deltaSinceYesterday)} since yesterday
              </div>
            )}
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {breakdownEntries.map(({ category, count }) => (
                <CategoryPill
                  key={category}
                  category={category}
                  label={`${count} ${category}`}
                  onClick={() => onFilterCategory(category)}
                />
              ))}
            </div>
            {atRiskExtra}
          </MetricCard>
        </div>

        <div className="md:order-1 min-h-[120px]">
          <MetricCard
            label="Open"
            value={open.value}
            delta={openDeltaProp}
          >
            {openSlot}
          </MetricCard>
        </div>

        <div className="md:order-2 min-h-[120px]">
          <MetricCard
            label="Decided today"
            value={decidedToday.value}
            delta={decidedDeltaProp}
            footnote={decidedFootnote}
          >
            {decidedExtra}
          </MetricCard>
        </div>
      </div>
    </div>
  );
}
