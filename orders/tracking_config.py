"""Typed config for public order tracking's rate limiter (§25, roadmap
Stage 11) — operational/security thresholds, not merchant-configurable
business policy, so these live here rather than on ``StoreSettings``
(CLAUDE.md: "if a merchant might change it, it is a StoreSettings
field" — no merchant has a legitimate reason to want a *weaker*
anti-enumeration control, so this isn't that kind of value).
"""

from __future__ import annotations

from typing import Final

# "A small number of attempts per minute" (§25) — throttles rapid-fire
# submissions from one IP regardless of whether they succeed.
TRACKING_RATE_LIMIT_MAX_ATTEMPTS: Final[int] = 5
TRACKING_RATE_LIMIT_WINDOW_SECONDS: Final[int] = 60

# "A longer lockout after repeated failures" (§25) — a sliding window
# over *failed* attempts only. Self-expires as old failures age out of
# the window; there is no separate lockout flag or duration to track.
TRACKING_LOCKOUT_FAILURE_THRESHOLD: Final[int] = 10
TRACKING_LOCKOUT_WINDOW_SECONDS: Final[int] = 3600
