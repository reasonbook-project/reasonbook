// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { semantic, ramps, type } from '@/design/tokens';

interface AvatarProps {
  initials: string;
  size?: number;
  variant?: 'info' | 'neutral';
}

export function Avatar({ initials, size = 22, variant = 'info' }: AvatarProps) {
  const colors = variant === 'info'
    ? { bg: ramps.blue[50], text: ramps.blue[800] }
    : { bg: semantic.surface.secondary, text: semantic.text.secondary };

  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: colors.bg,
        color: colors.text,
        fontSize: size < 24 ? '10px' : '12px',
        fontWeight: type.weight.bold,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      {initials}
    </div>
  );
}
