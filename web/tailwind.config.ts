// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Tailwind theme tokens.
 *
 * Two layers coexist during the SaaS rebrand migration:
 *   1. New SaaS tokens (navy, ink, rule, paper, bg, etc.) consuming
 *      hsl(var(--token)) per the SaaS frontend spec v1.0 §3.1.
 *      shadcn shims (primary, secondary, muted, accent, card) repoint here.
 *   2. Legacy Phase 6 aliases (brand-blue, deep-navy, cream, semantic
 *      crit/warn/info/resolved) kept as-is until the step 13 sweep.
 */
const config: Config = {
  // Dark mode tokens are defined but the theme is out of scope for v1.
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx,mdx}"],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        // ── SaaS rebrand tokens (§3.1) ───────────────────────────────────
        navy: "hsl(var(--navy))",
        "navy-deep": "hsl(var(--navy-deep))",
        "navy-soft": "hsl(var(--navy-soft))",
        "navy-tint": "hsl(var(--navy-tint))",

        ink: "hsl(var(--ink))",
        "ink-soft": "hsl(var(--ink-soft))",
        "ink-muted": "hsl(var(--ink-muted))",
        "ink-faint": "hsl(var(--ink-faint))",

        rule: "hsl(var(--rule))",
        "rule-soft": "hsl(var(--rule-soft))",
        "rule-faint": "hsl(var(--rule-faint))",

        paper: "hsl(var(--paper))",
        bg: "hsl(var(--bg))",
        "bg-warm": "hsl(var(--bg-warm))",

        "accent-warning": "hsl(var(--accent-warning))",
        "accent-success": "hsl(var(--accent-success))",

        // ── shadcn shims, repointed at SaaS tokens ───────────────────────
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        ring: "hsl(var(--ring))",
        input: "hsl(var(--input))",

        // ── Reasonbook brand layer ─────────────────────────────────────────
        // Token source for `bespoke-components.css`. New surfaces (bundle
        // page first) consume these via Tailwind utilities; the older
        // teal-tinted tokens above remain authoritative for existing screens
        // until a coordinated sweep retires them.
        //
        // Hex values reconciled to the brand guide (#3162AA blue) per
        // docs/architecture/backlog/02_style_fix/RECONCILE-tailwind.md §2
        // — the layer was first introduced with the generic Tailwind blue
        // (#1D4ED8); this corrects it. The layer is retired entirely in
        // the step-13 sweep so every ``bg-brand`` points at ``bg-navy``.
        brand: {
          DEFAULT: "#3162AA",
          "2": "#154E8C",
          ink: "#0B0F1A",
        },
        "paper-warm": "#FAF9F5",
        cleared: "#27B16B",  // "on the record" ledger dot
        flag: "#E5484D",     // exception / fraud flag
        tier: {
          federal: "#3162AA",
          state: "#0F6E56",
          contractor: "#534AB7",
        },

        // ── Component-layer additions (RECONCILE-tailwind.md §3) ──────────
        // Tokens the bespoke-components.css needs to resolve its
        // @apply rules. Hex matches the existing brand/tier style. Reuses
        // existing critical/warning/info/resolved semantic groups for
        // thresholds and flag pills — no new threshold tokens added.
        forensic: "#0B0F1A",            // dark nav / record-dark surface
        "ink-inv": "#EAEEF6",           // light text on dark
        "ink-inv-2": "#AEB9CE",         // muted light text on dark (nav items)
        "rule-warm": "#E7E0D2",         // hairline on the paper-warm record surface
        "rule-dark": "#26314A",         // hairline on dark surfaces
        "tint-state": "#E1F5EE",
        "tint-contractor": "#EEEDFE",
        // Tier badges sitting on the forensic preview pane — paired
        // dark-bg / light-text per tier. Distinct from the light-surface
        // tint-{state,contractor} above because the contrast pivots:
        // light text on dark bg here, dark text on light bg above.
        "tint-fed-dark": "#15334F",
        "tint-fed-text": "#7FB6E6",
        "tint-state-dark": "#103B32",
        "tint-state-text": "#56C9A0",
        "tint-contractor-dark": "#2B2752",
        "tint-contractor-text": "#A99FF0",
        // Rail-specific signature color — the light-navy used for active
        // text in the dark sidebar. Distinct from the brand navy because
        // it has to sit legibly on the forensic background.
        "nav-active": "#85B7EB",

        // ── Canonical UI style tokens (§18.6 + ADR-09) ─────────────────
        // Source: docs/architecture/UI Surface/dp-ui.css. Light workspace +
        // white rail + dark principle ticker. Wiring the :root tokens from
        // dp-ui.css as Tailwind utilities.
        canvas: "#EEF1F6",              // --bg, workspace surface
        panel: "#FFFFFF",               // --panel, card surface
        "panel-2": "#F6F8FC",           // --panel-2, sunken / hover surface
        rail: "#FFFFFF",                // --rail, white rail
        line: "rgba(20,30,50,.10)",     // --line, hairline
        "line-2": "rgba(20,30,50,.16)", // --line-2, stronger hairline
        teal: "#0E9E84",                // --teal, secondary accent
        "teal-soft": "rgba(14,158,132,.12)",
        amber: "#B7791F",               // --amber
        "amber-soft": "rgba(214,158,46,.16)",
        "flag-soft": "rgba(216,73,44,.12)",
        ok: "#1E7A54",                  // --ok, success
        "ok-soft": "rgba(30,122,84,.13)",
        // Tiered text tokens (replaces ad-hoc gray usage on light surfaces)
        t1: "#1A2233",                  // --t1, primary text
        t2: "#54607A",                  // --t2, secondary text
        t3: "#8893A6",                  // --t3, tertiary / muted
        // Dark principle ticker — single signature dark accent
        principle: "#0C1019",
        "principle-text": "#C8D2E2",

        // Semantic urgency dots (decision-row badges) — unchanged
        critical: {
          bg: "var(--color-critical-bg)",
          text: "var(--color-critical-text)",
          dot: "var(--color-critical-dot)",
        },
        warning: {
          bg: "var(--color-warning-bg)",
          text: "var(--color-warning-text)",
          dot: "var(--color-warning-dot)",
        },
        info: {
          bg: "var(--color-info-bg)",
          text: "var(--color-info-text)",
          dot: "var(--color-info-dot)",
        },
        resolved: {
          bg: "var(--color-resolved-bg)",
          text: "var(--color-resolved-text)",
          dot: "var(--color-resolved-dot)",
        },
      },

      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        // ADR-09: Space Grotesk for display / headings; Inter stays as body.
        display: [
          "Space Grotesk",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "IBM Plex Mono",
          "ui-monospace",
          "SF Mono",
          "Menlo",
          "monospace",
        ],
      },

      fontSize: {
        // ── SaaS rebrand scale (§3.2) ────────────────────────────────────
        // Page-level display (clamped, fluid)
        display: [
          "clamp(2.25rem, 4vw, 3.25rem)",
          {
            lineHeight: "1.05",
            letterSpacing: "-0.025em",
            fontWeight: "600",
          },
        ],
        page: [
          "clamp(1.75rem, 3vw, 2.5rem)",
          {
            lineHeight: "1.08",
            letterSpacing: "-0.025em",
            fontWeight: "600",
          },
        ],
        section: [
          "1.625rem",
          {
            lineHeight: "1.20",
            letterSpacing: "-0.018em",
            fontWeight: "600",
          },
        ],
        subsection: [
          "1.125rem",
          {
            lineHeight: "1.30",
            letterSpacing: "-0.01em",
            fontWeight: "600",
          },
        ],
        stat: [
          "2.25rem",
          {
            lineHeight: "1",
            letterSpacing: "-0.025em",
            fontWeight: "600",
            fontFeatureSettings: '"tnum"',
          },
        ],
        "stat-lg": [
          "3rem",
          {
            lineHeight: "1",
            letterSpacing: "-0.03em",
            fontWeight: "600",
            fontFeatureSettings: '"tnum"',
          },
        ],
        "mono-label": [
          "0.6875rem",
          {
            lineHeight: "1.40",
            letterSpacing: "0.14em",
            fontWeight: "500",
          },
        ],
        "mono-num": [
          "0.6875rem",
          {
            lineHeight: "1.30",
            letterSpacing: "0.06em",
            fontWeight: "500",
          },
        ],

        // ── Legacy Phase 6 scale — kept until step 13 sweep ──────────────
        "heading-xl": [
          "30px",
          { lineHeight: "1.2", letterSpacing: "-0.015em" },
        ],
        "heading-l": [
          "22px",
          { lineHeight: "1.3", letterSpacing: "-0.01em" },
        ],
        "heading-m": [
          "20px",
          { lineHeight: "1.35", letterSpacing: "-0.005em" },
        ],
        "heading-s": ["16px", { lineHeight: "1.4" }],
        body: ["14px", { lineHeight: "1.55" }],
        "body-sm": ["12px", { lineHeight: "1.5" }],
        caption: ["11px", { lineHeight: "1.4" }],
        tracked: ["11px", { lineHeight: "1.4", letterSpacing: "0.07em" }],
        "mono-sm": ["11px", { lineHeight: "1.4" }],
        "mono-md": ["20px", { lineHeight: "1.2" }],
      },

      letterSpacing: {
        tight: "-0.005em",
        tighter: "-0.01em",
        tightest: "-0.015em",
        tracked: "0.06em",
        "tracked-wide": "0.08em",
        "tracked-mono": "0.14em",
      },

      fontWeight: {
        normal: "400",
        medium: "500",
        semibold: "600",
      },

      // ── SaaS rebrand spacing aliases (§3.3) ────────────────────────────
      spacing: {
        gutter: "2rem",
        "gutter-lg": "4rem",
        section: "5rem",
        compact: "3.5rem",
      },

      borderRadius: {
        sm: "4px",
        md: "8px",
        lg: "var(--radius)",
      },
      borderWidth: {
        hairline: "0.5px",
        shelf: "1.5px",
      },
    },
  },
  plugins: [animate],
};

export default config;
