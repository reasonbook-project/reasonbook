// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { semantic, ramps, type, radius } from '@/design/tokens';

interface FilterChipProps {
  label: string;
  tone?: 'danger' | 'neutral';
  onRemove?: () => void;
}

export function FilterChip({ label, tone = 'danger', onRemove }: FilterChipProps) {
  const colors = tone === 'danger'
    ? { bg: semantic.danger.bg, text: ramps.red[800] }
    : { bg: semantic.surface.secondary, text: semantic.text.secondary };

  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '6px',
      fontSize: type.size.sm,
      padding: '3px 10px',
      background: colors.bg,
      color: colors.text,
      borderRadius: radius.pill,
      fontWeight: 500,
    }}>
      <i className="ti ti-filter" style={{ fontSize: '12px' }} aria-hidden="true" />
      {label}
      {onRemove && (
        <button
          onClick={onRemove}
          aria-label={`Remove ${label} filter`}
          style={{
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            color: 'inherit',
            display: 'inline-flex',
            alignItems: 'center',
          }}
        >
          <i className="ti ti-x" style={{ fontSize: '12px' }} aria-hidden="true" />
        </button>
      )}
    </span>
  );
}
