"""Nightly backup (§55, roadmap Stage 13): a Postgres dump plus an
off-box media mirror, both with a 30-day retention window.

Cron invokes this only through ``core.management.commands.backup`` (a
Django management command) — CLAUDE.md: "Background work is Django
management commands invoked by cron. Nothing else." This module is the
plain-function service layer the command wraps, kept separate so the
retention/upload logic is unit-testable without shelling out to
``manage.py``.

**Scope decision, recorded here rather than guessed silently:** by the
time this stage runs, product media already lives in Cloudflare R2
(``core.storage.R2MediaStorage``, Stage 12) — it is already off-box. A
second bucket dedicated to backups would give real protection against a
bug that corrupts the live bucket, but stands up infrastructure nobody
has asked for or funded yet. ``sync_media_backup_mirror`` supports one
via the optional ``AWS_BACKUP_BUCKET_NAME`` setting (same credentials,
different bucket) and falls back to a same-bucket ``backups/`` prefix
mirror when it is unset — real protection against accidental
overwrite/delete of a live object, not against total bucket loss. The
database dump is the artifact that actually needs day-by-day retention
(the roadmap's "30-day retention" language); the media mirror is a
single rolling copy refreshed nightly, so it carries no separate
retention logic of its own.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.core.files.storage import Storage, default_storage
from django.utils import timezone
from storages.backends.s3boto3 import S3Boto3Storage

from core.config import BACKUP_DB_DUMP_PREFIX, BACKUP_MEDIA_MIRROR_PREFIX

logger = logging.getLogger(__name__)

_DUMP_FILENAME_FORMAT = "ecommerce_%Y%m%d_%H%M%S.dump"
_DUMP_GLOB = "ecommerce_*.dump"


class _CopyableBucket(Protocol):
    """The slice of boto3's ``Bucket`` resource this module calls — typed
    by hand because django-storages/boto3 ship no stubs and
    ``mypy-boto3-s3`` is not in the approved dependency list."""

    name: str

    def copy(self, copy_source: dict[str, str], key: str) -> object: ...


class BackupError(Exception):
    """``pg_dump`` (or another backup step) exited non-zero."""


def _as_s3_storage(storage: Storage) -> S3Boto3Storage | None:
    """Returns ``storage`` narrowed to ``S3Boto3Storage``, or ``None``.

    Branching on the storage *class* (not ``settings.DEBUG``) matches
    this project's existing rule for picking behaviour by capability —
    the same reason ``R2MediaStorage`` itself is selected by settings
    module rather than an ``if DEBUG`` branch. In dev, ``default_storage``
    is ``FileSystemStorage`` and every function below becomes a documented
    no-op instead of failing.
    """
    return storage if isinstance(storage, S3Boto3Storage) else None


def dump_database(destination_dir: Path) -> Path:
    """Runs ``pg_dump -Fc`` against ``settings.DATABASES["default"]``.

    Custom format (``-Fc``), not plain SQL: it is what ``pg_restore``
    expects for the selective, ordered restore this project's schema
    needs (deferred constraint triggers, extensions) — the same format
    proven by the manual dump/restore/verify run recorded in the Stage 13
    log entry in specs/state.md.
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    dump_path = destination_dir / timezone.now().strftime(_DUMP_FILENAME_FORMAT)
    db = settings.DATABASES["default"]

    command = [
        settings.BACKUP_PG_DUMP_PATH,
        "-h", str(db["HOST"] or "localhost"),
        "-p", str(db["PORT"] or 5432),
        "-U", str(db["USER"]),
        "-d", str(db["NAME"]),
        "-Fc",
        "-f", str(dump_path),
    ]  # fmt: skip

    result = subprocess.run(
        command,
        env={"PGPASSWORD": str(db["PASSWORD"])},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        # stderr from pg_dump does not include PGPASSWORD (it is an env
        # var, never a CLI arg), so this is safe to log in full.
        logger.error("pg_dump failed (exit %d): %s", result.returncode, result.stderr)
        raise BackupError(f"pg_dump exited {result.returncode}")

    logger.info("pg_dump wrote %s", dump_path)
    return dump_path


def apply_local_dump_retention(directory: Path, *, retention_days: int) -> int:
    """Deletes ``ecommerce_*.dump`` files older than ``retention_days``.

    Matches only this command's own filename pattern — never a blanket
    sweep of ``directory``, in case a human ever points ``BACKUP_DIR`` at
    a directory that holds something else too.
    """
    if not directory.exists():
        return 0
    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted = 0
    for dump_file in directory.glob(_DUMP_GLOB):
        mtime = datetime.fromtimestamp(
            dump_file.stat().st_mtime, tz=timezone.get_default_timezone()
        )
        if mtime < cutoff:
            dump_file.unlink()
            deleted += 1
    return deleted


def upload_dump_to_r2(dump_path: Path, *, storage: Storage = default_storage) -> str | None:
    """Uploads a local dump file to ``backups/db/`` in the media bucket.

    Returns the object key, or ``None`` when ``storage`` isn't R2 (dev) —
    the dump still exists locally either way; this is the off-box copy.
    """
    s3_storage = _as_s3_storage(storage)
    if s3_storage is None:
        logger.info("upload_dump_to_r2: default storage is not S3-compatible, skipping")
        return None

    key = f"{BACKUP_DB_DUMP_PREFIX}{dump_path.name}"
    s3_storage.bucket.upload_file(str(dump_path), key)
    logger.info("uploaded %s to r2://%s/%s", dump_path, s3_storage.bucket.name, key)
    return key


def apply_r2_dump_retention(*, retention_days: int, storage: Storage = default_storage) -> int:
    """Deletes objects under ``backups/db/`` older than ``retention_days``."""
    s3_storage = _as_s3_storage(storage)
    if s3_storage is None:
        return 0

    cutoff = timezone.now() - timedelta(days=retention_days)
    deleted = 0
    for obj in s3_storage.bucket.objects.filter(Prefix=BACKUP_DB_DUMP_PREFIX):
        if obj.last_modified < cutoff:
            obj.delete()
            deleted += 1
    return deleted


def _backup_bucket(s3_storage: S3Boto3Storage) -> _CopyableBucket:
    """The destination bucket for the media mirror — a dedicated backup
    bucket if ``AWS_BACKUP_BUCKET_NAME`` is set, else the live bucket
    itself (mirrored under a distinct prefix). See this module's
    docstring for why a same-bucket mirror is the honest default.
    """
    backup_bucket_name = getattr(settings, "AWS_BACKUP_BUCKET_NAME", "") or s3_storage.bucket.name
    if backup_bucket_name == s3_storage.bucket.name:
        bucket: _CopyableBucket = s3_storage.bucket
        return bucket
    return s3_storage.connection.Bucket(backup_bucket_name)  # type: ignore[no-any-return]


def sync_media_backup_mirror(*, storage: Storage = default_storage) -> int:
    """Copies every live media object to the backup bucket/prefix.

    A rolling mirror, overwritten in place each night — not dated
    snapshots (see module docstring for why that's an intentionally
    simpler scope than the dump's day-by-day retention).
    """
    s3_storage = _as_s3_storage(storage)
    if s3_storage is None:
        logger.info("sync_media_backup_mirror: default storage is not S3-compatible, skipping")
        return 0

    destination_bucket = _backup_bucket(s3_storage)
    same_bucket = destination_bucket.name == s3_storage.bucket.name
    copied = 0
    for obj in s3_storage.bucket.objects.all():
        if same_bucket and obj.key.startswith(BACKUP_MEDIA_MIRROR_PREFIX):
            continue  # never mirror the mirror
        destination_key = f"{BACKUP_MEDIA_MIRROR_PREFIX}{obj.key}" if same_bucket else obj.key
        destination_bucket.copy(
            {"Bucket": s3_storage.bucket.name, "Key": obj.key},
            destination_key,
        )
        copied += 1
    logger.info(
        "sync_media_backup_mirror: mirrored %d object(s) to %s", copied, destination_bucket.name
    )
    return copied
