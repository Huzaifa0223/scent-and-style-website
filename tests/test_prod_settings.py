"""Settings modules aren't Django apps, so they get no pytest-django DB
access and no test client — these run config.settings.prod in a subprocess
and check how it fails, which is the only reliable way to test module-level
``raise ImproperlyConfigured`` statements without corrupting the settings
already loaded into this test process.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_BASE_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "SECRET_KEY": "subprocess-check-only-not-a-real-secret-0123456789",
    "ALLOWED_HOSTS": "example.com",
    "DATABASE_URL": "postgres://postgres:postgres@localhost:5432/ecommerce",
    "AWS_ACCESS_KEY_ID": "x",
    "AWS_SECRET_ACCESS_KEY": "x",
    "AWS_STORAGE_BUCKET_NAME": "x",
    "AWS_S3_ENDPOINT_URL": "https://example.r2.cloudflarestorage.com",
}


def _run_django_setup(**overrides: str) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env.pop("DEBUG", None)
    env.update(_BASE_ENV)
    env.update(overrides)
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        check=False,
    )


def test_prod_settings_refuses_to_load_with_debug_true() -> None:
    result = _run_django_setup(DEBUG="True")
    assert result.returncode != 0
    assert b"ImproperlyConfigured" in result.stderr
    assert b"DEBUG must be False" in result.stderr


def test_prod_settings_refuses_to_load_without_allowed_hosts() -> None:
    result = _run_django_setup(DEBUG="False", ALLOWED_HOSTS="")
    assert result.returncode != 0
    assert b"ImproperlyConfigured" in result.stderr
    assert b"ALLOWED_HOSTS must be set" in result.stderr


def test_prod_settings_loads_cleanly_with_valid_config() -> None:
    result = _run_django_setup(DEBUG="False")
    assert result.returncode == 0, result.stderr.decode()


def test_prod_settings_trusts_the_proxy_headers_caddy_sets() -> None:
    """§41, roadmap Stage 13: Caddy terminates TLS and reverse-proxies to
    gunicorn over plain HTTP — without SECURE_PROXY_SSL_HEADER,
    request.is_secure() is always False behind it (breaking
    SECURE_SSL_REDIRECT and every build_absolute_uri() call). Without
    TRUST_X_FORWARDED_FOR, core.ratelimit.client_ip() sees Caddy's own
    address for every request instead of the real client's."""
    env = os.environ.copy()
    env.pop("DEBUG", None)
    env.update(_BASE_ENV)
    env["DEBUG"] = "False"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from django.conf import settings; "
            "print(settings.SECURE_PROXY_SSL_HEADER); print(settings.TRUST_X_FORWARDED_FOR)",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    stdout_lines = result.stdout.decode().strip().splitlines()
    assert stdout_lines == ["('HTTP_X_FORWARDED_PROTO', 'https')", "True"]
