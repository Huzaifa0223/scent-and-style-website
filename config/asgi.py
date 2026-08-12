"""ASGI config. Not served in production (WSGI via gunicorn/Caddy is the deploy
path — see docs/deploy.md); kept for local tooling that expects it."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_asgi_application()
