"""Customer domain model (requirements §29, roadmap Stage 8).

Created implicitly at checkout, matched on normalised phone — never a
customer-facing login or account in MVP (§29: "No customer login in
MVP"). The derived stats §29 also names (``total_orders``, ``total_spent``,
``last_order_at``) and a profile/order-history portal page are
deliberately not built here: no roadmap stage assigns that page anywhere
(checked end to end), so building it now would be speculative scope
rather than something Stage 8 needs — recorded under Proposed spec
amendments in state.md instead of built.
"""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class Customer(TimeStampedModel):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, unique=True, db_index=True)
    whatsapp_number = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"
