"""Payment state enum (requirements §28) — defined now and unused. No
``Model`` subclass in this file: the ``payments`` app ships in MVP as this
enum plus the ``PaymentProvider`` protocol (``protocols.py``) and the
payment-related columns on ``orders.Order`` — nothing else. Adding a real
payment provider (JazzCash, Easypaisa, COD, cards, bank transfer) must
never require touching ``orders.Order``'s schema; the columns already
exist, unused, ready.
"""

from __future__ import annotations

from django.db import models


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    INITIATED = "initiated", "Initiated"
    SUCCESSFUL = "successful", "Successful"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
    PARTIALLY_REFUNDED = "partially_refunded", "Partially Refunded"
