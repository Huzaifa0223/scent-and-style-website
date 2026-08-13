from __future__ import annotations

import pytest

from customers import services
from customers.factories import CustomerFactory
from customers.models import Customer


@pytest.mark.django_db
def test_get_or_create_customer_creates_a_new_row() -> None:
    customer = services.get_or_create_customer(
        name="Ayesha Khan",
        phone="+923001234567",
        whatsapp_number="+923001234567",
        email="ayesha@example.com",
    )

    assert Customer.objects.count() == 1
    assert customer.name == "Ayesha Khan"
    assert customer.phone == "+923001234567"


@pytest.mark.django_db
def test_get_or_create_customer_matches_an_existing_row_on_phone() -> None:
    existing = CustomerFactory(phone="+923001234567", name="Old Name")

    customer = services.get_or_create_customer(
        name="New Name", phone="+923001234567", whatsapp_number="", email=""
    )

    assert Customer.objects.count() == 1
    assert customer.pk == existing.pk


@pytest.mark.django_db
def test_get_or_create_customer_updates_fields_from_a_repeat_submission() -> None:
    CustomerFactory(phone="+923001234567", name="Old Name", email="old@example.com")

    customer = services.get_or_create_customer(
        name="New Name",
        phone="+923001234567",
        whatsapp_number="+923009999999",
        email="new@example.com",
    )

    assert customer.name == "New Name"
    assert customer.email == "new@example.com"
    assert customer.whatsapp_number == "+923009999999"


@pytest.mark.django_db
def test_get_or_create_customer_does_not_overwrite_known_fields_with_blanks() -> None:
    """A blank email on this order must not wipe a known one from a
    previous order."""
    CustomerFactory(phone="+923001234567", email="known@example.com")

    customer = services.get_or_create_customer(
        name="Same Name", phone="+923001234567", whatsapp_number="", email=""
    )

    assert customer.email == "known@example.com"
