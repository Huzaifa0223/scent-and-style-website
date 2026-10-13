from __future__ import annotations

from django.apps import AppConfig


class PosSyncConfig(AppConfig):
    """POS <-> website stock sync.

    The store POS is the master of *physical* stock; online orders ship from
    the same shelves. This app maps POS SKUs to website variants (by an
    admin, never automatically), accepts POS stock snapshots, and tells the
    POS which web orders it still has to record. It never changes a price.
    """

    name = "possync"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from . import checks  # noqa: F401  (registers the deploy check)
