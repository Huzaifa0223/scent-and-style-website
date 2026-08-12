"""Sweeper (§10.4): deletes StockReservation rows past their TTL. Cron
every 10 minutes — see README for the crontab entry. Idempotent and safe
to run concurrently with itself; see inventory/services.py's
release_expired_reservations() docstring for why, and
inventory/tests/test_concurrency.py::test_gate6_... for the proof.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand

from inventory.services import release_expired_reservations

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Delete StockReservation rows whose TTL has elapsed."

    def handle(self, *args: Any, **options: Any) -> None:
        count = release_expired_reservations()
        logger.info("release_expired_reservations: released %d reservation(s)", count)
        self.stdout.write(f"Released {count} expired reservation(s).")
