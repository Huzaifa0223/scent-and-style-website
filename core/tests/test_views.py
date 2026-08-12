from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db.utils import OperationalError
from django.test import Client


@pytest.mark.django_db
def test_healthz_returns_ok_with_db_connectivity(client: Client) -> None:
    response = client.get("/healthz/")
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"status": "ok", "database": True}


@pytest.mark.django_db
def test_healthz_returns_503_when_db_unreachable(client: Client) -> None:
    with patch("core.views.connection.cursor", side_effect=OperationalError("down")):
        response = client.get("/healthz/")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": False}


@pytest.mark.django_db
def test_healthz_response_has_no_extra_fields(client: Client) -> None:
    response = client.get("/healthz/")
    payload = response.json()
    assert set(payload.keys()) == {"status", "database"}
