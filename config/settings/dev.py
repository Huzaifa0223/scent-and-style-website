"""Local development settings."""

from __future__ import annotations

from .base import *
from .base import env

DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

# Verbose SQL/template errors are useful locally; kept off the fast console
# handler used everywhere else so dev logs stay readable.
LOGGING["loggers"]["django"]["level"] = "DEBUG" if DEBUG else "INFO"
