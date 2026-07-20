"""Tests del endpoint de health-check."""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_health_ok(client):
    """Responde 200 y reporta la base de datos accesible."""
    response = client.get(reverse("farms:health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
