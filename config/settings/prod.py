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

# Caddy (the only front door, per CLAUDE.md) terminates TLS and reverse-
# proxies to gunicorn over plain HTTP — without this, request.is_secure()
# is always False behind that proxy, which both breaks SECURE_SSL_REDIRECT
# (a redirect loop: Django redirects to https, the proxied request still
# looks like http, Django redirects again) and makes every
# request.build_absolute_uri() call (core.context_processors.canonical_url,
# storefront.seo's JSON-LD, storefront.sitemaps) emit http:// URLs in
# production. docs/deploy.md's Caddyfile sets X-Forwarded-Proto on every
# proxied request to match.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# core.ratelimit.client_ip() / orders.tracking.client_ip() read this to
# decide whether to trust X-Forwarded-For over REMOTE_ADDR (which, behind
# a reverse proxy, is otherwise always Caddy's own address — every
# customer would share one rate-limit bucket). Safe specifically because
# Caddy is the *only* process gunicorn accepts connections from
# (docs/deploy.md binds gunicorn to a loopback/unix socket Caddy alone
# reaches) — a single trusted hop appending the real client address as
# X-Forwarded-For's last entry, not an arbitrary, spoofable proxy chain.
# Resolves the open question recorded in specs/state.md's Stage 11 notes.
TRUST_X_FORWARDED_FOR = True

# Cloudflare R2 (S3-compatible) object storage is optional in the local
# deployment model: if the merchant is using the server's filesystem instead
# of R2, Django should keep booting with the built-in local storage backend
# and not fail at import time. The project still supports the managed-R2
# path by selecting the R2 backend only when all required storage settings
# are present.
R2_CONFIG = {
    "AWS_ACCESS_KEY_ID": env.str("AWS_ACCESS_KEY_ID", default=""),
    "AWS_SECRET_ACCESS_KEY": env.str("AWS_SECRET_ACCESS_KEY", default=""),
    "AWS_STORAGE_BUCKET_NAME": env.str("AWS_STORAGE_BUCKET_NAME", default=""),
    "AWS_S3_ENDPOINT_URL": env.str("AWS_S3_ENDPOINT_URL", default=""),
}
if all(R2_CONFIG.values()):
    STORAGES["default"] = {"BACKEND": "core.storage.R2MediaStorage"}
    AWS_ACCESS_KEY_ID = R2_CONFIG["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_ACCESS_KEY = R2_CONFIG["AWS_SECRET_ACCESS_KEY"]
    AWS_STORAGE_BUCKET_NAME = R2_CONFIG["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = R2_CONFIG["AWS_S3_ENDPOINT_URL"]
    AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="auto")
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
else:
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    AWS_ACCESS_KEY_ID = ""
    AWS_SECRET_ACCESS_KEY = ""
    AWS_STORAGE_BUCKET_NAME = ""
    AWS_S3_ENDPOINT_URL = ""
    AWS_S3_REGION_NAME = env.str("AWS_S3_REGION_NAME", default="auto")
    AWS_S3_ADDRESSING_STYLE = "virtual"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False

# core/backup.py's media mirror target. Optional: a second bucket gives
# real off-box protection; left unset, the mirror lives under a prefix in
# the same bucket instead (see core/backup.py's module docstring).
AWS_BACKUP_BUCKET_NAME = env.str("AWS_BACKUP_BUCKET_NAME", default="")

# Static asset delivery. Off by default, which is the documented VPS
# deployment: Caddy is the front door and serves STATIC_ROOT off disk,
# which is faster than routing asset requests through Django and is what
# docs/deploy.md's Caddyfile is written for.
#
# Managed platforms (Railway, Render — see docs/deploy-paas.md) have no
# such front door: the app process is the only thing listening, and Django
# does not serve static itself once DEBUG is False, so CSS, JS and the
# self-hosted fonts would all 404. Setting SERVE_STATIC_FROM_R2=True
# pushes collectstatic output to the R2 bucket already configured above
# and serves assets from there.
#
# WhiteNoise is the more common answer to this and would let the app serve
# its own static files. It is deliberately not used: it is a new runtime
# dependency and CLAUDE.md's approved list is explicit, whereas
# django-storages is already here for media. If WhiteNoise is preferred
# later that is a dependency decision to take on its own merits, not a
# side effect of choosing a host.
SERVE_STATIC_FROM_R2 = env.bool("SERVE_STATIC_FROM_R2", default=False)
if SERVE_STATIC_FROM_R2:
    STORAGES["staticfiles"] = {"BACKEND": "core.storage.R2StaticStorage"}
