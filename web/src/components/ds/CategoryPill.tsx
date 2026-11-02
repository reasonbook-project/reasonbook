// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import { categories, components } from '@/design/tokens';

export type Category = 'credit' | 'compliance' | 'ops';

interface CategoryPillProps {
  category: Category;
  onClick?: () => void;
  label?: string; // override display label
}

const labels: Record<Category, string> = {
  credit: 'Credit',
  compliance: 'Compliance',
  ops: 'Ops',
};

export function CategoryPill({ category, onClick, label }: CategoryPillProps) {
  const colors = categories[category];
  const isInteractive = Boolean(onClick);

  return (
    <span
      role={isInteractive ? 'button' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
      onClick={onClick}
      onKeyDown={isInteractive ? (e) => { if (e.key === 'Enter') onClick?.(); } : undefined}
      style={{
        fontSize: components.pill.fontSize,
        padding: components.pill.padding,
        borderRadius: components.pill.radius,
        background: colors.bg,
        color: colors.text,
        fontWeight: 500,
        display: 'inline-block',
        cursor: isInteractive ? 'pointer' : 'default',
        userSelect: 'none',
      }}
    >
      {label ?? labels[category]}
    </span>
  );
}
