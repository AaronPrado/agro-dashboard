"""Tests de los modelos del dominio: representación, restricciones y relaciones."""

import pytest
from django.db import IntegrityError

from farms.models import Farm


@pytest.mark.django_db
def test_farm_str_incluye_nombre_y_codigo():
    """La etiqueta del admin identifica la granja sin ambigüedad."""
    farm = Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )

    assert str(farm) == "Casa Grande (casa-grande)"


@pytest.mark.django_db
def test_farm_code_es_unico():
    """El código identifica la granja en la API, así que no puede repetirse."""
    Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )

    with pytest.raises(IntegrityError):
        Farm.objects.create(
            name="Otra granja",
            code="casa-grande",
            municipality="Chantada",
            province="Lugo",
        )


@pytest.mark.django_db
def test_farm_ordenacion_por_defecto_alfabetica():
    """Meta.ordering garantiza un orden estable, requisito de la paginación."""
    Farm.objects.create(name="Zaragoza", code="z", municipality="A", province="Lugo")
    Farm.objects.create(name="Abegondo", code="a", municipality="B", province="A Coruña")

    assert [farm.name for farm in Farm.objects.all()] == ["Abegondo", "Zaragoza"]


@pytest.mark.django_db
def test_farm_created_at_se_rellena_sola():
    """auto_now_add sella el alta sin que el generador de datos tenga que pasarla."""
    farm = Farm.objects.create(
        name="Casa Grande", code="cg", municipality="Sarria", province="Lugo"
    )

    assert farm.created_at is not None
