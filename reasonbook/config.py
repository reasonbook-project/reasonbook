# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Configuration loading for Reasonbook.

All settings come from environment variables, prefixed ``REASONBOOK_``
(e.g. ``REASONBOOK_SECRET_KEY``). The legacy unprefixed ``DATABASE_URL``
is accepted as an alias for ``REASONBOOK_DATABASE_URL`` so managed-DB
providers that inject ``DATABASE_URL`` keep working.

No secret has a usable default. ``secret_key`` is empty by default; the
application factory fails fast in production when it is unset (see
``reasonbook.app.create_app``).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from the environment."""

    model_config = SettingsConfigDict(
        env_prefix="REASONBOOK_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # "production" | "development" | "testing". Controls fail-fast behaviour
    # for missing secrets and whether dev-only conveniences are allowed.
    flask_env: str = "production"

    # HMAC signing key for session JWTs and the PII-hash fallback. No default:
    # create_app() refuses to boot in production when this is empty.
    secret_key: str = ""

    # SQLite by default (single-file, zero-config). Point at PostgreSQL with
    # REASONBOOK_DATABASE_URL=postgresql+psycopg://user:pass@host/db — the
    # unprefixed DATABASE_URL is accepted as an alias.
    database_url: str = Field(
        default="sqlite:///reasonbook.db",
        validation_alias=AliasChoices("REASONBOOK_DATABASE_URL", "DATABASE_URL"),
    )

    # JWT — HS256 signed with secret_key. 30-minute lifetime by default.
    jwt_issuer: str = "reasonbook"
    jwt_ttl_minutes: int = 30

    cors_origins: str = "http://localhost:5173"

    # SMTP — optional. When smtp_host is empty, verification/reset links are
    # logged to stdout in development and the flows are disabled in production.
    # No host default: Reasonbook makes no outbound calls unless configured.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # falls back to smtp_user when empty

    # Public-facing base URL used to build verification/reset links.
    app_url: str = "http://localhost:8000"

    # HMAC key for hashing IPs / emails in structured logs. Falls back to
    # secret_key when empty.
    pii_hash_secret: str = ""

    log_level: str = "INFO"
    log_format: str = "json"

    # Attachment storage. "local" (default) writes under attachment_local_root;
    # "s3" uses the S3-compatible settings below (requires the [s3] extra).
    attachment_backend: str = Field(default="local")
    attachment_local_root: str = Field(default="/data/attachments")

    # S3-compatible object storage — only consulted when attachment_backend=s3.
    # Works with AWS S3, MinIO, or any S3-compatible endpoint. No defaults tied
    # to any hosting provider.
    s3_region: str = ""
    s3_bucket: str = ""
    s3_endpoint: str = ""  # e.g. https://s3.us-east-1.amazonaws.com or a MinIO URL
    s3_key: str = ""
    s3_secret: str = ""
    s3_presigned_url_expiry: int = 300

    # Demo seed accounts (scripts/seed_dev.py) are created only when
    # seed_demo=true; they are clearly labelled non-production. seed_password
    # has no default — seeding fails loudly when it is required but unset.
    seed_demo: bool = False
    seed_password: str = ""

    # First-run bootstrap admin. When set, an admin user is created on startup
    # with a generated password printed once to stdout.
    admin_email: str = ""

    # The in-process ingestion scheduler (APScheduler) starts with the app.
    # Must run in exactly one process — keep gunicorn at --workers 1, or set
    # this false on extra workers. See DEPLOY.md.
    run_scheduler: bool = True
    ingestion_interval_minutes: int = 5

    # Keep hash-chain / integrity canonicalization stable. Skip the semantic
    # boot in tests that don't need workflows loaded.
    skip_semantic_boot: bool = False

    version: str = Field(default="1.0.0")

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: object) -> object:
        """Rewrite bare ``postgresql://`` to the psycopg 3 driver form."""
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://") :]
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://") :]
        return v

    @field_validator("app_url", mode="before")
    @classmethod
    def _normalize_app_url(cls, v: object) -> object:
        """Strip a trailing slash and prepend a scheme when missing."""
        if not isinstance(v, str) or not v.strip():
            return v
        s = v.strip().rstrip("/")
        if "://" in s:
            return s
        if s.startswith("localhost") or s.startswith("127.0.0.1"):
            return f"http://{s}"
        return f"https://{s}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def db_schema(self) -> str | None:
        """Named schema on PostgreSQL ("platform"); flat (None) on SQLite.

        Drives the MetaData schema (reasonbook.db) and the raw-SQL
        ``schema_prefix`` so the same models run on both dialects.
        """
        return "platform" if self.is_postgres else None

    @property
    def testing(self) -> bool:
        return self.flask_env == "testing"


@lru_cache
def get_settings() -> Settings:
    return Settings()
