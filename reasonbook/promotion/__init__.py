# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Promotion module — sits between archetype determinations and Decisions.

Per docs/architecture/MODEL-DESIGN-SPEC.md and the WORKFLOW-MIGRATION
contract, this module owns the volume switch:

  * Every atomic determination writes a ledger row (always).
  * For ``promotes: every_case`` archetypes, every determination is
    immediately materialised as a governed Decision in reasonbook.decisions.
  * For ``promotes: on_trigger`` archetypes, the Decision is created
    only when a ``promotion_triggers`` event arrives (override,
    adverse_action, appeal, sample, fraud_flag).

The promotion service is the ONLY place that knows about
``gate: conditional`` — it resolves it to ``authority`` (when promoted)
or ``none`` (when not) before the Decision reaches reasonbook.decisions, so
the lifecycle code stays unaware of the new enum value.

This module:

  * Reads archetype + program from the semantic engine.
  * Writes ledger rows via :mod:`reasonbook.promotion.ledger`.
  * Materialises Decisions via the existing reasonbook.decisions.manager
    APIs — no changes to dp/decisions/ are needed.

What this module does NOT do:

  * Run the determination basis (formula / ruleset / review scoring).
    Callers supply the basis result; the promotion service decides
    what to do with it.
  * Change the lifecycle. Once a Decision is created, it flows through
    the unchanged Signal -> Owner -> Decision -> Action -> Outcome
    pipeline.
"""

from reasonbook.promotion.service import (
    PromotionOutcome,
    PromotionResult,
    PromotionService,
    record_determination,
)

__all__ = [
    "PromotionOutcome",
    "PromotionResult",
    "PromotionService",
    "record_determination",
]
