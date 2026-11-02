// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from 'react';
import { sla, ramps } from '@/design/tokens';

interface SLAIndicatorProps {
  deadline: string | Date; // ISO string or Date
}

function getTierAndFormat(msRemaining: number) {
  const hours = msRemaining / (1000 * 60 * 60);
  const absHours = Math.abs(hours);
  const h = Math.floor(absHours);
  const m = Math.floor((absHours - h) * 60);
  const formatted = `${h}h ${m.toString().padStart(2, '0')}m`;

  if (hours < 0) {
    return { tier: 'breached' as const, formatted: `-${formatted}`, color: ramps.red[900], dot: ramps.red[600] };
  }
  if (hours <= sla.critical.maxHours) {
    return { tier: 'critical' as const, formatted, color: sla.critical.textColor, dot: sla.critical.dotColor };
  }
  if (hours <= sla.warning.maxHours) {
    return { tier: 'warning' as const, formatted, color: sla.warning.textColor, dot: sla.warning.dotColor };
  }
  return { tier: 'normal' as const, formatted, color: sla.normal.textColor, dot: sla.normal.dotColor };
}

export function SLAIndicator({ deadline }: SLAIndicatorProps) {
  const target = typeof deadline === 'string' ? new Date(deadline) : deadline;
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, []);

  const remaining = target.getTime() - now;
  const { formatted, color, dot } = getTierAndFormat(remaining);

  return (
    <span
      style={{
        color,
        fontWeight: 500,
        fontVariantNumeric: 'tabular-nums',
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: dot,
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      {formatted}
    </span>
  );
}
