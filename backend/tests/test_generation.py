"""Tests del generador: reproducibilidad, estructura, límites y casos borde.

El generador es puro (no toca la base de datos): trabaja sobre dataclasses.
"""

import datetime
import random
from decimal import Decimal

import pytest

from farms.services.generation import GenerationParams, generate

START = datetime.date(2024, 1, 1)
END = datetime.date(2024, 12, 31)


def _params(farms=2, animals=10):
    return GenerationParams(farms=farms, animals_per_farm=animals, start=START, end=END)


@pytest.fixture
def poblacion():
    """Población amplia y determinista para comprobar límites y casos borde."""
    params = _params(farms=3, animals=40)
    return generate(random.Random(42), params), params


def test_reproducibilidad_misma_semilla_mismos_datos():
    """El criterio de hecho de la sesión: misma semilla ⇒ datos idénticos."""
    params = _params()
    assert generate(random.Random(7), params) == generate(random.Random(7), params)


def test_semillas_distintas_producen_datos_distintos():
    """Semillas distintas divergen (si no, la semilla no estaría teniendo efecto)."""
    params = _params()
    assert generate(random.Random(1), params) != generate(random.Random(2), params)


def test_estructura_respeta_los_parametros():
    """Se genera exactamente el número de granjas y animales pedido."""
    params = _params(farms=4, animals=15)
    farms = generate(random.Random(1), params)

    assert len(farms) == params.farms
    assert all(len(farm.animals) == params.animals_per_farm for farm in farms)


def test_distribucion_de_razas_sesgada_a_frisona(poblacion):
    """La Frisona domina la cabaña, como en el vacuno de leche gallego."""
    farms, _ = poblacion
    breeds = [animal.breed for farm in farms for animal in farm.animals]

    assert breeds.count("holstein") > len(breeds) / 2


def test_litros_dentro_de_los_limites_del_modelo(poblacion):
    """Ningún ordeño viola el DecimalField(max_digits=5, decimal_places=2)."""
    farms, _ = poblacion
    for farm in farms:
        for animal in farm.animals:
            for milking in animal.milkings:
                if milking.liters is not None:
                    assert Decimal("0") <= milking.liters <= Decimal("999.99")
                    assert milking.liters.as_tuple().exponent == -2


def test_analitica_dentro_de_los_limites_del_modelo(poblacion):
    """Grasa, proteína y células somáticas respetan los límites de sus campos."""
    farms, _ = poblacion
    for farm in farms:
        for animal in farm.animals:
            for record in animal.milk_records:
                if record.fat_pct is not None:
                    assert Decimal("0") <= record.fat_pct <= Decimal("99.99")
                if record.protein_pct is not None:
                    assert Decimal("0") <= record.protein_pct <= Decimal("99.99")
                if record.somatic_cell_count is not None:
                    assert record.somatic_cell_count > 0


def test_ordenos_dentro_de_la_ventana_y_antes_de_la_baja(poblacion):
    """No hay ordeños fuera del rango pedido ni después de la baja del animal."""
    farms, params = poblacion
    for farm in farms:
        for animal in farm.animals:
            for milking in animal.milkings:
                assert params.start <= milking.date <= params.end
                if animal.culled_date is not None:
                    assert milking.date <= animal.culled_date


def test_incluye_casos_borde(poblacion):
    """La población contiene nulos (lecturas ausentes) y bajas a mitad de serie."""
    farms, _ = poblacion
    milkings = [m for farm in farms for animal in farm.animals for m in animal.milkings]

    assert any(m.liters is None for m in milkings)
    assert any(a.culled_date is not None for farm in farms for a in farm.animals)


def test_produccion_sigue_la_curva_de_lactacion(poblacion):
    """La media de producción al inicio de la lactación supera a la del final."""
    farms, _ = poblacion
    inicio: list[Decimal] = []
    final: list[Decimal] = []
    for farm in farms:
        for animal in farm.animals:
            if animal.last_calving_date is None:
                continue
            for milking in animal.milkings:
                if milking.liters is None:
                    continue
                dim = (milking.date - animal.last_calving_date).days
                if 30 <= dim <= 120:
                    inicio.append(milking.liters)
                elif 250 <= dim <= 305:
                    final.append(milking.liters)

    assert inicio and final
    assert sum(inicio) / len(inicio) > sum(final) / len(final)
