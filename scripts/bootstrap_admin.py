# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""First-run admin bootstrap.

Creates a single local admin user from ``REASONBOOK_ADMIN_EMAIL`` if one does
not already exist, generates a random password, and prints it ONCE to stdout.
Idempotent: a second run is a no-op when the admin already exists (no new
password is printed).

Run automatically by the container entrypoint when ``REASONBOOK_ADMIN_EMAIL``
is set, or manually:

    python -m scripts.bootstrap_admin
"""

from __future__ import annotations

import logging
import os
import secrets
import uuid

import bcrypt

from reasonbook.db import session_scope
from reasonbook.models import Tenant, User

log = logging.getLogger(__name__)

# The single organization id (single-tenant deployment).
ORG_ID = "us-federal"
BCRYPT_COST = int(os.environ.get("BCRYPT_TEST_COST", "12"))


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_COST)).decode()


def bootstrap_admin() -> None:
    email = (os.environ.get("REASONBOOK_ADMIN_EMAIL") or "").strip().lower()
    if not email:
        print("REASONBOOK_ADMIN_EMAIL not set — skipping admin bootstrap.")
        return

    with session_scope() as session:
        # Ensure the single organization row exists.
        org = session.get(Tenant, ORG_ID)
        if org is None:
            org = Tenant(tenant_id=ORG_ID, name="Organization", org_type="FEDERAL_GOVERNMENT")
            session.add(org)
            session.flush()

        existing = session.query(User).filter(User.email.ilike(email)).one_or_none()
        if existing is not None:
            print(f"Admin {email} already exists — nothing to do.")
            return

        password = secrets.token_urlsafe(18)
        session.add(
            User(
                id=uuid.uuid4(),
                tenant_id=ORG_ID,
                username=email,
                email=email,
                password_hash=_hash(password),
                name="Administrator",
                title="Administrator",
                role="admin",
                status="active",
                email_verified=True,
                tier="federal",
            )
        )
        print("=" * 68)
        print("Reasonbook first-run admin created.")
        print(f"  email:    {email}")
        print(f"  password: {password}")
        print("  Save this password now — it is shown only once.")
        print("=" * 68)


if __name__ == "__main__":
    bootstrap_admin()
