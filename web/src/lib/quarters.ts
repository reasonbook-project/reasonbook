// Copyright 2026 Data Visuals LLC
// SPDX-License-Identifier: Apache-2.0

/**
 * Quarter math helpers used across the governance roadmap surfaces.
 *
 * Quarters are represented as plain strings in ``YYYY-QN`` form, matching
 * the storage shape on platform.governance_initiatives.started_quarter
 * (etc.) and the per-milestone target_quarter values. Strings are the
 * natural form the UI renders and they sort lexicographically as long as
 * the year is zero-padded to 4 digits.
 *
 * These were originally private helpers inside PromoteInitiativeModal
 * (Prompt 1); extracted here in Prompt 2 because the roadmap timeline
 * has many independent consumers (column headers, bar positioning,
 * today-line, milestone display, drawer milestone display).
 */

const QUARTER_RE = /^(\d{4})-Q([1-4])$/;

/** UTC-anchored current quarter for the runtime clock. */
export function currentQuarter(date: Date = new Date()): string {
  const year = date.getUTCFullYear();
  const q = Math.floor(date.getUTCMonth() / 3) + 1;
  return `${year}-Q${q}`;
}

/** ``YYYY-QN`` + offset → ``YYYY-QN``. Negative offsets shift backward. */
export function quarterFromOffset(start: string, offset: number): string {
  const m = QUARTER_RE.exec(start);
  if (!m) throw new Error(`invalid quarter string: ${start}`);
  const year = Number(m[1]);
  const q = Number(m[2]);
  const totalQuarters = year * 4 + (q - 1) + offset;
  const newYear = Math.floor(totalQuarters / 4);
  const newQ = ((totalQuarters % 4) + 4) % 4; // handle negatives correctly
  return `${newYear}-Q${newQ + 1}`;
}

/** Array of N consecutive quarters starting at ``start`` (inclusive). */
export function nextNQuarters(start: string, n: number): string[] {
  return Array.from({ length: n }, (_, idx) => quarterFromOffset(start, idx));
}

/** ``< 0 / 0 / > 0`` ordering — string compare works because zero-padded year. */
export function quarterCompare(a: string, b: string): number {
  if (a === b) return 0;
  return a < b ? -1 : 1;
}

/**
 * Signed quarter delta: ``quartersBetween('2026-Q3', '2027-Q1')`` = ``2``.
 * Negative when ``end`` is before ``start``.
 */
export function quartersBetween(start: string, end: string): number {
  const ms = QUARTER_RE.exec(start);
  const me = QUARTER_RE.exec(end);
  if (!ms) throw new Error(`invalid quarter string: ${start}`);
  if (!me) throw new Error(`invalid quarter string: ${end}`);
  const startUnits = Number(ms[1]) * 4 + (Number(ms[2]) - 1);
  const endUnits = Number(me[1]) * 4 + (Number(me[2]) - 1);
  return endUnits - startUnits;
}

/** Inclusive range of quarters from ``from`` to ``to``. Empty if from > to. */
export function quartersInRange(from: string, to: string): string[] {
  const span = quartersBetween(from, to);
  if (span < 0) return [];
  return nextNQuarters(from, span + 1);
}

/** Display form: ``2026-Q3`` → ``Q3·26``. Matches the mockup column headers. */
export function formatQuarterCompact(q: string): string {
  const m = QUARTER_RE.exec(q);
  if (!m) return q;
  const yy = m[1].slice(2);
  return `Q${m[2]}·${yy}`;
}

/** Display form: ``2026-Q3`` → ``Q3 2026``. The longer form used in copy. */
export function formatQuarterLong(q: string): string {
  const m = QUARTER_RE.exec(q);
  if (!m) return q;
  return `Q${m[2]} ${m[1]}`;
}

/** True when ``q`` is at or before ``reference`` (default: today). */
export function isPastQuarter(q: string, reference: string = currentQuarter()): boolean {
  return quarterCompare(q, reference) < 0;
}

/** True when ``q`` equals ``reference`` (default: today). */
export function isCurrentQuarter(q: string, reference: string = currentQuarter()): boolean {
  return q === reference;
}
