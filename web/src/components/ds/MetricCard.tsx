// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';
import { components, semantic, type, ramps } from '@/design/tokens';

interface MetricCardProps {
  label: string;
  value: number | string;
  variant?: 'default' | 'alert';
  delta?: { value: number; direction: 'up' | 'down'; tone?: 'positive' | 'negative' | 'neutral' };
  footnote?: string;
  rightLabel?: string;
  children?: ReactNode; // for breakdowns, sparklines, etc.
}

function formatValue(value: number | string): string {
  if (typeof value === 'string') return value;
  return new Intl.NumberFormat('en-US').format(Math.round(value));
}

function DeltaIndicator({ delta }: { delta: NonNullable<MetricCardProps['delta']> }) {
  const arrow = delta.direction === 'up' ? '▲' : '▼';
  const tone = delta.tone ?? 'neutral';
  const color =
    tone === 'positive' ? semantic.success.text :
    tone === 'negative' ? semantic.danger.text :
    semantic.text.secondary;
  return (
    <span style={{ fontSize: type.size.xs, color, fontWeight: 500 }}>
      {arrow} {Math.abs(Math.round(delta.value))}
    </span>
  );
}

/**
 * Metric card primitive. Two variants:
 *
 *   - ``default`` — paper ground, ink number, used for Open / Decided
 *   - ``alert`` — critical-bg ground, left border, larger number, used
 *     for At Risk
 *
 * Layout contract: the card is a flex column that fills its grid cell
 * (``height: 100%``). Header (label + delta/rightLabel) and value pin
 * to the top. Footnote and ``children`` (sparkline / breakdown pills /
 * etc.) pin to the bottom. A flex spacer in the middle eats any extra
 * vertical space, so multiple cards in the same grid row align their
 * bottom edges regardless of content depth.
 *
 * When neither ``footnote`` nor ``children`` is set, the bottom group
 * is omitted entirely — no empty div eating space, no spacer ghost.
 */
export function MetricCard({ label, value, variant = 'default', delta, footnote, rightLabel, children }: MetricCardProps) {
  const isAlert = variant === 'alert';

  const cardStyle = isAlert ? {
    background: components.metricCardAlert.bg,
    borderLeft: components.metricCardAlert.borderLeft,
    borderRadius: components.metricCardAlert.radius,
    borderTopLeftRadius: 0,
    borderBottomLeftRadius: 0,
    padding: components.metricCardAlert.padding,
  } : {
    background: components.metricCard.bg,
    borderRadius: components.metricCard.radius,
    padding: components.metricCard.padding,
  };

  const labelColor = isAlert ? ramps.red[800] : semantic.text.secondary;
  const valueColor = isAlert ? ramps.red[800] : semantic.text.primary;
  const valueSize = isAlert ? type.size.metricLarge : type.size.metric;

  const hasBottomGroup = Boolean(footnote) || Boolean(children);

  return (
    <div
      style={{
        ...cardStyle,
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      }}
    >
      {/* Top group — label row + value (anchored top). */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <span style={{
            fontSize: type.size.xs,
            letterSpacing: type.letterSpacing.label,
            color: labelColor,
            fontWeight: 500,
            textTransform: 'uppercase',
          }}>
            {label}
          </span>
          {delta && <DeltaIndicator delta={delta} />}
          {rightLabel && !delta && (
            <span style={{ fontSize: type.size.xs, color: labelColor, fontWeight: 500 }}>{rightLabel}</span>
          )}
        </div>
        <div style={{
          fontSize: valueSize,
          fontWeight: type.weight.bold,
          fontVariantNumeric: 'tabular-nums',
          lineHeight: type.lineHeight.tight,
          color: valueColor,
        }}>
          {formatValue(value)}
        </div>
      </div>

      {/*
        Spacer + bottom group. Only rendered when there's actual bottom
        content (footnote OR children). Otherwise the card is just the
        top group at the top of its cell — no ghost spacer, no empty
        bottom div.
      */}
      {hasBottomGroup && (
        <>
          <div style={{ flex: 1, minHeight: '8px' }} aria-hidden />
          <div>
            {footnote && (
              <div style={{ fontSize: type.size.xs, color: semantic.text.tertiary }}>
                {footnote}
              </div>
            )}
            {children && (
              <div style={{ marginTop: footnote ? '6px' : 0 }}>{children}</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
