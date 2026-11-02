# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Attachment storage abstraction for Phase 7.5 authoring surfaces.

Per ``reasonbook-authoring-and-config-amendment-v1_2.md`` §3.3. The storage
backend for ``decision_attachments`` is deferred until the first paying
customer's compliance posture is known. The schema records
``storage_backend`` so a later migration can identify which backend was
used; this package keeps the implementation choice abstracted behind
the ``AttachmentStorage`` Protocol.

For Phase 7.5 only ``LocalFilesystemStorage`` is implemented.
``S3Storage`` and ``PostgresLargeObjectStorage`` are stubbed so
``get_storage`` can route to them once selected without a code-shape
change.
"""

from reasonbook.storage.attachments import (
    AttachmentStorage,
    LocalFilesystemStorage,
    PostgresLargeObjectStorage,
    S3Storage,
    StorageRef,
    get_storage,
)

__all__ = [
    "AttachmentStorage",
    "S3Storage",
    "LocalFilesystemStorage",
    "PostgresLargeObjectStorage",
    "StorageRef",
    "get_storage",
]
