from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.template import engines
from django.test import RequestFactory


def test_vendor_files_exist_on_disk() -> None:
    vendor_dir = Path(settings.BASE_DIR) / "static" / "vendor"
    assert (vendor_dir / "htmx.min.js").is_file()
    assert (vendor_dir / "alpine.min.js").is_file()


@pytest.mark.django_db
def test_base_template_loads_htmx_and_alpine_from_vendor_not_cdn(rf: RequestFactory) -> None:
    request = rf.get("/")
    html = engines["django"].get_template("base.html").render({}, request)
    assert "vendor/htmx.min.js" in html
    assert "vendor/alpine.min.js" in html
    for cdn_marker in ("unpkg.com", "cdn.jsdelivr", "cdnjs.cloudflare"):
        assert cdn_marker not in html


def test_500_template_renders_with_no_context_like_django_actually_calls_it() -> None:
    """Mirrors django.views.defaults.server_error, which calls template.render()
    with neither a context nor a request — context processors never run for it."""
    html = engines["django"].get_template("500.html").render()
    assert "Something went wrong" in html
    assert "<html" in html


@pytest.mark.django_db
def test_404_response_renders_styled_template_not_django_default(client) -> None:
    response = client.get("/this-page-does-not-exist/")
    assert response.status_code == 404
    assert b"We couldn't find that page" in response.content
