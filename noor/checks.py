from __future__ import annotations

from django.conf import settings
from django.core.checks import CheckMessage, Tags, Warning, register

from .config import SYNC_TOKEN_MIN_LENGTH


@register(Tags.security, deploy=True)
def sync_token_is_configured(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """A Warning (never an Error): a missing token must not stop the shop
    booting — the private API simply refuses every request until it is set."""
    token = getattr(settings, "SCENT_SYNC_TOKEN", "")
    if len(token) >= SYNC_TOKEN_MIN_LENGTH:
        return []
    return [
        Warning(
            f"SCENT_SYNC_TOKEN is missing or shorter than {SYNC_TOKEN_MIN_LENGTH} characters.",
            hint=(
                "/api/kiosk/sync/ answers 401 to every request until it is set. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(40))"'
            ),
            id="noor.W001",
        )
    ]
