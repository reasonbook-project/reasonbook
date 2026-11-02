# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Alert triage — signal capture with recorded dispositions.

Public entry points:

  * ``record_disposition`` — write one disposition (promote / dismiss /
    hold / reopen) to the append-only alert ledger. For ``promote``,
    instantiates a governed Decision via the existing
    :mod:`reasonbook.promotion.service` (no changes to that module).

See ``docs/architecture/fedRAMP/ALERTS-SPEC.md`` for the design rationale.
"""

from reasonbook.alerts.service import DispositionError, record_disposition

__all__ = ["DispositionError", "record_disposition"]
