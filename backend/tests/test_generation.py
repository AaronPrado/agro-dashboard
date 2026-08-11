"""Tests del generador: reproducibilidad, estructura, límites y casos borde.

El generador es puro (no toca la base de datos): trabaja sobre dataclasses.
"""

import datetime
import random
from decimal import Decimal

import pytest

from farms.services.agronomy import FEEDING_GROUPS
from farms.services.generation import GenerationParams, generate
from farms.services.milk_quality import MILK_ANALYTE_RANGES, MILK_ANALYTES

START = datetime.date(2024, 1, 1)
END = datetime.date(2024, 12, 31)

DRY_BATCH = next(group.batch_name for group in FEEDING_GROUPS if group.max_days_in_milk is None)


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


def test_kilos_dentro_de_los_limites_del_modelo(poblacion):
    """El generador emite kilos, la unidad que mide la báscula del ordeño.

    El tope es deliberadamente conservador: tras convertir a litros en el
    adaptador sigue cabiendo en el DecimalField(max_digits=5, decimal_places=2).
    """
    farms, _ = poblacion
    for farm in farms:
        for animal in farm.animals:
            for daily_yield in animal.daily_yields:
                if daily_yield.kg is not None:
                    assert Decimal("0") <= daily_yield.kg <= Decimal("999.99")
                    assert daily_yield.kg.as_tuple().exponent == -2


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


def test_produccion_dentro_de_la_ventana_y_antes_de_la_baja(poblacion):
    """No hay registros fuera del rango pedido ni después de la baja del animal."""
    farms, params = poblacion
    for farm in farms:
        for animal in farm.animals:
            for daily_yield in animal.daily_yields:
                assert params.start <= daily_yield.date <= params.end
                if animal.culled_date is not None:
                    assert daily_yield.date <= animal.culled_date


def test_incluye_casos_borde(poblacion):
    """La población contiene nulos (lecturas ausentes) y bajas a mitad de serie."""
    farms, _ = poblacion
    daily_yields = [m for farm in farms for animal in farm.animals for m in animal.daily_yields]

    assert any(m.kg is None for m in daily_yields)
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
            for daily_yield in animal.daily_yields:
                if daily_yield.kg is None:
                    continue
                dim = (daily_yield.date - animal.last_calving_date).days
                if 30 <= dim <= 120:
                    inicio.append(daily_yield.kg)
                elif 250 <= dim <= 305:
                    final.append(daily_yield.kg)

    assert inicio and final
    assert sum(inicio) / len(inicio) > sum(final) / len(final)


# --- Muestras de leche del lote ---


def test_se_generan_muestras_de_leche_de_lote(poblacion):
    """Guarda del resto: sin muestras, los tests de abajo pasarían en vacío."""
    farms, _ = poblacion

    assert all(farm.milk_samples for farm in farms)


def test_el_lote_de_secas_no_se_muestrea(poblacion):
    """Una vaca seca no da leche, así que su lote no tiene qué muestrear."""
    farms, _ = poblacion

    assert all(sample.batch_name != DRY_BATCH for farm in farms for sample in farm.milk_samples)


def test_toda_muestra_pertenece_a_un_lote_con_animales_ese_dia(poblacion):
    """No se muestrea un lote vacío: la serie prefiere el hueco al dato inventado."""
    farms, _ = poblacion
    for farm in farms:
        for sample in farm.milk_samples:
            assert any(
                membership.batch_name == sample.batch_name
                and membership.date_from <= sample.date
                and (membership.date_to is None or sample.date <= membership.date_to)
                for animal in farm.animals
                for membership in animal.memberships
            ), f"{sample.batch_name} sin animales el {sample.date}"


def test_no_hay_dos_muestras_del_mismo_lote_en_la_misma_fecha(poblacion):
    """El modelo lo impide con un unique; el generador no debe llegar a probarlo."""
    farms, _ = poblacion
    for farm in farms:
        claves = [(sample.batch_name, sample.date) for sample in farm.milk_samples]

        assert len(claves) == len(set(claves))


def test_cada_muestra_trae_los_cuatro_analitos_dentro_de_rango(poblacion):
    farms, _ = poblacion
    codigos = {code for code, _, _ in MILK_ANALYTES}
    for farm in farms:
        for sample in farm.milk_samples:
            assert set(sample.results) == codigos
            for code, value in sample.results.items():
                low, high = MILK_ANALYTE_RANGES[code]
                assert low <= value <= high, f"{code} fuera de rango el {sample.date}"


def test_las_muestras_caen_dentro_de_la_ventana(poblacion):
    farms, params = poblacion
    for farm in farms:
        for sample in farm.milk_samples:
            assert params.start <= sample.date <= params.end


def test_las_muestras_comparten_rejilla_con_el_control_lechero(poblacion):
    """Compartir fechas es lo que hace comparables las dos analíticas."""
    farms, _ = poblacion
    for farm in farms:
        controles = {record.date for animal in farm.animals for record in animal.milk_records}
        muestras = {sample.date for sample in farm.milk_samples}

        assert muestras <= controles
