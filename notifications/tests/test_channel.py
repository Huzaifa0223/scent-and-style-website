from __future__ import annotations

from notifications.whatsapp.channel import WhatsAppLinkChannel


def test_build_url_strips_the_leading_plus_and_encodes_the_message() -> None:
    url = WhatsAppLinkChannel().build_url(phone="+923001234567", message="Hi there!")

    assert url == "https://wa.me/923001234567?text=Hi%20there%21"


def test_build_url_with_a_blank_phone_omits_the_phone_segment() -> None:
    url = WhatsAppLinkChannel().build_url(phone="", message="Hello")

    assert url == "https://wa.me/?text=Hello"


def test_build_url_encodes_newlines_and_special_characters() -> None:
    url = WhatsAppLinkChannel().build_url(phone="+923001234567", message="Line 1\nLine 2 & 3")

    encoded = url.split("?text=")[1]
    assert "%0A" in encoded  # newline
    assert "%20" in encoded  # space
    assert "\n" not in encoded
