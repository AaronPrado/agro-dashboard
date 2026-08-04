"""Fixtures compartidas por la batería de tests.

pytest descubre este fichero automáticamente: las fixtures definidas aquí
están disponibles en todos los tests del directorio sin necesidad de importarlas.
"""

import datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from farms.models import Animal, AnimalBatch, Crop, Farm, Plot, Ration, Silage


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


@pytest.fixture
def plot(farm):
    """Parcela base sobre la que colgar cultivos."""
    return Plot.objects.create(
        farm=farm,
        name="Leira do Souto",
        code="P-001",
        area_ha=Decimal("2.5000"),
    )


@pytest.fixture
def crop(plot):
    """Campaña de maíz sobre la parcela base."""
    return Crop.objects.create(
        plot=plot,
        species=Crop.Species.MAIZE,
        season=2025,
        sowing_date=datetime.date(2025, 5, 1),
        harvest_date=datetime.date(2025, 9, 20),
    )


@pytest.fixture
def silage(crop):
    """Silo procedente de la campaña base."""
    return Silage.objects.create(
        crop=crop,
        code="S-2025-01",
        sealed_date=datetime.date(2025, 9, 22),
    )


@pytest.fixture
def batch(farm):
    """Lote de animales de la granja base."""
    return AnimalBatch.objects.create(farm=farm, name="Alta producción")


@pytest.fixture
def ration(farm):
    """Ración formulada para la granja base."""
    return Ration.objects.create(
        farm=farm,
        name="Lactación alta",
        formulated_on=datetime.date(2026, 1, 15),
    )
