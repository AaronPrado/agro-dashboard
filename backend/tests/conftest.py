"""Fixtures compartidas por la batería de tests.

pytest descubre este fichero automáticamente: las fixtures definidas aquí
están disponibles en todos los tests del directorio sin necesidad de importarlas.
"""

import datetime

import pytest
from rest_framework.test import APIClient

from farms.models import Animal, Farm


@pytest.fixture
def api_client():
    """Cliente HTTP de DRF para ejercitar los endpoints de la API.

    Se prefiere al cliente de Django porque negocia el contenido como lo hará
    un consumidor real de la API y facilita enviar cuerpos en JSON.
    """
    return APIClient()


@pytest.fixture
def farm(db):
    """Granja base sobre la que colgar animales en los tests."""
    return Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )


@pytest.fixture
def animal(farm):
    """Animal base sobre el que colgar registros de producción."""
    return Animal.objects.create(
        farm=farm,
        ear_tag="ES0001",
        birth_date=datetime.date(2021, 3, 1),
    )
