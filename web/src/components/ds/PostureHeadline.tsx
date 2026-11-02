// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { semantic, ramps, type, radius } from '@/design/tokens';

interface PostureHeadlineProps {
  atRiskCount: number;
  slaWindow?: string; // e.g. "24h"
  onReview: () => void;
}

export function PostureHeadline({ atRiskCount, slaWindow = '24h', onReview }: PostureHeadlineProps) {
  if (atRiskCount === 0) return null;

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '10px',
      padding: '12px 14px',
      background: semantic.danger.bg,
      borderLeft: `3px solid ${ramps.red[600]}`,
      borderRadius: radius.md,
      borderTopLeftRadius: 0,
      borderBottomLeftRadius: 0,
      marginBottom: '18px',
    }}>
      <i
        className="ti ti-alert-triangle"
        style={{ fontSize: '18px', color: ramps.red[800] }}
        aria-hidden="true"
      />
      <span style={{
        fontSize: type.size.body,
        fontWeight: type.weight.bold,
        color: ramps.red[900],
      }}>
        {atRiskCount} {atRiskCount === 1 ? 'decision needs' : 'decisions need'} attention in the next {slaWindow}
      </span>
      <button
        onClick={onReview}
        style={{
          marginLeft: 'auto',
          fontSize: type.size.sm,
          padding: '4px 10px',
          borderRadius: '6px',
          border: `0.5px solid ${semantic.border.secondary}`,
          background: 'transparent',
          cursor: 'pointer',
          fontWeight: type.weight.bold,
        }}
      >
        Review now ↗
      </button>
    </div>
  );
}
