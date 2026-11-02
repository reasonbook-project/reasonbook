# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Signup helpers — tenant_id slug generation + reserved blocklist.

The ``POST /api/auth/signup`` endpoint generates a fresh ``tenant_id`` from
the supplied ``institution_name`` per spec-2 v2 Component 1 § "tenant_id slug
generation": ``slugify(institution_name)[:43] + '-' + uuid4_hex[-6:]``,
lowercased ASCII with non-alphanum collapsed to single hyphens. Reserved
slugs are blocklisted to prevent collisions with platform-internal names.
"""

from __future__ import annotations

import re
import unicodedata
import uuid

# Reserved slugs — institution_names that resolve to one of these get rejected
# at signup time. Initial list from `docs/architecture/design-notes/pricing-
# architecture-reconciliation.md` v1.1 §"Open items" item 2.
RESERVED_TENANT_IDS: frozenset[str] = frozenset(
    {
        "us-federal",  # demo seed organization
        "admin",
        "administrator",
        "support",
        "api",
        "app",
        "www",
        "staging",
        "test",
        "demo",
    }
)

# Lengths sized so the final tenant_id (slug + '-' + 6-char suffix) fits in
# the existing platform.tenants.tenant_id VARCHAR(50) column.
SLUG_MAX_LENGTH = 43
SUFFIX_LENGTH = 6


class ReservedSlugError(ValueError):
    """Raised when an institution_name resolves to a reserved tenant_id slug."""


def slugify(value: str) -> str:
    """Normalize a string into a URL-safe ASCII slug.

    Lowercases, drops accents and non-ASCII characters, collapses runs of
    non-alphanumeric characters to single hyphens, trims leading/trailing
    hyphens. Returns empty string if the input contains no usable chars.
    """
    normalized = unicodedata.normalize("NFKD", value)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered)
    return slug.strip("-")


def generate_tenant_id(institution_name: str) -> str:
    """Generate a fresh tenant_id slug from an institution name.

    Format: ``{slug}-{6-char-uuid-suffix}``. The slug is at most 43 chars
    (so the total fits in VARCHAR(50)). Suffix is the last 6 hex chars of
    a UUID4.

    Raises ``ReservedSlugError`` if the slug normalizes to a reserved value
    (e.g. ``"admin"``); the caller surfaces this as a 400 error and the user
    picks a different institution name.
    """
    base = slugify(institution_name)[:SLUG_MAX_LENGTH]
    if not base:
        # Empty after normalization — institution_name was entirely non-ASCII
        # or whitespace. Caller should validate min length pre-call, but be
        # defensive here too.
        base = "tenant"
    if base in RESERVED_TENANT_IDS:
        raise ReservedSlugError(
            f"institution_name {institution_name!r} resolves to reserved slug {base!r}"
        )

    suffix = uuid.uuid4().hex[-SUFFIX_LENGTH:]
    return f"{base}-{suffix}"


__all__ = [
    "RESERVED_TENANT_IDS",
    "ReservedSlugError",
    "SLUG_MAX_LENGTH",
    "SUFFIX_LENGTH",
    "generate_tenant_id",
    "slugify",
]
