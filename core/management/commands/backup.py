"""Nightly cron entry point for core/backup.py (§55, roadmap Stage 13).

Cron target: ``manage.py backup``. See docs/deploy.md for the crontab
line. Thin by design — every real decision (retention window, mirror
target, what "off-box" means here) lives in core/backup.py, which is
tested directly; this command is just argument plumbing and a stdout
summary for cron's own mail-on-error behaviour.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.backup import (
    BackupError,
    apply_local_dump_retention,
    apply_r2_dump_retention,
    dump_database,
    sync_media_backup_mirror,
    upload_dump_to_r2,
)
from core.config import BACKUP_RETENTION_DAYS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Dump the database, mirror media, and apply the 30-day retention window."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--skip-media",
            action="store_true",
            help="Skip the media mirror step (dump/retention only).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            dump_path = dump_database(settings.BACKUP_DIR)
        except BackupError as exc:
            raise CommandError(str(exc)) from exc

        local_deleted = apply_local_dump_retention(
            settings.BACKUP_DIR, retention_days=BACKUP_RETENTION_DAYS
        )
        r2_key = upload_dump_to_r2(dump_path)
        r2_deleted = apply_r2_dump_retention(retention_days=BACKUP_RETENTION_DAYS)

        mirrored = 0
        if not options["skip_media"]:
            mirrored = sync_media_backup_mirror()

        summary = (
            f"dump={dump_path.name} r2_upload={'yes' if r2_key else 'skipped (not R2)'} "
            f"local_retention_deleted={local_deleted} r2_retention_deleted={r2_deleted} "
            f"media_mirrored={mirrored}"
        )
        logger.info("backup: %s", summary)
        self.stdout.write(summary)
