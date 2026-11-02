# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""CLI wrapper for SEC-1 chain verification.

Usage::

    uv run python -m scripts.verify_integrity

Walks the ``decision_events`` table from genesis, recomputes every
event's hash, and compares against the stored value. Prints a one-line
summary plus a JSON dump suitable for piping into evidence collection.

Exit codes:

  * ``0`` — chain verified end-to-end.
  * ``1`` — chain broken; ``broken_at_*`` fields identify the first row
    whose stored hash diverges from the recomputed value.
"""

from __future__ import annotations

import json
import sys

from reasonbook.db import session_scope
from reasonbook.integrity import verify_chain


def main() -> int:
    with session_scope() as s:
        result = verify_chain(s)
    payload = result.as_dict()
    if result.ok:
        print(
            f"OK — {result.total_events} events verified · head={result.head_hash[:16]}…"
        )
    else:
        print(
            f"FAIL — chain breaks at index {result.broken_at_index} "
            f"(id={result.broken_at_id})"
        )
    print(json.dumps(payload, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
