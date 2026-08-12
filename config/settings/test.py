"""Settings for the automated test suite (pytest-django).

pytest-django builds its test database from these ``DATABASES`` by prefixing
``test_`` onto the configured name — no separate database URL needed.
"""

from __future__ import annotations

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver"]
