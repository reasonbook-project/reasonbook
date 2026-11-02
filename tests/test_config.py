# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Tests for ``reasonbook.config.Settings`` validators."""

from __future__ import annotations

import pytest

from reasonbook.config import Settings


@pytest.mark.parametrize(
    ("input_value", "expected"),
    [
        # No scheme + production domain → auto-prepend https://
        ("example.com", "https://example.com"),
        # Trailing slash stripped before scheme prepend
        ("example.com/", "https://example.com"),
        # Already has scheme — left alone
        ("https://example.com", "https://example.com"),
        ("http://localhost:5173", "http://localhost:5173"),
        # Trailing slash stripped on already-schemed URL
        ("https://example.com/", "https://example.com"),
        # Localhost without scheme → http:// for dev convenience
        ("localhost:5173", "http://localhost:5173"),
        ("127.0.0.1:8080", "http://127.0.0.1:8080"),
        # Whitespace stripped
        ("  https://example.com  ", "https://example.com"),
    ],
)
def test_app_url_normalization(input_value: str, expected: str) -> None:
    """APP_URL is normalized to always have a scheme.

    Strict URL parsers reject schemeless URLs; email clients linkify
    them silently. The Settings validator normalizes at load time so a
    misconfig like ``APP_URL=app.fraudsterfree.com`` becomes
    ``https://app.fraudsterfree.com`` rather than getting passed
    verbatim downstream.
    """
    s = Settings(app_url=input_value)
    assert s.app_url == expected


def test_app_url_default_is_dev_localhost() -> None:
    """Default APP_URL keeps the dev localhost value with scheme intact."""
    s = Settings()
    assert s.app_url == "http://localhost:8000"
