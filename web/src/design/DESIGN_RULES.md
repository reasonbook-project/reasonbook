# DGP Design Rules

This is the working-copy mirror of `docs/architecture/dgp-design-rules.md`, located next to `tokens.ts` so they ship together.

If the two files diverge, treat `docs/architecture/dgp-design-rules.md` as canonical and sync this one.

---

See `docs/architecture/dgp-design-rules.md` for the full ruleset.

## Quick reference

**Hard rules:**
1. Import colors from `@/design/tokens` — no inline hex
2. Two font weights only: 400, 500 (never 600 or 700)
3. Sentence case for all text
4. Borders: 0.5px (or 4px alert, 2px featured)
5. No box-shadows, gradients, glow, blur
6. No emoji — Tabler outline icons only
7. Bold for headings/labels only, never mid-sentence
8. Round every displayed number
9. Color encodes meaning (red=danger, amber=warning, etc.)
10. Max 2-3 colors per view
11. Never use `var(--ink-*)` / `var(--bg-*)` / `var(--rule-*)` / `var(--navy*)` directly as a color in TSX inline styles or SVG attributes. They're raw HSL components for Tailwind — invalid as standalone colors → silent transparent stroke. Import from `@/design/tokens` instead. (`var(--color-*)` is full hex and safe, but tokens are preferred for consistency.)

**Imports cheat sheet:**
```tsx
import { semantic, ramps, type, components, radius, border, sla, categories } from '@/design/tokens';
import { MetricCard, PostureHeadline, CategoryPill, SLAIndicator, FilterChip, Avatar } from '@/components/ds';
import { TopRail, DecisionQueueDrawer } from '@/components/dashboard';
```

**When in doubt:** read the canonical file at `docs/architecture/dgp-design-rules.md`.
