"""core/backup.py (§55, roadmap Stage 13). The R2-branch tests use
``MagicMock(spec=S3Boto3Storage)`` rather than a real storage instance —
``isinstance()`` against a spec'd Mock succeeds without ever opening a
real network connection, so ``_as_s3_storage``'s class check exercises
the real branch with no live R2 credentials involved.
"""

from __future__ import annotations

import os
import subprocess
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings as django_settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3boto3 import S3Boto3Storage

from core.backup import (
    BackupError,
    apply_local_dump_retention,
    apply_r2_dump_retention,
    dump_database,
    sync_media_backup_mirror,
    upload_dump_to_r2,
)


def _completed_process(returncode: int, stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="", stderr=stderr)


def test_dump_database_invokes_pg_dump_with_connection_settings_and_custom_format(
    tmp_path: Path,
) -> None:
    with patch("core.backup.subprocess.run", return_value=_completed_process(0)) as run:
        dump_path = dump_database(tmp_path)

    assert dump_path.parent == tmp_path
    assert dump_path.name.startswith("ecommerce_") and dump_path.name.endswith(".dump")

    command = run.call_args.args[0]
    assert command[0] == "pg_dump"
    # pytest-django swaps DATABASES["default"]["NAME"] for the "test_"-
    # prefixed database for the duration of the run — assert against the
    # live setting rather than a literal, so this test doesn't depend on
    # running in or out of that context.
    db_name = str(django_settings.DATABASES["default"]["NAME"])
    assert "-d" in command and db_name in command
    assert "-Fc" in command
    assert str(dump_path) in command


def test_dump_database_passes_the_db_password_only_via_env_not_argv(tmp_path: Path) -> None:
    with patch("core.backup.subprocess.run", return_value=_completed_process(0)) as run:
        dump_database(tmp_path)

    command = run.call_args.args[0]
    passed_env = run.call_args.kwargs["env"]
    assert "PGPASSWORD" in passed_env
    assert passed_env["PGPASSWORD"] not in command


def test_dump_database_raises_backup_error_when_pg_dump_exits_nonzero(tmp_path: Path) -> None:
    with patch(
        "core.backup.subprocess.run",
        return_value=_completed_process(1, stderr="connection refused"),
    ):
        with pytest.raises(BackupError):
            dump_database(tmp_path)


def test_apply_local_dump_retention_deletes_only_old_matching_files(tmp_path: Path) -> None:
    old_dump = tmp_path / "ecommerce_20200101_000000.dump"
    recent_dump = tmp_path / "ecommerce_20990101_000000.dump"
    unrelated_file = tmp_path / "notes.txt"
    old_dump.write_bytes(b"old")
    recent_dump.write_bytes(b"recent")
    unrelated_file.write_bytes(b"keep me regardless of age")

    old_time = 1_000_000  # 1970 — far past any retention window
    os.utime(old_dump, (old_time, old_time))
    os.utime(unrelated_file, (old_time, old_time))

    deleted = apply_local_dump_retention(tmp_path, retention_days=30)

    assert deleted == 1
    assert not old_dump.exists()
    assert recent_dump.exists()
    assert unrelated_file.exists()


def test_apply_local_dump_retention_on_a_missing_directory_deletes_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    assert apply_local_dump_retention(missing, retention_days=30) == 0


def test_upload_dump_to_r2_skips_and_returns_none_for_non_s3_storage(tmp_path: Path) -> None:
    dump_path = tmp_path / "ecommerce_20990101_000000.dump"
    dump_path.write_bytes(b"data")

    result = upload_dump_to_r2(dump_path, storage=FileSystemStorage())

    assert result is None


def test_upload_dump_to_r2_uploads_under_the_db_prefix(tmp_path: Path) -> None:
    dump_path = tmp_path / "ecommerce_20990101_000000.dump"
    dump_path.write_bytes(b"data")
    storage = MagicMock(spec=S3Boto3Storage)
    storage.bucket.name = "test-bucket"

    key = upload_dump_to_r2(dump_path, storage=storage)

    assert key == f"backups/db/{dump_path.name}"
    storage.bucket.upload_file.assert_called_once_with(str(dump_path), key)


def test_apply_r2_dump_retention_skips_non_s3_storage() -> None:
    assert apply_r2_dump_retention(retention_days=30, storage=FileSystemStorage()) == 0


def test_apply_r2_dump_retention_deletes_only_objects_past_the_window() -> None:
    from datetime import datetime, timedelta

    storage = MagicMock(spec=S3Boto3Storage)
    storage.bucket.name = "test-bucket"
    old_object = MagicMock(last_modified=datetime.now(tz=UTC) - timedelta(days=60))
    recent_object = MagicMock(last_modified=datetime.now(tz=UTC) - timedelta(days=1))
    storage.bucket.objects.filter.return_value = [old_object, recent_object]

    deleted = apply_r2_dump_retention(retention_days=30, storage=storage)

    assert deleted == 1
    old_object.delete.assert_called_once()
    recent_object.delete.assert_not_called()
    storage.bucket.objects.filter.assert_called_once_with(Prefix="backups/db/")


def test_sync_media_backup_mirror_skips_non_s3_storage() -> None:
    assert sync_media_backup_mirror(storage=FileSystemStorage()) == 0


def test_sync_media_backup_mirror_copies_every_object_under_the_mirror_prefix() -> None:
    storage = MagicMock(spec=S3Boto3Storage)
    storage.bucket.name = "test-bucket"
    obj_a = MagicMock(key="products/originals/a.jpg")
    obj_b = MagicMock(key="products/originals/b.jpg")
    storage.bucket.objects.all.return_value = [obj_a, obj_b]

    with patch("core.backup.settings") as settings_mock:
        settings_mock.AWS_BACKUP_BUCKET_NAME = ""
        copied = sync_media_backup_mirror(storage=storage)

    assert copied == 2
    storage.bucket.copy.assert_any_call(
        {"Bucket": "test-bucket", "Key": "products/originals/a.jpg"},
        "backups/media-mirror/products/originals/a.jpg",
    )
    storage.bucket.copy.assert_any_call(
        {"Bucket": "test-bucket", "Key": "products/originals/b.jpg"},
        "backups/media-mirror/products/originals/b.jpg",
    )


def test_sync_media_backup_mirror_never_mirrors_the_mirror_itself() -> None:
    storage = MagicMock(spec=S3Boto3Storage)
    storage.bucket.name = "test-bucket"
    already_mirrored = MagicMock(key="backups/media-mirror/products/originals/a.jpg")
    storage.bucket.objects.all.return_value = [already_mirrored]

    with patch("core.backup.settings") as settings_mock:
        settings_mock.AWS_BACKUP_BUCKET_NAME = ""
        copied = sync_media_backup_mirror(storage=storage)

    assert copied == 0
    storage.bucket.copy.assert_not_called()


def test_sync_media_backup_mirror_targets_a_dedicated_bucket_when_configured() -> None:
    storage = MagicMock(spec=S3Boto3Storage)
    storage.bucket.name = "live-bucket"
    obj = MagicMock(key="products/originals/a.jpg")
    storage.bucket.objects.all.return_value = [obj]
    backup_bucket = MagicMock()
    backup_bucket.name = "dedicated-backup-bucket"
    storage.connection.Bucket.return_value = backup_bucket

    with patch("core.backup.settings") as settings_mock:
        settings_mock.AWS_BACKUP_BUCKET_NAME = "dedicated-backup-bucket"
        copied = sync_media_backup_mirror(storage=storage)

    assert copied == 1
    storage.connection.Bucket.assert_called_once_with("dedicated-backup-bucket")
    backup_bucket.copy.assert_called_once_with(
        {"Bucket": "live-bucket", "Key": "products/originals/a.jpg"},
        "products/originals/a.jpg",
    )
