# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Structured logging configuration."""

from __future__ import annotations

import hashlib
import hmac
import logging
import sys

import structlog

log = logging.getLogger(__name__)

# Flag so the "no secret configured" warning fires once per process rather
# than once per call. Set the first time hash_pii_for_log runs without a
# secret. Ops sees one log line at first use, not one per request.
_LOG_HASH_FALLBACK_WARNED = False


def hash_pii(value: str | None) -> str | None:
    """SHA-256 hex digest for PII used as a namespace / cache key.

    Unsalted on purpose: this function's outputs are used as a log-correlation key
    suffixes (per-account rate-limit counters, etc.) where stability
    across secret rotations matters more than secrecy of the input. The
    counter store is inside the trust boundary; an attacker who reads
    the logs already has worse problems than reversing email hashes.

    For PII flowing into structured logs (which may leave the trust
    boundary via log aggregation), use ``hash_pii_for_log`` instead.
    """
    if value is None:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_pii_for_log(value: str | None) -> str | None:
    """HMAC-SHA256 hex digest for PII in structured logs.

    Uses ``Settings.pii_hash_secret`` (env: ``PII_HASH_SECRET``) as the
    HMAC key. With the secret configured, log leaks can't be reversed by
    rainbow tables against common emails — an attacker would need the
    secret to mount a brute-force.

    Falls back to plain ``hash_pii`` when the secret isn't configured.
    Logs one warning per process at fallback time so ops sees the gap
    without spamming on every request. The fallback exists so dev/test
    can run without provisioning a secret; production should always set
    one (the security runbook lists this as a required SECRET env).
    """
    global _LOG_HASH_FALLBACK_WARNED
    if value is None:
        return None

    from reasonbook.config import get_settings

    secret = get_settings().pii_hash_secret
    if not secret:
        if not _LOG_HASH_FALLBACK_WARNED:
            log.warning(
                "PII_HASH_SECRET not set; log PII hashes fall back to unsalted SHA-256. "
                "Set the env var in production (DO console, type=SECRET) before launch."
            )
            _LOG_HASH_FALLBACK_WARNED = True
        return hash_pii(value)

    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def configure_logging(level: str = "INFO", format_: str = "json") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if format_ == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        stream=sys.stdout,
    )
