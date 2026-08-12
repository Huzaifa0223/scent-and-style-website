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

# Starting value for a new ProductVariant.low_stock_threshold — a merchant
# edits this per variant immediately if they want something else; this is
# just the row default, not a business rule.
DEFAULT_LOW_STOCK_THRESHOLD: Final[int] = 5

# JPEG/WebP encode quality for generated product image derivatives (§2.5).
IMAGE_DERIVATIVE_QUALITY: Final[int] = 85
