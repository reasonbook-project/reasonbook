# Copyright 2026 Data Visuals LLC
# SPDX-License-Identifier: Apache-2.0
"""Phase 7.5 Gate 3 — attachment storage abstraction.

Covers ``reasonbook/storage/attachments.py``:

- ``LocalFilesystemStorage`` round-trip (put → get with byte-equal content,
  delete removes the file, ``signed_url`` returns ``None``).
- ``S3Storage`` boto3 wiring: put / get / delete / signed_url against
  a mocked S3 client; backend rejects refs from other backends.
- ``PostgresLargeObjectStorage`` raises ``NotImplementedError`` with a
  message that names the deferred-decision section of the amendment.
- ``get_storage`` factory routes by ``ATTACHMENT_BACKEND`` and
  rejects unknown values.
- Filename sanitization defeats path-traversal payloads.

No DB, no Postgres — pure filesystem and import-level checks. These run
without ``clean_db``.
"""

from __future__ import annotations

import dataclasses
import io
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from reasonbook.storage import (
    AttachmentStorage,
    S3Storage,
    LocalFilesystemStorage,
    PostgresLargeObjectStorage,
    StorageRef,
    get_storage,
)

# ---------------------------------------------------------------------------
# StorageRef
# ---------------------------------------------------------------------------


def test_storage_ref_is_frozen() -> None:
    ref = StorageRef(backend="local", path="/tmp/x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        ref.path = "/tmp/y"  # type: ignore[misc]


def test_storage_ref_str_format_per_backend() -> None:
    assert str(StorageRef(backend="local", path="/tmp/reasonbook/x")) == "local:///tmp/reasonbook/x"
    assert (
        str(StorageRef(backend="s3", path="dec/abc.pdf", bucket="reasonbook-prod"))
        == "s3://reasonbook-prod/dec/abc.pdf"
    )
    assert str(StorageRef(backend="pg_lo", path="", oid=12345)) == "pg_lo://12345"


# ---------------------------------------------------------------------------
# LocalFilesystemStorage — put / get / delete / signed_url
# ---------------------------------------------------------------------------


def test_local_storage_put_creates_file_under_decision_dir(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()
    payload = b"PDF-fake-bytes-for-test"

    ref = storage.put(decision_id, "referral.pdf", io.BytesIO(payload))

    assert ref.backend == "local"
    p = Path(ref.path)
    assert p.exists()
    assert p.parent == tmp_path / str(decision_id)
    # Filename is `{uuid}-{sanitized}` — preserves the original suffix.
    assert p.name.endswith("-referral.pdf")
    assert p.read_bytes() == payload


def test_local_storage_get_returns_byte_equal_content(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()
    payload = b"\x00\x01\x02arbitrary binary\xfe\xff"

    ref = storage.put(decision_id, "blob.bin", io.BytesIO(payload))

    with storage.get(ref) as fh:
        assert fh.read() == payload


def test_local_storage_get_missing_raises_file_not_found(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    bogus = StorageRef(backend="local", path=str(tmp_path / "no-such-file.bin"))
    with pytest.raises(FileNotFoundError):
        storage.get(bogus)


def test_local_storage_delete_removes_file_then_get_fails(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()
    ref = storage.put(decision_id, "x.txt", io.BytesIO(b"hello"))

    storage.delete(ref)

    assert not Path(ref.path).exists()
    with pytest.raises(FileNotFoundError):
        storage.get(ref)


def test_local_storage_delete_is_idempotent(tmp_path: Path) -> None:
    """Deleting an already-removed file should not raise — the DB row's
    ``superseded_at`` is the source of truth; filesystem cleanup is
    bookkeeping that should be safe to retry."""
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()
    ref = storage.put(decision_id, "y.txt", io.BytesIO(b"again"))

    storage.delete(ref)
    storage.delete(ref)  # second delete must not raise


def test_local_storage_signed_url_returns_none(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()
    ref = storage.put(decision_id, "z.txt", io.BytesIO(b"hi"))

    assert storage.signed_url(ref, expiry_seconds=60) is None


def test_local_storage_get_rejects_foreign_backend_ref(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    foreign = StorageRef(backend="s3", path="bucket/key", bucket="x")
    with pytest.raises(ValueError, match="LocalFilesystemStorage"):
        storage.get(foreign)


def test_local_storage_two_files_with_same_name_dont_collide(tmp_path: Path) -> None:
    """The ``uuid``-prefix in the path layout keeps two ``referral.pdf``
    uploads on the same decision from clobbering each other."""
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()

    ref_a = storage.put(decision_id, "referral.pdf", io.BytesIO(b"A"))
    ref_b = storage.put(decision_id, "referral.pdf", io.BytesIO(b"B"))

    assert ref_a.path != ref_b.path
    with storage.get(ref_a) as fh:
        assert fh.read() == b"A"
    with storage.get(ref_b) as fh:
        assert fh.read() == b"B"


# ---------------------------------------------------------------------------
# Filename sanitization — path traversal defense
# ---------------------------------------------------------------------------


def test_local_storage_strips_path_components(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()

    # `../../../etc/passwd` must not escape the decision directory.
    ref = storage.put(decision_id, "../../../etc/passwd", io.BytesIO(b"x"))

    p = Path(ref.path)
    assert p.parent == tmp_path / str(decision_id)
    # Sanitized basename — only the leaf, no `..` segments.
    assert ".." not in p.parts
    assert p.name.endswith("-passwd")


def test_local_storage_replaces_unsafe_chars(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()

    ref = storage.put(decision_id, "weird name; rm -rf /.txt", io.BytesIO(b"x"))

    p = Path(ref.path)
    # Sanitization replaces spaces, semicolons, slashes → underscores.
    assert ";" not in p.name
    assert " " not in p.name
    # The .txt suffix survives since `.` is allowed.
    assert p.name.endswith(".txt")


def test_local_storage_dot_only_filename_falls_back_to_file(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    decision_id = uuid.uuid4()

    ref = storage.put(decision_id, "..", io.BytesIO(b"x"))

    p = Path(ref.path)
    assert p.name.endswith("-file")  # purely-dot names collapse to "file"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_local_storage_satisfies_protocol(tmp_path: Path) -> None:
    storage = LocalFilesystemStorage(root=tmp_path)
    assert isinstance(storage, AttachmentStorage)


def test_stub_backends_satisfy_protocol() -> None:
    # PostgresLargeObjectStorage stub still raises in body but conforms to
    # the Protocol. S3Storage is now real and tested separately below.
    assert isinstance(S3Storage(bucket="x"), AttachmentStorage)
    assert isinstance(PostgresLargeObjectStorage(), AttachmentStorage)


# ---------------------------------------------------------------------------
# S3Storage — real implementation, mocked boto3 client
# ---------------------------------------------------------------------------


def _s3_with_mock(mock_client: MagicMock) -> S3Storage:
    """Construct a S3Storage with the cached boto3 client preset to a
    Mock so we don't actually talk to DO."""
    storage = S3Storage(bucket="reasonbook-test-bucket", region="nyc3")
    storage._cached_client = mock_client
    return storage


def test_s3_requires_bucket() -> None:
    with pytest.raises(ValueError, match="bucket"):
        S3Storage(bucket="")


def test_s3_endpoint_derived_from_region() -> None:
    storage = S3Storage(bucket="x", region="sfo3")
    assert storage.endpoint == "https://s3.sfo3.amazonaws.com"


def test_s3_endpoint_can_be_overridden() -> None:
    storage = S3Storage(bucket="x", region="nyc3", endpoint="https://custom.example.com")
    assert storage.endpoint == "https://custom.example.com"


def test_s3_put_uploads_with_private_acl_and_sse() -> None:
    client = MagicMock()
    storage = _s3_with_mock(client)
    decision_id = uuid.uuid4()

    ref = storage.put(decision_id, "deposit-history.pdf", io.BytesIO(b"%PDF-fake"))

    assert ref.backend == "s3"
    assert ref.bucket == "reasonbook-test-bucket"
    assert ref.path.startswith(f"{decision_id}/")
    assert ref.path.endswith("-deposit-history.pdf")
    # Verify the upload call included private ACL + server-side encryption
    client.upload_fileobj.assert_called_once()
    call = client.upload_fileobj.call_args
    extra = call.kwargs["ExtraArgs"] if "ExtraArgs" in call.kwargs else call.args[3]
    assert extra["ACL"] == "private"
    assert extra["ServerSideEncryption"] == "AES256"
    assert extra["ContentType"] == "application/pdf"


def test_s3_put_seeks_stream_to_zero_before_upload() -> None:
    """If the caller already read from the stream (e.g. for a size check),
    S3Storage must rewind so the bytes upload from byte 0."""
    client = MagicMock()
    storage = _s3_with_mock(client)

    stream = io.BytesIO(b"hello-world")
    stream.read()  # advance to EOF
    assert stream.tell() != 0

    storage.put(uuid.uuid4(), "x.txt", stream)

    # The wrapper should have rewound the stream before passing it to boto3
    assert stream.tell() == 0


def test_s3_str_round_trip_through_storage_uri() -> None:
    """``str(ref)`` produces the canonical URI the schema persists, and the
    ``_parse_storage_uri`` helper in decisions/manager reconstructs the
    same ref. Without this, downloads after a redeploy can't find the bytes."""
    from reasonbook.decisions.manager import _parse_storage_uri

    ref = StorageRef(
        backend="s3",
        bucket="reasonbook-test-bucket",
        path="abc-123/uuid-deposit.pdf",
    )
    uri = str(ref)
    assert uri == "s3://reasonbook-test-bucket/abc-123/uuid-deposit.pdf"

    parsed = _parse_storage_uri(uri, "s3")
    assert parsed.backend == "s3"
    assert parsed.bucket == "reasonbook-test-bucket"
    assert parsed.path == "abc-123/uuid-deposit.pdf"


def test_s3_get_returns_buffer_with_downloaded_bytes() -> None:
    client = MagicMock()

    # Simulate boto3.download_fileobj writing bytes into the buffer it's given
    def fake_download(bucket: str, key: str, buf: Any) -> None:
        buf.write(b"downloaded-bytes")

    client.download_fileobj.side_effect = fake_download
    storage = _s3_with_mock(client)

    ref = StorageRef(backend="s3", bucket="reasonbook-test-bucket", path="d1/uuid-x.pdf")
    fh = storage.get(ref)
    assert fh.read() == b"downloaded-bytes"
    client.download_fileobj.assert_called_once()


def test_s3_delete_calls_s3_delete_object() -> None:
    client = MagicMock()
    storage = _s3_with_mock(client)
    ref = StorageRef(backend="s3", bucket="reasonbook-test-bucket", path="d1/uuid-x.pdf")

    storage.delete(ref)

    client.delete_object.assert_called_once_with(Bucket="reasonbook-test-bucket", Key="d1/uuid-x.pdf")


def test_s3_signed_url_returns_presigned_get_url() -> None:
    client = MagicMock()
    client.generate_presigned_url.return_value = (
        "https://s3.nyc3.amazonaws.com/reasonbook-test-bucket/d1/x.pdf?X-Amz-Signature=abc"
    )
    storage = _s3_with_mock(client)
    ref = StorageRef(backend="s3", bucket="reasonbook-test-bucket", path="d1/uuid-x.pdf")

    url = storage.signed_url(ref, expiry_seconds=300)

    assert url is not None
    assert "X-Amz-Signature" in url
    client.generate_presigned_url.assert_called_once()
    call = client.generate_presigned_url.call_args
    assert call.args[0] == "get_object"
    assert call.kwargs["Params"]["Bucket"] == "reasonbook-test-bucket"
    assert call.kwargs["Params"]["Key"] == "d1/uuid-x.pdf"
    assert call.kwargs["ExpiresIn"] == 300


def test_s3_signed_url_returns_none_on_botocore_error() -> None:
    client = MagicMock()
    client.generate_presigned_url.side_effect = RuntimeError("boto3 down")
    storage = _s3_with_mock(client)
    ref = StorageRef(backend="s3", bucket="reasonbook-test-bucket", path="d1/uuid-x.pdf")

    assert storage.signed_url(ref, expiry_seconds=60) is None


def test_s3_rejects_foreign_backend_ref_on_get() -> None:
    storage = _s3_with_mock(MagicMock())
    foreign = StorageRef(backend="local", path="/tmp/x")
    with pytest.raises(ValueError, match="S3Storage"):
        storage.get(foreign)


def test_s3_rejects_foreign_backend_ref_on_delete() -> None:
    storage = _s3_with_mock(MagicMock())
    foreign = StorageRef(backend="local", path="/tmp/x")
    with pytest.raises(ValueError, match="S3Storage"):
        storage.delete(foreign)


# ---------------------------------------------------------------------------
# Postgres large-object stub still raises with the amendment reference
# ---------------------------------------------------------------------------


def test_pg_lo_stub_put_raises_not_implemented() -> None:
    storage = PostgresLargeObjectStorage()
    with pytest.raises(NotImplementedError) as exc:
        storage.put(uuid.uuid4(), "x.pdf", io.BytesIO(b"x"))
    msg = str(exc.value)
    assert "Postgres large object" in msg
    assert "amendment" in msg.lower()
    assert "§3.3" in msg


def test_pg_lo_stub_other_methods_raise_not_implemented() -> None:
    storage = PostgresLargeObjectStorage()
    bogus = StorageRef(backend="pg_lo", path="", oid=1)
    with pytest.raises(NotImplementedError):
        storage.get(bogus)
    with pytest.raises(NotImplementedError):
        storage.delete(bogus)
    with pytest.raises(NotImplementedError):
        storage.signed_url(bogus, expiry_seconds=60)


# ---------------------------------------------------------------------------
# get_storage factory
# ---------------------------------------------------------------------------


def _reset_settings_cache() -> None:
    from reasonbook.config import get_settings

    get_settings.cache_clear()


def test_get_storage_returns_local_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ATTACHMENT_BACKEND", raising=False)
    monkeypatch.setenv("ATTACHMENT_LOCAL_ROOT", str(tmp_path))
    _reset_settings_cache()
    try:
        storage = get_storage()
    finally:
        _reset_settings_cache()

    assert isinstance(storage, LocalFilesystemStorage)
    assert storage.root == tmp_path


def test_get_storage_routes_to_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTACHMENT_BACKEND", "s3")
    monkeypatch.setenv("REASONBOOK_S3_BUCKET", "reasonbook-test-bucket")
    monkeypatch.setenv("SPACES_REGION", "nyc3")
    _reset_settings_cache()
    try:
        storage = get_storage()
    finally:
        _reset_settings_cache()
    assert isinstance(storage, S3Storage)
    assert storage.bucket == "reasonbook-test-bucket"


def test_get_storage_s3_without_bucket_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATTACHMENT_BACKEND", "s3")
    monkeypatch.delenv("REASONBOOK_S3_BUCKET", raising=False)
    _reset_settings_cache()
    try:
        with pytest.raises(ValueError, match="bucket"):
            get_storage()
    finally:
        _reset_settings_cache()


def test_get_storage_routes_to_pg_lo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTACHMENT_BACKEND", "pg_lo")
    _reset_settings_cache()
    try:
        storage = get_storage()
    finally:
        _reset_settings_cache()
    assert isinstance(storage, PostgresLargeObjectStorage)


def test_get_storage_is_case_insensitive_on_backend_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ATTACHMENT_BACKEND", "LOCAL")
    monkeypatch.setenv("ATTACHMENT_LOCAL_ROOT", str(tmp_path))
    _reset_settings_cache()
    try:
        storage = get_storage()
    finally:
        _reset_settings_cache()
    assert isinstance(storage, LocalFilesystemStorage)


def test_get_storage_rejects_unknown_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATTACHMENT_BACKEND", "azure-blob")
    _reset_settings_cache()
    try:
        with pytest.raises(ValueError, match="azure-blob"):
            get_storage()
    finally:
        _reset_settings_cache()
