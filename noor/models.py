from __future__ import annotations

from django.db import models


class KioskBackup(models.Model):
    """One backup uploaded by an in-store tablet (``POST backup/``).

    ``body`` is a ``TextField`` holding the exact JSON text received, not a
    ``JSONField``: ``jsonb`` rejects the ``\\u0000`` escape (which is valid
    JSON, so a tablet could legitimately send it and get a 500), reorders
    keys, and normalises numbers — a backup must come back byte-for-byte as
    it was sent. The text is validated as JSON before it is stored.

    Deliberately not registered in the Django admin and carries no file
    field: backups can hold customer data, so they are reachable only
    through the bearer-token API, never under ``MEDIA_URL`` or an admin page.
    Only the newest ``config.BACKUP_KEEP_NEWEST`` rows are kept.
    """

    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    size = models.PositiveIntegerField(help_text="Size of the received body in bytes.")
    body = models.TextField()

    class Meta:
        ordering = ["-received_at", "-id"]

    def __str__(self) -> str:
        return f"KioskBackup {self.pk} ({self.size} bytes, {self.received_at:%Y-%m-%d %H:%M})"
