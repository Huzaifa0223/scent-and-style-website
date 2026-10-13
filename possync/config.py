"""Operational constants for the POS sync (see ``noor/config.py`` for the
convention — kept beside the app so it stays self-contained)."""

from __future__ import annotations

from datetime import timedelta
from typing import Final, cast

from core.models import RateLimitScope

# Separate secret from SCENT_SYNC_TOKEN (the tablets'), so one leaking never
# opens the other API. Same minimum length as noor's.
POS_TOKEN_SETTING: Final[str] = "SCENT_POS_TOKEN"

# Own rate-limit bucket (same policy as noor's: ~30/min/IP). core's enum is
# not extended — that would generate a ``core`` migration; see noor/config.py
# for the full reasoning, which applies unchanged here.
POS_RATE_LIMIT_SCOPE: Final = cast(RateLimitScope, "pos_sync")

# Stock snapshot request body cap.
SNAPSHOT_MAX_BYTES: Final[int] = 5 * 1024 * 1024

# A snapshot stamped further in the future than this is refused: because
# older snapshots are ignored, one wrong-clock "future" snapshot would
# otherwise silently block every legitimate sync after it.
SNAPSHOT_FUTURE_TOLERANCE: Final = timedelta(hours=1)

# POS product CSV upload cap.
CSV_MAX_BYTES: Final[int] = 2 * 1024 * 1024

# Mapping suggestions: how many to show, and the floor below which a
# candidate is not worth showing at all.
SUGGESTION_COUNT: Final[int] = 3
SUGGESTION_MIN_SCORE: Final[float] = 0.30

MAPPING_PAGE_SIZE: Final[int] = 50
PRICE_MISMATCH_PAGE_SIZE: Final[int] = 50

# Postgres advisory-lock key serialising snapshot application. Arbitrary but
# fixed; it only needs to differ from any other advisory lock in this database
# (none exist in this project).
SNAPSHOT_LOCK_KEY: Final[int] = 7_012_042

# "Mark recorded" by hand: the reason is mandatory so the audit trail says why.
MARK_RECORDED_MIN_REASON_LENGTH: Final[int] = 5
MARK_RECORDED_MAX_REASON_LENGTH: Final[int] = 400
