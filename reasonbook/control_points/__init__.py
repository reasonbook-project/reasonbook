# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Control points — first-class decision gates.

Per ADR-11 (Spine/ADR-11-accountability-spine.md): a control point is one
clearance obligation that must be cleared — or recorded as a *named gap* —
before a downstream lifecycle event advances. Materialized per matter on
creation; cleared on Decision finalize; can be marked as a named gap (with
a required reason on the record) by an authorized user.

Surface API:

  * :func:`materialize_for_matter` — seed control points for a matter's
    nodes × archetypes × trigger events on matter creation.
  * :func:`clear` — mark cleared, with the Decision that cleared it.
  * :func:`mark_gap` — mark skipped with a required reason. The
    auditable named gap.

Every state change is also recorded as a hash-chained ``decision_events``
row (``control_point_cleared`` / ``control_point_skipped``) so the chain
covers control-point activity.
"""

from reasonbook.control_points.service import (
    ControlPointError,
    clear,
    find_pending_for_decision,
    mark_gap,
    materialize_for_matter,
    trigger_event_for_decision,
)

__all__ = [
    "ControlPointError",
    "clear",
    "find_pending_for_decision",
    "mark_gap",
    "materialize_for_matter",
    "trigger_event_for_decision",
]
