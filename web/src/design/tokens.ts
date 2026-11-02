// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * DGP Design Tokens
 * Single source of truth for colors, typography, spacing, and component values.
 *
 * RULES:
 * - Never use hex values outside this file
 * - Never invent new ramps or stops
 * - Import tokens, don't redefine them
 */

// ============================================================================
// COLOR RAMPS — 9 ramps, 7 stops each (50 lightest → 900 darkest)
// ============================================================================

export const ramps = {
  purple: {
    50: '#EEEDFE', 100: '#CECBF6', 200: '#AFA9EC', 400: '#7F77DD',
    600: '#534AB7', 800: '#3C3489', 900: '#26215C',
  },
  teal: {
    50: '#E1F5EE', 100: '#9FE1CB', 200: '#5DCAA5', 400: '#1D9E75',
    600: '#0F6E56', 800: '#085041', 900: '#04342C',
  },
  coral: {
    50: '#FAECE7', 100: '#F5C4B3', 200: '#F0997B', 400: '#D85A30',
    600: '#993C1D', 800: '#712B13', 900: '#4A1B0C',
  },
  pink: {
    50: '#FBEAF0', 100: '#F4C0D1', 200: '#ED93B1', 400: '#D4537E',
    600: '#993556', 800: '#72243E', 900: '#4B1528',
  },
  gray: {
    50: '#F1EFE8', 100: '#D3D1C7', 200: '#B4B2A9', 400: '#888780',
    600: '#5F5E5A', 800: '#444441', 900: '#2C2C2A',
  },
  blue: {
    50: '#E6F1FB', 100: '#B5D4F4', 200: '#85B7EB', 400: '#378ADD',
    600: '#185FA5', 800: '#0C447C', 900: '#042C53',
  },
  green: {
    50: '#EAF3DE', 100: '#C0DD97', 200: '#97C459', 400: '#639922',
    600: '#3B6D11', 800: '#27500A', 900: '#173404',
  },
  amber: {
    50: '#FAEEDA', 100: '#FAC775', 200: '#EF9F27', 400: '#BA7517',
    600: '#854F0B', 800: '#633806', 900: '#412402',
  },
  red: {
    50: '#FCEBEB', 100: '#F7C1C1', 200: '#F09595', 400: '#E24B4A',
    600: '#A32D2D', 800: '#791F1F', 900: '#501313',
  },
} as const;

// ============================================================================
// SEMANTIC COLORS — use these in components, not ramp stops directly
// ============================================================================

export const semantic = {
  // Status meanings
  danger: { bg: ramps.red[50], border: ramps.red[400], text: ramps.red[800], textStrong: ramps.red[900] },
  warning: { bg: ramps.amber[50], border: ramps.amber[400], text: ramps.amber[800], textStrong: ramps.amber[900] },
  success: { bg: ramps.teal[50], border: ramps.teal[400], text: ramps.teal[800], textStrong: ramps.teal[900] },
  info: { bg: ramps.blue[50], border: ramps.blue[400], text: ramps.blue[800], textStrong: ramps.blue[900] },

  // Surfaces
  surface: {
    primary: '#FFFFFF',
    secondary: '#F7F6F2',
    tertiary: '#F1EFE8',
  },

  // Text
  text: {
    primary: '#2C2C2A',
    secondary: '#5F5E5A',
    tertiary: '#888780',
  },

  // Borders
  border: {
    tertiary: 'rgba(0,0,0,0.10)',
    secondary: 'rgba(0,0,0,0.20)',
    primary: 'rgba(0,0,0,0.30)',
  },
} as const;

// ============================================================================
// CATEGORY COLORS — DGP-specific decision categories
// ============================================================================

export const categories = {
  credit: { bg: 'rgba(121,31,31,0.12)', text: ramps.red[800] },
  compliance: { bg: 'rgba(163,45,45,0.12)', text: ramps.red[600] },
  ops: { bg: 'rgba(216,90,48,0.15)', text: ramps.coral[600] },
} as const;

// ============================================================================
// TYPOGRAPHY — only these sizes and weights exist
// ============================================================================

export const type = {
  family: {
    sans: 'var(--font-sans, system-ui, -apple-system, sans-serif)',
    serif: 'var(--font-serif, Georgia, serif)',
    mono: 'var(--font-mono, ui-monospace, monospace)',
  },
  size: {
    xs: '11px',   // labels, captions, micro-meta
    sm: '12px',   // secondary UI text
    base: '13px', // table cells, dense UI
    body: '14px', // primary UI text
    md: '15px',   // section headers
    lg: '16px',   // h3, prose body
    xl: '18px',   // h2
    xxl: '22px',  // h1
    metric: '28px',     // metric card numbers
    metricLarge: '36px', // emphasized metric (e.g. At Risk)
  },
  weight: {
    regular: 400,
    bold: 500,
  },
  lineHeight: {
    tight: 1.1,
    snug: 1.4,
    body: 1.7,
  },
  letterSpacing: {
    label: '0.06em', // ALL CAPS labels
    tight: '-0.01em',
  },
} as const;

// ============================================================================
// SPACING — rem for layout, px for component internals
// ============================================================================

export const space = {
  xs: '4px',
  sm: '8px',
  md: '12px',
  lg: '16px',
  xl: '24px',
  xxl: '32px',
  // Vertical rhythm (use rem)
  section: '1rem',
  sectionLg: '1.5rem',
  sectionXl: '2rem',
} as const;

// ============================================================================
// RADIUS
// ============================================================================

export const radius = {
  sm: '4px',
  md: '8px',   // most UI elements
  lg: '12px',  // cards
  xl: '16px',
  pill: '10px', // small pills
  round: '50%',
} as const;

// ============================================================================
// BORDERS — always 0.5px, never thicker (except 2px featured accent)
// ============================================================================

export const border = {
  default: `0.5px solid ${semantic.border.tertiary}`,
  emphasis: `0.5px solid ${semantic.border.secondary}`,
  featured: `2px solid ${ramps.blue[600]}`, // ONLY for "most popular" / featured
  alertLeft: `4px solid ${ramps.red[400]}`, // alert card accent only
} as const;

// ============================================================================
// COMPONENT TOKENS — pre-built primitives
// ============================================================================

export const components = {
  card: {
    bg: semantic.surface.primary,
    border: border.default,
    radius: radius.lg,
    padding: '1rem 1.25rem',
  },
  metricCard: {
    bg: semantic.surface.secondary,
    radius: radius.md,
    padding: '14px 16px',
    labelSize: type.size.xs,
    labelLetterSpacing: type.letterSpacing.label,
    valueSize: type.size.metric,
    valueWeight: type.weight.bold,
  },
  metricCardAlert: {
    bg: ramps.red[50],
    borderLeft: border.alertLeft,
    radius: radius.md,
    radiusLeft: '0',
    padding: '14px 16px',
    valueSize: type.size.metricLarge,
    valueColor: ramps.red[800],
  },
  pill: {
    fontSize: type.size.xs,
    padding: '2px 8px',
    radius: radius.pill,
  },
  button: {
    fontSize: type.size.sm,
    padding: '4px 10px',
    radius: '6px',
    border: border.emphasis,
  },
  input: {
    height: '36px',
    radius: radius.md,
    border: border.default,
  },
} as const;

// ============================================================================
// SLA TIERS — DGP-specific decision urgency thresholds
// ============================================================================

export const sla = {
  critical: { maxHours: 8, dotColor: ramps.red[400], textColor: ramps.red[800] },
  warning: { maxHours: 24, dotColor: ramps.amber[200], textColor: ramps.amber[400] },
  normal: { maxHours: Infinity, dotColor: ramps.gray[200], textColor: ramps.gray[600] },
} as const;
