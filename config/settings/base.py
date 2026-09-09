"""Base settings shared by every environment.

Environment-specific modules (``dev``, ``prod``, ``test``) do ``from .base import *``
and override only what differs. Non-merchant configuration (secrets, database URL,
storage credentials) is read from the environment via ``django-environ`` — see
``.env.example``. No merchant-specific value belongs here; those live on
``store.models.StoreSettings`` (§40).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import django_stubs_ext
import environ

django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(str(BASE_DIR / ".env"))

SECRET_KEY = env.str("SECRET_KEY")
DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "django.contrib.sitemaps",
    "core",
    "store",
    "catalog",
    "accounts",
    "inventory",
    "search",
    "storefront",
    "cart",
    "customers",
    "payments",
    "shipping",
    "orders",
    "notifications",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.store_settings",
                "cart.context_processors.cart",
                "core.context_processors.canonical_url",
                "core.context_processors.static_asset_version",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache_table",
    },
}

SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_CACHE_ALIAS = "default"

# The merchant portal is the only authenticated surface (requirements §1) —
# every login/logout redirect funnels through it, never django-admin.
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "portal:product_list"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2 first per CLAUDE.md — Django falls back to the others only to verify
# password hashes created before this project standardised on Argon2.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

LANGUAGE_CODE = "en-us"

# Locked decisions (CLAUDE.md): PKR / Asia-Karachi, sourced from StoreSettings
# for display purposes — USE_TZ/TIME_ZONE below is the process-level clock,
# independent of the merchant-editable StoreSettings.timezone field.
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# core/backup.py (§55, roadmap Stage 13). BACKUP_PG_DUMP_PATH defaults to
# relying on PATH (true on the production host once postgresql-client is
# installed per docs/deploy.md); overridable because this dev machine's
# Postgres install does not put pg_dump on PATH by itself.
BACKUP_DIR = Path(env.str("BACKUP_DIR", default=str(BASE_DIR / "backups")))
BACKUP_PG_DUMP_PATH = env.str("BACKUP_PG_DUMP_PATH", default="pg_dump")

# Dotted path to the SearchBackend implementation (search/backends.py's
# protocol) — the same "one concrete implementation, selected by settings"
# pattern as DeliveryCalculator/NotificationChannel/PaymentProvider
# elsewhere in this project, so a future non-Postgres backend drops in here
# without touching view code.
SEARCH_BACKEND = "search.backends.PostgresSearchBackend"

# §41's "error monitoring hook" (roadmap Stage 13): Django's own built-in
# mail_admins mechanism, no new dependency (Sentry etc. aren't in the
# approved list). django.utils.log.DEFAULT_LOGGING already wires the
# "django" logger to a mail_admins AdminEmailHandler out of the box — but
# that wiring is a *separate*, earlier logging.config.dictConfig() call
# than the LOGGING dict below (Django applies DEFAULT_LOGGING first, then
# this project's own LOGGING on top). Redefining the "django" logger's
# handlers here without re-listing "mail_admins" would silently drop
# Django's own default, which is exactly what an earlier version of this
# file did — confirmed via `logging.getLogger("django").handlers` showing
# only the console StreamHandler, no AdminEmailHandler, even though
# nothing here ever intended to disable it. Re-declared explicitly below
# instead of relying on the default surviving a second dictConfig() call.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        # Only fires when DEBUG=False (require_debug_false), and only
        # sends anywhere once ADMINS and EMAIL_* are actually configured
        # (config.settings.prod / .env — see docs/deploy.md's human task
        # for the real SMTP credentials this needs to send for real).
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {
            "handlers": ["console", "mail_admins"],
            "level": "INFO",
            "propagate": False,
        },
        # Django's DB backend logs every query at DEBUG when settings.DEBUG
        # is True; left at INFO this drowns out everything else in dev.
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ADMINS format: "Name:email,Name:email" — kept to a flat env-friendly
# string rather than requiring JSON in a single env var. Empty by default
# (no addresses configured yet — a real human task, see docs/deploy.md);
# AdminEmailHandler simply sends nothing when ADMINS is empty, it does
# not error.
ADMINS = [
    (name, email)
    for name, _, email in (pair.partition(":") for pair in env.list("ADMINS", default=[]))
    if email
]
SERVER_EMAIL = env.str("SERVER_EMAIL", default="root@localhost")
EMAIL_BACKEND = env.str("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env.str("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env.str("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env.str("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
