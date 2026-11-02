# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Attachment storage Protocol + Local filesystem implementation.

Per ``reasonbook-authoring-and-config-amendment-v1_2.md`` §3.3. The Protocol
ships with one production-shaped backend (``LocalFilesystemStorage``)
and two stubs (``S3Storage``, ``PostgresLargeObjectStorage``)
that raise ``NotImplementedError`` so ``get_storage`` can route to them
once a backend is chosen — without changing the call sites that consume
the abstraction.

Path layout for ``LocalFilesystemStorage``:

    {root}/{decision_id}/{uuid4}-{sanitized_filename}

The ``uuid4`` segment guarantees uniqueness within a decision (two
files named ``referral.pdf`` don't collide); the trailing
``sanitized_filename`` preserves human-readable filenames in directory
listings during dev / debugging. Filenames are sanitized to defeat
path traversal — only ``[A-Za-z0-9._-]`` characters survive; everything
else is replaced with ``_``.
"""

from __future__ import annotations

import contextlib
import io
import mimetypes
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Protocol, runtime_checkable

if TYPE_CHECKING:  # boto3 is only imported when S3Storage is constructed
    pass

# ---------------------------------------------------------------------------
# StorageRef
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StorageRef:
    """Opaque reference to a stored attachment.

    ``backend`` and ``path`` are always set. Backend-specific fields
    (``bucket`` for S3-compatible backends, ``oid`` for Postgres large
    objects) are ``None`` for backends that don't use them. The
    ``decision_attachments.storage_uri`` column persists the canonical
    ``str(ref)`` form so future readers can reconstruct the ``StorageRef``
    by parsing it back.
    """

    backend: str
    path: str
    bucket: str | None = None
    oid: int | None = None

    def __str__(self) -> str:
        # Stable serialisation — the storage_uri column holds this.
        # Local: "local:///tmp/dp-attachments-dev/{decision_id}/{uuid}-name"
        # S3-compatible object storage: "s3://{bucket}/{path}"
        # Postgres LO: "pg_lo://{oid}"
        if self.backend == "local":
            return f"local://{self.path}"
        if self.backend == "s3":
            return f"s3://{self.bucket}/{self.path}"
        if self.backend == "pg_lo":
            return f"pg_lo://{self.oid}"
        return f"{self.backend}://{self.path}"


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class AttachmentStorage(Protocol):
    """Storage backend contract for decision attachments.

    Implementations are expected to be safe for concurrent calls from
    distinct request handlers but are not required to be thread-safe
    within a single handler. ``put`` is the only call that produces a
    new ``StorageRef``; subsequent ``get``/``delete``/``signed_url``
    calls work against the existing reference.
    """

    def put(self, decision_id: uuid.UUID, filename: str, content: BinaryIO) -> StorageRef: ...

    def get(self, ref: StorageRef) -> BinaryIO: ...

    def delete(self, ref: StorageRef) -> None: ...

    def signed_url(self, ref: StorageRef, expiry_seconds: int) -> str | None:
        """Return a time-bounded download URL, or ``None`` if the backend
        cannot mint one (e.g. local filesystem). Callers fall back to
        streaming the bytes through the API in that case.
        """
        ...


# ---------------------------------------------------------------------------
# LocalFilesystemStorage — the only concrete backend in Phase 7.5
# ---------------------------------------------------------------------------


_FILENAME_SANITIZE_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitize_filename(filename: str) -> str:
    """Strip the path component and replace unsafe characters.

    Defends against path-traversal payloads (``../etc/passwd``) and
    filenames containing shell metacharacters. The leading ``uuid4-``
    prefix ensures the result is still unique even if sanitization
    collapses two distinct names into the same string.
    """
    base = os.path.basename(filename) or "file"
    cleaned = _FILENAME_SANITIZE_RE.sub("_", base)
    # Defeat purely-dot names like "." or ".." after sanitization.
    if cleaned.strip(".") == "":
        cleaned = "file"
    # Cap length so directory listings stay sane.
    return cleaned[:120]


class LocalFilesystemStorage:
    """Stores attachment bytes under a configurable root directory.

    The root is created on first ``put`` if it does not exist. Per-
    decision subdirectories are created lazily. Deleting the last file
    in a decision directory leaves the empty directory in place — that's
    cheaper and safer than racing a concurrent ``put`` to clean it up.
    """

    backend_name = "local"

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self._root = Path(root)

    @property
    def root(self) -> Path:
        return self._root

    def _decision_dir(self, decision_id: uuid.UUID) -> Path:
        return self._root / str(decision_id)

    def _ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, decision_id: uuid.UUID, filename: str, content: BinaryIO) -> StorageRef:
        self._ensure_root()
        decision_dir = self._decision_dir(decision_id)
        decision_dir.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_filename(filename)
        # Per amendment §3.3 the spec calls for uuid7; codebase convention
        # is uuid4 (no uuid7 in stdlib at Python 3.13). uuid4 is used to
        # match every other id default in the project.
        unique = uuid.uuid4().hex
        target = decision_dir / f"{unique}-{safe_name}"

        with target.open("wb") as fh:
            shutil.copyfileobj(content, fh)

        return StorageRef(backend=self.backend_name, path=str(target))

    def get(self, ref: StorageRef) -> BinaryIO:
        if ref.backend != self.backend_name:
            raise ValueError(f"LocalFilesystemStorage cannot read ref with backend {ref.backend!r}")
        path = Path(ref.path)
        if not path.exists():
            raise FileNotFoundError(ref.path)
        return path.open("rb")

    def delete(self, ref: StorageRef) -> None:
        if ref.backend != self.backend_name:
            raise ValueError(
                f"LocalFilesystemStorage cannot delete ref with backend {ref.backend!r}"
            )
        path = Path(ref.path)
        # Idempotent — deleting an already-missing file is not an error.
        # Soft-delete on the DB side (`superseded_at`) is the source of
        # truth; the filesystem removal is bookkeeping.
        if path.exists():
            path.unlink()

    def signed_url(self, ref: StorageRef, expiry_seconds: int) -> str | None:
        # Local filesystem can't mint pre-signed URLs. Callers fall
        # back to streaming via the API endpoint.
        return None


# ---------------------------------------------------------------------------
# S3Storage — optional backend for container deploys
# ---------------------------------------------------------------------------
#
# Containers typically have ephemeral filesystems — anything written locally
# is lost on redeploy. LocalFilesystemStorage is fine for a single host with a
# persistent volume; for object storage, S3Storage talks to any S3-compatible
# endpoint (AWS S3, MinIO, Ceph, ...) with presigned-URL support. No hosting
# provider is assumed — the endpoint is configured explicitly.


class S3Storage:
    """S3-compatible object-storage backend for decision attachments.

    Works with AWS S3, MinIO, or any S3-compatible endpoint. Path layout in
    the bucket: ``{decision_id}/{uuid4}-{sanitized_filename}``. Mirrors the
    Local backend's per-decision-directory shape so audit reconstructions and
    bucket listings stay legible.

    Downloads use ``signed_url`` (presigned GET) so bytes flow storage→browser
    directly, not storage→Flask→browser.
    """

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "",
        endpoint: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        if not bucket:
            raise ValueError(
                "S3Storage requires a bucket name. Set REASONBOOK_S3_BUCKET in "
                "the environment when ATTACHMENT_BACKEND=s3."
            )
        self._bucket = bucket
        self._region = region
        # Explicit endpoint, or the AWS S3 regional endpoint when a region is
        # given. No provider-specific default.
        self._endpoint = endpoint or (f"https://s3.{region}.amazonaws.com" if region else None)
        self._access_key = access_key
        self._secret_key = secret_key
        self._cached_client: Any = None

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def _client(self) -> Any:
        if self._cached_client is not None:
            return self._cached_client
        # Lazy import keeps boto3 out of the import path for dev/test runs
        # that never construct a Spaces backend.
        import boto3
        from botocore.config import Config as BotoConfig

        self._cached_client = boto3.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key or "",
            aws_secret_access_key=self._secret_key or "",
            config=BotoConfig(signature_version="s3v4"),
        )
        return self._cached_client

    def _key(self, decision_id: uuid.UUID, filename: str) -> str:
        safe = _sanitize_filename(filename)
        unique = uuid.uuid4().hex
        return f"{decision_id}/{unique}-{safe}"

    def _check_backend(self, ref: StorageRef) -> None:
        if ref.backend != self.backend_name:
            raise ValueError(f"S3Storage cannot operate on ref with backend {ref.backend!r}")

    def put(self, decision_id: uuid.UUID, filename: str, content: BinaryIO) -> StorageRef:
        key = self._key(decision_id, filename)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        # Reset to start of stream so we don't upload zero bytes when the
        # caller previously read for a size check.
        if hasattr(content, "seek"):
            with contextlib.suppress(OSError, ValueError):
                content.seek(0)
        self._client().upload_fileobj(
            content,
            self._bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "ACL": "private",
                "ServerSideEncryption": "AES256",
            },
        )
        return StorageRef(backend=self.backend_name, bucket=self._bucket, path=key)

    def get(self, ref: StorageRef) -> BinaryIO:
        self._check_backend(ref)
        bucket = ref.bucket or self._bucket
        buf = io.BytesIO()
        self._client().download_fileobj(bucket, ref.path, buf)
        buf.seek(0)
        return buf

    def delete(self, ref: StorageRef) -> None:
        self._check_backend(ref)
        bucket = ref.bucket or self._bucket
        # S3 delete_object is idempotent — succeeds even if the key is gone.
        self._client().delete_object(Bucket=bucket, Key=ref.path)

    def signed_url(self, ref: StorageRef, expiry_seconds: int) -> str | None:
        self._check_backend(ref)
        bucket = ref.bucket or self._bucket
        try:
            url: str = self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": ref.path},
                ExpiresIn=expiry_seconds,
            )
        except Exception:
            return None
        return url


# ---------------------------------------------------------------------------
# Stubs — PostgresLargeObjectStorage
# ---------------------------------------------------------------------------


_STUB_MESSAGE = (
    "{backend} storage backend is stubbed. The choice of production "
    "backend is deferred per reasonbook-authoring-and-config-amendment-v1_2.md "
    "§3.3 — implement before selecting it via REASONBOOK_ATTACHMENT_BACKEND."
)


class PostgresLargeObjectStorage:
    """Postgres large-object (lo_*) backend. Stub only.

    The deferred-decision note in amendment §3.3 is the canonical
    reasoning for why this isn't implemented yet.
    """

    backend_name = "pg_lo"

    def put(self, decision_id: uuid.UUID, filename: str, content: BinaryIO) -> StorageRef:
        raise NotImplementedError(_STUB_MESSAGE.format(backend="Postgres large object"))

    def get(self, ref: StorageRef) -> BinaryIO:
        raise NotImplementedError(_STUB_MESSAGE.format(backend="Postgres large object"))

    def delete(self, ref: StorageRef) -> None:
        raise NotImplementedError(_STUB_MESSAGE.format(backend="Postgres large object"))

    def signed_url(self, ref: StorageRef, expiry_seconds: int) -> str | None:
        raise NotImplementedError(_STUB_MESSAGE.format(backend="Postgres large object"))


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_storage() -> AttachmentStorage:
    """Return the storage backend named by ``ATTACHMENT_BACKEND``.

    Reads ``Settings.attachment_backend`` (env var ``ATTACHMENT_BACKEND``,
    default ``local``). For ``local`` the root is ``ATTACHMENT_LOCAL_ROOT``;
    for ``s3`` the bucket / region / endpoint / credentials come from
    ``REASONBOOK_S3_*`` env vars
    DO credentials works across both apps). Raises ``ValueError`` for an
    unknown backend name or a misconfigured ``s3`` selection.
    """
    from reasonbook.config import get_settings

    settings = get_settings()
    backend = settings.attachment_backend.lower()

    if backend == "local":
        return LocalFilesystemStorage(root=settings.attachment_local_root)
    if backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint=settings.s3_endpoint or None,
            access_key=settings.s3_key or None,
            secret_key=settings.s3_secret or None,
        )
    if backend == "pg_lo":
        return PostgresLargeObjectStorage()
    raise ValueError(
        f"unknown REASONBOOK_ATTACHMENT_BACKEND={backend!r}; expected one of: local, s3"
    )
