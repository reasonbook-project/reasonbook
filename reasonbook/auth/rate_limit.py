# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Login/signup rate limiting — disabled in v1.0.

v1.0 ships **no login rate limiting** (see README, Known limitations).
Reintroducing it (DB-backed, or via the roadmap scale profile) is tracked
for a future release.

``check_rate_limit`` always allows, keeping the call sites in
``api/auth.py`` working. Account **lockout** (consecutive-failure based)
is a separate, still-active control — see ``reasonbook.auth.lockout``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)


class RateLimitStoreUnavailableError(Exception):
    """Retained for call-site compatibility. Not raised in v1.0."""


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate-limit check. In v1.0 ``allowed`` is always True."""

    allowed: bool
    count: int
    retry_after_s: int


def check_rate_limit(key: str, *, limit: int, window_s: int) -> RateLimitResult:  # noqa: ARG001
    """No-op limiter: always allows. See module docstring."""
    return RateLimitResult(allowed=True, count=0, retry_after_s=0)
