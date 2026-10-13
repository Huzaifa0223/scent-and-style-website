"""Operational constants for the Noor integration (see ``core/config.py`` for
the project-wide convention — these live beside the app so it stays
self-contained and removable)."""

from __future__ import annotations

from typing import Final, cast

from core.models import RateLimitScope
from core.ratelimit import RateLimitPolicy

# Public feeds: how long a browser (or any shared cache) may reuse a response.
PUBLIC_FEED_MAX_AGE_SECONDS: Final[int] = 300

# Shortest shared secret accepted for the tablet sync API. A shorter (or
# missing) token makes every private endpoint answer 401 rather than letting
# a weak secret quietly protect a stock/backup API.
SYNC_TOKEN_MIN_LENGTH: Final[int] = 32

# "~30 requests/minute per IP" — a single short window, no lockout tier:
# tablets legitimately retry, so a lockout would punish the shop's own devices.
SYNC_RATE_LIMIT_POLICY: Final = RateLimitPolicy(max_attempts=30, window_seconds=60)

# core.ratelimit keys its budget on RateLimitScope. Adding a member to that
# TextChoices would generate a ``core`` migration (choices are part of the
# field's migration state) — exactly the kind of change to an existing app
# this integration must not make. The column is a plain CharField(max_length=20)
# with no DB-level choice check, so a value outside the enum is stored fine.
# Fold this into RateLimitScope the next time ``core`` is migrated anyway.
SYNC_RATE_LIMIT_SCOPE: Final = cast(RateLimitScope, "kiosk_sync")

# POST /api/kiosk/sync/backup/ — 5 MiB, and the number of backups retained.
BACKUP_MAX_BYTES: Final[int] = 5 * 1024 * 1024
BACKUP_KEEP_NEWEST: Final[int] = 10
BACKUP_FORMAT: Final[str] = "scent-style-backup"

# CORS preflight cache lifetime for the browser (seconds).
PREFLIGHT_MAX_AGE_SECONDS: Final[int] = 600
