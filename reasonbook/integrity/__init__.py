# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Integrity layer — SEC-1 + SEC-4 (hash chain on the append-only ledger).

See ``ARCHITECTURE_MASTER §7.2`` for design intent and
``docs/architecture/fedRAMP/COMPLIANCE-REGISTER.md`` for the requirement
→ code map. Tracked in reconcile/v3_6.md as P09.

The SQLAlchemy hook lives in ``reasonbook.integrity.hooks`` and is imported
directly by ``reasonbook.models.__init__`` (not re-exported here) to avoid a
circular import between reasonbook.models and reasonbook.integrity.
"""

from reasonbook.integrity.hash_chain import (
    HASHED_FIELDS,
    VerifyResult,
    canonical_event,
    chain_head,
    compute_hash,
    verify_chain,
)

__all__ = [
    "HASHED_FIELDS",
    "VerifyResult",
    "canonical_event",
    "chain_head",
    "compute_hash",
    "verify_chain",
]
