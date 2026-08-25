from __future__ import annotations

from core.templatetags.phone import tel_target


def test_tel_target_preserves_leading_plus_and_strips_formatting() -> None:
    assert tel_target("+92 334-117 2222") == "+923341172222"


def test_tel_target_returns_digits_only_for_local_numbers() -> None:
    assert tel_target("(051) 123 4567") == "0511234567"


def test_tel_target_returns_empty_string_for_blank_values() -> None:
    assert tel_target("") == ""
