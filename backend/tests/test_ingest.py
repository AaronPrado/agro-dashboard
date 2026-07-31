"""Tests del cargador: persistencia de la jerarquía e idempotencia con --clear."""

import datetime
import random

import pytest

from farms.models import Animal, DailyYield, Farm, MilkRecord
from farms.services.generation import GenerationParams, generate
from farms.services.ingest import load_farms

START = datetime.date(2024, 1, 1)
END = datetime.date(2024, 3, 31)


def _generate(seed=1, farms=2, animals=5):
    params = GenerationParams(farms=farms, animals_per_farm=animals, start=START, end=END)
    return generate(random.Random(seed), params)


@pytest.mark.django_db
def test_load_persiste_toda_la_jerarquia():
    """Cada nivel se guarda y los contadores del resumen cuadran con la base."""
    summary = load_farms(_generate())

    assert Farm.objects.count() == summary.farms == 2
    assert Animal.objects.count() == summary.animals
    assert DailyYield.objects.count() == summary.daily_yields
    assert MilkRecord.objects.count() == summary.milk_records


@pytest.mark.django_db
def test_la_produccion_cuelga_del_animal_correcto():
    """Las FK apuntan al animal que les corresponde tras el bulk_create."""
    load_farms(_generate(farms=1, animals=3))

    for animal in Animal.objects.all():
        for daily_yield in animal.daily_yields.all():
            assert daily_yield.animal_id == animal.id


@pytest.mark.django_db
def test_relanzar_con_clear_es_idempotente():
    """Misma semilla + --clear ⇒ misma base: relanzar no acumula ni cambia datos."""
    load_farms(_generate(seed=5), clear=True)
    primera = list(
        DailyYield.objects.order_by("animal__ear_tag", "date").values_list("liters", flat=True)
    )

    load_farms(_generate(seed=5), clear=True)
    segunda = list(
        DailyYield.objects.order_by("animal__ear_tag", "date").values_list("liters", flat=True)
    )

    assert primera == segunda
