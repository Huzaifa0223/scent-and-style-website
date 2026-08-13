from __future__ import annotations

import pytest

from core.phone import normalize_pk_mobile


@pytest.mark.parametrize(
    "raw",
    [
        "03001234567",
        "+923001234567",
        "923001234567",
        "3001234567",
        " 0300 123 4567 ",
        "0300-1234567",
    ],
)
def test_normalize_pk_mobile_accepts_every_recognised_shape(raw: str) -> None:
    assert normalize_pk_mobile(raw) == "+923001234567"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "12345",
        "04001234567",  # not a mobile prefix (doesn't start with 3)
        "+1234567890",
        "030012345",  # too short
        "030012345678",  # too long
        "abcnotaphone",
    ],
)
def test_normalize_pk_mobile_rejects_unrecognised_input(raw: str) -> None:
    assert normalize_pk_mobile(raw) is None
