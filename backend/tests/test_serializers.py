"""Tests de los serializers de la API.

Se prueban en aislamiento, sin pasar por una vista: un serializer recibe una
instancia y produce el diccionario que acabará en el JSON. Aquí se fija el
contrato de la API (qué claves salen y con qué tipo), independientemente de
cómo se enruten los endpoints.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import Animal, Milking, MilkRecord
from farms.serializers import (
    AnimalSerializer,
    FarmSerializer,
    MilkingSerializer,
    MilkRecordSerializer,
)


@pytest.mark.django_db
def test_farm_serializer_expone_los_campos_acordados(farm):
    """El contrato de la granja es una lista blanca cerrada."""
    data = FarmSerializer(farm).data

    assert set(data) == {
        "id",
        "name",
        "code",
        "municipality",
        "province",
        "created_at",
    }
    assert data["code"] == "casa-grande"


@pytest.mark.django_db
def test_animal_serializer_aplana_la_granja_y_la_raza(animal):
    """Los datos de la relación viajan planos, no anidados."""
    data = AnimalSerializer(animal).data

    assert data["farm"] == animal.farm_id
    assert data["farm_name"] == "Casa Grande"
    # El valor estable sirve para filtrar; el rótulo, para pintar.
    assert data["breed"] == "holstein"
    assert data["breed_display"] == "Frisona"


@pytest.mark.django_db
def test_animal_sin_baja_esta_activo(animal):
    """`is_active` se deriva de la ausencia de fecha de baja."""
    data = AnimalSerializer(animal).data

    assert data["culled_date"] is None
    assert data["is_active"] is True


@pytest.mark.django_db
def test_animal_con_baja_no_esta_activo(farm):
    """Un animal dado de baja se reporta como inactivo."""
    culled = Animal.objects.create(
        farm=farm,
        ear_tag="ES0002",
        birth_date=datetime.date(2020, 1, 15),
        culled_date=datetime.date(2026, 2, 1),
    )

    data = AnimalSerializer(culled).data

    assert data["is_active"] is False


@pytest.mark.django_db
def test_milking_serializa_los_litros_como_cadena(animal):
    """DRF representa los `Decimal` como string para no perder exactitud."""
    milking = Milking.objects.create(
        animal=animal,
        date=datetime.date(2026, 5, 10),
        liters=Decimal("28.40"),
    )

    data = MilkingSerializer(milking).data

    assert data["liters"] == "28.40"
    assert data["date"] == "2026-05-10"


@pytest.mark.django_db
def test_milking_conserva_el_nulo_de_una_lectura_ausente(animal):
    """Un ordeño sin medir viaja como `null`, no como cero ni como cadena."""
    milking = Milking.objects.create(
        animal=animal,
        date=datetime.date(2026, 5, 11),
        liters=None,
    )

    data = MilkingSerializer(milking).data

    assert data["liters"] is None


@pytest.mark.django_db
def test_milking_expone_animal_y_granja_para_poder_agrupar(animal):
    """El ordeño arrastra el crotal y el identificador de granja."""
    milking = Milking.objects.create(
        animal=animal,
        date=datetime.date(2026, 5, 12),
        liters=Decimal("30.00"),
    )

    data = MilkingSerializer(milking).data

    assert data["animal"] == animal.id
    assert data["animal_ear_tag"] == "ES0001"
    assert data["farm"] == animal.farm_id


@pytest.mark.django_db
def test_milk_record_serializa_la_analitica_completa(animal):
    """El control lechero expone grasa, proteína y células somáticas."""
    record = MilkRecord.objects.create(
        animal=animal,
        date=datetime.date(2026, 4, 30),
        fat_pct=Decimal("3.70"),
        protein_pct=Decimal("3.10"),
        somatic_cell_count=145_000,
    )

    data = MilkRecordSerializer(record).data

    assert data["fat_pct"] == "3.70"
    assert data["protein_pct"] == "3.10"
    # El recuento es entero: no pasa por la representación decimal.
    assert data["somatic_cell_count"] == 145_000
    assert data["animal_ear_tag"] == "ES0001"
    assert data["farm"] == animal.farm_id


@pytest.mark.django_db
def test_milk_record_conserva_los_nulos_de_la_analitica(animal):
    """Un control sin analítica distingue "no medido" de cero."""
    record = MilkRecord.objects.create(animal=animal, date=datetime.date(2026, 3, 31))

    data = MilkRecordSerializer(record).data

    assert data["fat_pct"] is None
    assert data["protein_pct"] is None
    assert data["somatic_cell_count"] is None
