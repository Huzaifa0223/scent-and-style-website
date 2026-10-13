from __future__ import annotations

from django.apps import AppConfig


class NoorConfig(AppConfig):
    """Integration with Noor, the store's fragrance-consultant app (in-store
    tablets plus the public web app at ``settings.NOOR_ORIGIN``).

    Self-contained on purpose: it reads the catalog but owns exactly one
    table (``KioskBackup``) and changes no behaviour of any other app.
    """

    name = "noor"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (registers the deploy check)
