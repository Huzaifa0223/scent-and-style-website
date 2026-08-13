"""``PaymentProvider`` protocol (requirements §28) — no implementation
ships in MVP. Kept deliberately minimal rather than guessing at a fuller
interface no real provider has validated against yet; a future concrete
provider (JazzCash, Easypaisa, cards, ...) is free to need more than this
and extend the protocol then, not now.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from orders.models import Order


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    transaction_id: str | None = None
    message: str = ""


class PaymentProvider(Protocol):
    def charge(self, *, order: Order, amount: Decimal) -> PaymentResult: ...
