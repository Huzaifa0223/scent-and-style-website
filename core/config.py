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

# search/backends.py (§15): Postgres text-search config used for both the
# tsvector column expression and every query against it — must match the
# one baked into the GIN index migration (catalog/migrations/0006), or the
# index silently stops being usable.
SEARCH_TSVECTOR_CONFIG: Final[str] = "simple"

# search/backends.py: result-page vs. type-ahead-box row caps. Suggestions
# are deliberately smaller — a dropdown, not a page.
SEARCH_RESULTS_LIMIT: Final[int] = 20
SEARCH_SUGGESTIONS_LIMIT: Final[int] = 8

# core/validators.py (§41, roadmap Stage 13). Django's ImageField already
# rejects a non-image payload via Pillow (a real content check, not an
# extension check) — this is the one thing that check doesn't cover: a
# hard cap so a large-but-genuine image can't be used to exhaust memory
# or CPU during derivative generation (core/images.py). 8 MB comfortably
# fits any real product photo a merchant would upload from a phone.
MAX_IMAGE_UPLOAD_BYTES: Final[int] = 8 * 1024 * 1024

# core/backup.py (§55, roadmap Stage 13): how long a nightly pg_dump (local
# file and its R2 copy) survives before the next run's retention pass
# deletes it. "30-day retention" is the roadmap's own number.
BACKUP_RETENTION_DAYS: Final[int] = 30

# R2 key prefixes for core/backup.py's two artifact kinds, kept apart so
# retention (dump-only) never touches the media mirror and vice versa.
BACKUP_DB_DUMP_PREFIX: Final[str] = "backups/db/"
BACKUP_MEDIA_MIRROR_PREFIX: Final[str] = "backups/media-mirror/"

# pg_trgm.word_similarity_threshold (core/migrations/0003) — locked in
# explicitly rather than left at Postgres's own default (also 0.6), per
# CLAUDE.md's Traps note: "Do not rely on the default... Set it in a
# migration so CI and production agree." Verified against real Postgres
# data (afnn/Afnan typo, EDP-9PM-100 partial-SKU-in-a-longer-SKU cases)
# before being locked in — see search/tests/test_backend.py.
PG_TRGM_WORD_SIMILARITY_THRESHOLD: Final[float] = 0.6
