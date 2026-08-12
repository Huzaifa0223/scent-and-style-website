from __future__ import annotations

from decimal import Decimal

from core.templatetags.money import money


def test_money_formats_with_thousands_separator_and_two_places() -> None:
    assert money(Decimal("1234.5")) == "Rs. 1,234.50"


def test_money_defaults_none_to_zero() -> None:
    assert money(None) == "Rs. 0.00"


def test_money_accepts_int_and_float_and_str() -> None:
    assert money(10) == "Rs. 10.00"
    assert money(10.5) == "Rs. 10.50"
    assert money("10.50") == "Rs. 10.50"


def test_money_unknown_currency_code_falls_back_to_code_itself() -> None:
    assert money(Decimal("10"), "USD") == "USD 10.00"


def test_money_rejects_unparseable_input_without_raising() -> None:
    assert money("not-a-number") == "Rs. 0.00"


def test_money_rounds_half_even_to_two_decimal_places() -> None:
    # Decimal's default rounding (ROUND_HALF_EVEN): 1.005 is an exact tie
    # between 1.00 and 1.01, so it rounds to the even neighbour, 1.00.
    assert money(Decimal("1.005")) == "Rs. 1.00"
