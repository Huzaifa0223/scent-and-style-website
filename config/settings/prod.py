"""Production settings.

Fails loudly rather than silently running insecure — a truthy ``DEBUG`` or a
missing ``ALLOWED_HOSTS`` raises at import time instead of booting a server
that leaks stack traces or accepts any Host header.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from .base import *
from .base import env

DEBUG = env.bool("DEBUG", default=False)
if DEBUG:
    raise ImproperlyConfigured("DEBUG must be False when using config.settings.prod.")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must be set in production.")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Cloudflare R2 (S3-compatible) object storage — selected here, by settings
# module, never by an `if DEBUG` branch inside storage code (CLAUDE.md).
STORAGES["default"] = {"BACKEND": "core.storage.R2MediaStorage"}

AWS_ACCESS_KEY_ID = env.str("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = env.str("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = env.str("AWS_STORAGE_BUCKET_NAME")
AWS_S3_ENDPOINT_URL = env.str("AWS_S3_ENDPOINT_URL")
AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="auto")
AWS_S3_ADDRESSING_STYLE = "virtual"
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = False
