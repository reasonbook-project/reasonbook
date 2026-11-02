# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Workspace SMTP helper — plain-text outbound email.

Sends plain-text email via stdlib smtplib. Configured via SMTP_* settings;
SMTP credentials. Fail-silent: returns False on any failure (logged); never
raises. Callers must treat email-send as best-effort and never block on it.

Configured via env (see ``reasonbook.config.Settings``):

- ``SMTP_HOST`` (default: ``smtp.gmail.com``)
- ``SMTP_PORT`` (default: 587)
- ``SMTP_USER`` (required for sends; empty means "skip")
- ``SMTP_PASSWORD`` (required for sends; mark encrypted in DO env)
- ``SMTP_FROM`` (optional; falls back to ``SMTP_USER``)
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from reasonbook.config import get_settings

log = logging.getLogger(__name__)


def send_email(
    *,
    to_addr: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
) -> bool:
    """Send a plain-text email. Returns True on success, False on any failure.

    Failures are logged at ERROR (delivery problems) or WARNING (no credentials).
    Never raises — callers can treat the boolean result as advisory.
    """
    settings = get_settings()
    smtp_user = settings.smtp_user
    smtp_password = settings.smtp_password
    smtp_from = settings.smtp_from or smtp_user

    if not smtp_user or not smtp_password:
        log.warning("SMTP credentials not configured; skipping send to %s", to_addr)
        return False

    msg = EmailMessage()
    msg["From"] = smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
        return True
    except Exception as exc:  # noqa: BLE001
        log.error("SMTP send failed (to=%s): %s", to_addr, exc)
        return False


__all__ = ["send_email"]
