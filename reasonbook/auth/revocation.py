# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""JWT revocation — no-op in v1.0.

v1.0 has **no server-side token revocation list** (see README, Known
limitations). Session JWTs are short-lived (30 min by default) and logout
clears the client cookie only. These functions keep the call sites in
``api/auth.py`` (logout) working without an external dependency;
reintroducing a real denylist is on the roadmap.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def revoke(token: str) -> None:  # noqa: ARG001 - kept for call-site compatibility
    """No-op. v1.0 does not maintain a revocation list."""
    return None


def is_revoked(jti: str) -> bool:  # noqa: ARG001 - kept for call-site compatibility
    """Always False. v1.0 does not maintain a revocation list."""
    return False
