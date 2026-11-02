# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Outbound email — verification, password reset, signup confirmation.

Single SMTP path mirroring the marketing site's Workspace SMTP integration.
Fail-silent: SMTP outages must never break a signup or password-reset request.
The caller decides whether to surface the failure to the user; the helper
itself always returns a boolean and logs.
"""
