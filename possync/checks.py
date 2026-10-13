from __future__ import annotations

from django.conf import settings
from django.core.checks import CheckMessage, Tags, Warning, register

from noor.config import SYNC_TOKEN_MIN_LENGTH

from .config import POS_TOKEN_SETTING


@register(Tags.security, deploy=True)
def pos_token_is_configured(app_configs: object, **kwargs: object) -> list[CheckMessage]:
    """A Warning, never an Error: a missing token must not stop the shop
    booting — the POS API simply refuses every request until it is set."""
    token = getattr(settings, POS_TOKEN_SETTING, "")
    if len(token) >= SYNC_TOKEN_MIN_LENGTH:
        return []
    return [
        Warning(
            f"{POS_TOKEN_SETTING} is missing or shorter than {SYNC_TOKEN_MIN_LENGTH} characters.",
            hint=(
                "/api/pos/sync/ answers 401 to every request until it is set. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(40))" '
                "(and use a different value from SCENT_SYNC_TOKEN)."
            ),
            id="possync.W001",
        )
    ]
