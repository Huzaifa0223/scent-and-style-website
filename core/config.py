"""Typed, non-merchant-configurable constants.

Values a merchant might reasonably want to change belong on
``store.models.StoreSettings`` instead (CLAUDE.md: "if a merchant might
change it, it is a StoreSettings field"). What lives here are operational
constants: cache keys, and thresholds that are about how the system runs,
not what the business does.
"""

from __future__ import annotations

from typing import Final

STORE_SETTINGS_CACHE_KEY: Final[str] = "store:settings:singleton"
