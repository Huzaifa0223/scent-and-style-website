"""Settings for the automated test suite (pytest-django).

pytest-django builds its test database from these ``DATABASES`` by prefixing
``test_`` onto the configured name — no separate database URL needed.
"""

from __future__ import annotations

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["testserver"]

# Never let a test attempt a real SMTP connection (base.py's default is
# the real SMTP backend, for production). locmem is also what pytest-
# django's own `mailoutbox` fixture requires to capture sent messages.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
