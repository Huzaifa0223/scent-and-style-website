"""Order creation (requirements §20-22, §24, §27, roadmap Stage 8) — the
transactional core. ``create_order()`` is the only sanctioned way to turn
a cart into an ``Order``.

**The actual concurrency-safety mechanism is ``inventory.services.
reserve()``, not the pre-check below.** ``reserve()`` is the only
function that ever creates a ``StockReservation``, and it always takes
``select_for_update()`` on the variant row before writing — Postgres
blocks *any* other writer to a locked row, not just other
``select_for_update()`` callers, so two concurrent ``create_order()``
calls for the same variant serialize through that lock regardless of
what either transaction did beforehand. The pre-check in step 3/4 below
exists to produce a good per-line error message *before* writing
anything, across every line in one pass, not to be the safety guarantee
itself — by the time step 4 passes, step 10's ``reserve()`` calls cannot
fail for stock reasons (the lock taken in step 3 is held continuously
through commit), and are not optional even so, since they're the only
code path that actually writes the reservation rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from cart import services as cart_services
from cart.models import Cart
from catalog.models import ProductVariant
from customers import services as customer_services
from inventory import services as inventory_services
from shipping.calculators import get_delivery_calculator

from .models import Order, OrderItem
from .order_number import generate_order_number


@dataclass(frozen=True)
class CheckoutInput:
    """Everything checkout's form collects, already validated and
    normalised (``phone``/``whatsapp_number`` to E.164) by the caller —
    this function trusts its inputs rather than re-validating form-level
    concerns."""

    name: str
    phone: str
    whatsapp_number: str
    email: str
    address: str
    city: str
    postal_code: str
    instructions: str
    notes: str


@dataclass(frozen=True)
class CheckoutLineError:
    product_name: str
    requested_quantity: int
    available_quantity: int


class CheckoutError(Exception):
    """Base for anything that stops create_order() before commit."""


class EmptyCartError(CheckoutError):
    pass


class CheckoutValidationError(CheckoutError):
    def __init__(self, errors: list[CheckoutLineError]) -> None:
        self.errors = errors
        super().__init__(f"{len(errors)} line(s) failed availability re-check.")


@transaction.atomic
def create_order(*, cart: Cart, checkout_input: CheckoutInput) -> Order:
    # 1. Read the cart's own lines directly — deliberately not
    #    cart.services.cart_lines(), whose availability read is
    #    unlocked and taken before this transaction started. Reusing it
    #    for price/availability here would let a mid-checkout reprice
    #    produce an Order whose subtotal doesn't match the sum of its own
    #    OrderItem.line_totals. Every price and availability number below
    #    comes from the single locked read in step 3/4, and nowhere else.
    items = list(cart.items.all())
    if not items:
        raise EmptyCartError

    # 2. Lock the Cart row itself. NOTE: this does not fully solve
    #    double-submit — two requests from one session can still resolve
    #    to two different Cart rows, or race Cart creation itself.
    #    Recorded as an open question in specs/state.md, not claimed
    #    solved; kept because it's still a real (if partial) guard for
    #    the common case where the Cart row already exists.
    Cart.objects.select_for_update().get(pk=cart.pk)

    # 3. Lock every referenced variant row, deterministically ordered to
    #    avoid a deadlock between two checkouts that share variants in
    #    different orders. Deliberately NOT combined with
    #    with_available_quantity(): that annotation is a correlated
    #    Subquery over StockReservation, and SELECT FOR UPDATE against a
    #    query shaped like that either errors or locks only the outer
    #    ProductVariant rows while leaving the StockReservation rows the
    #    subquery aggregates over completely unlocked.
    variant_ids = sorted({item.variant_id for item in items if item.variant_id is not None})
    locked_ids = set(
        ProductVariant.objects.select_for_update()
        .filter(pk__in=variant_ids)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    # 4. With those locks held, a separate unlocked query reads
    #    availability — safe without its own lock, since no other
    #    transaction can change stock_quantity on these rows (blocked by
    #    the lock above) or insert a competing StockReservation for them
    #    (every path that does so is reserve(), which takes the same
    #    lock first). prefetch_related is required for variant.
    #    display_label (used in step 9) to stay N+1-safe.
    available_by_id = {
        variant.pk: variant
        for variant in ProductVariant.objects.with_available_quantity()
        .select_related("product")
        .prefetch_related("variant_attribute_values__value")
        .filter(pk__in=locked_ids)
    }

    # Keyed by CartItem.pk (always non-None), not variant_id (nullable) —
    # every item that survives this loop without an error has a real
    # entry here, so steps 6/9-10 read from this dict rather than
    # re-deriving "is this item's variant_id present and valid" a second
    # time from a type mypy can't narrow across the loop boundary.
    errors: list[CheckoutLineError] = []
    variant_by_item_pk: dict[int, ProductVariant] = {}
    for item in items:
        variant = available_by_id.get(item.variant_id) if item.variant_id is not None else None
        if variant is None:
            errors.append(
                CheckoutLineError(
                    product_name="An item in your cart",
                    requested_quantity=item.quantity,
                    available_quantity=0,
                )
            )
        elif not variant.is_active:
            errors.append(
                CheckoutLineError(
                    product_name=variant.product.name,
                    requested_quantity=item.quantity,
                    available_quantity=0,
                )
            )
        elif variant.available_quantity < item.quantity:  # type: ignore[attr-defined]
            errors.append(
                CheckoutLineError(
                    product_name=variant.product.name,
                    requested_quantity=item.quantity,
                    available_quantity=variant.available_quantity,  # type: ignore[attr-defined]
                )
            )
        else:
            variant_by_item_pk[item.pk] = variant
    if errors:
        raise CheckoutValidationError(errors)

    # 5. Resolve/create the Customer.
    customer = customer_services.get_or_create_customer(
        name=checkout_input.name,
        phone=checkout_input.phone,
        whatsapp_number=checkout_input.whatsapp_number,
        email=checkout_input.email,
    )

    # 6. subtotal/delivery/total — every price read from
    #    variant_by_item_pk, the locked read, never from step 1's raw
    #    cart items.
    subtotal = sum(
        (variant_by_item_pk[item.pk].price * item.quantity for item in items),
        Decimal("0.00"),
    )
    delivery_charge = get_delivery_calculator().calculate(
        subtotal=subtotal, city=checkout_input.city
    )
    discount = Decimal("0.00")
    total = subtotal + delivery_charge - discount

    # 7-8. Generate the order number and create the Order in one insert.
    order = Order.objects.create(
        order_number=generate_order_number(),
        customer=customer,
        customer_name=checkout_input.name,
        customer_phone=checkout_input.phone,
        customer_whatsapp_number=checkout_input.whatsapp_number,
        customer_email=checkout_input.email,
        delivery_address=checkout_input.address,
        delivery_city=checkout_input.city,
        delivery_postal_code=checkout_input.postal_code,
        delivery_instructions=checkout_input.instructions,
        subtotal=subtotal,
        delivery_charge=delivery_charge,
        discount=discount,
        total=total,
        customer_notes=checkout_input.notes,
    )

    # 9-10. OrderItem snapshots, then a reservation per line — reserve()
    #       is the real safety mechanism, see this module's docstring.
    for item in items:
        variant = variant_by_item_pk[item.pk]
        OrderItem.objects.create(
            order=order,
            variant=variant,
            product_name=variant.product.name,
            variant_label=variant.display_label,
            sku=variant.sku,
            unit_price=variant.price,
            quantity=item.quantity,
            line_total=variant.price * item.quantity,
        )
        inventory_services.reserve(variant_id=variant.pk, quantity=item.quantity, order=order)

    # 11. Empty the cart now that its contents are safely an Order.
    cart_services.clear_cart(cart)

    return order
