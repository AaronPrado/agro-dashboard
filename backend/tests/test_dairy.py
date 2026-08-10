"""Tests del modelo biológico del dominio: curva de Wood y estacionalidad.

Son funciones puras (sin base de datos ni azar): entra un número, sale un número.
"""

import datetime

import pytest

from farms.services import dairy


def test_wood_yield_es_cero_fuera_de_la_lactacion():
    """En secado (fuera de [1, LACTATION_DAYS]) la vaca no produce."""
    assert dairy.wood_yield_kg(0) == 0.0
    assert dairy.wood_yield_kg(dairy.LACTATION_DAYS + 1) == 0.0


def test_wood_yield_tiene_forma_de_curva_de_lactacion():
    """Sube hasta el pico (~b/c días) y luego decae: la firma de la lactación."""
    peak = round(dairy.WOOD_B / dairy.WOOD_C)
    subida = dairy.wood_yield_kg(peak - 50)
    pico = dairy.wood_yield_kg(peak)
    bajada = dairy.wood_yield_kg(peak + 120)

    assert subida < pico
    assert bajada < pico
    # Con los parámetros de literatura, el pico de una Holstein ronda los 32 kg/día.
    assert 28 < pico < 36


def test_seasonal_factor_minimo_en_verano_y_pleno_en_invierno():
    """La producción cae en verano por estrés térmico y se recupera en invierno."""
    verano = datetime.date(2025, 8, 1)  # ~día 213, máximo calor
    invierno = datetime.date(2025, 1, 31)

    assert dairy.seasonal_factor(verano) == pytest.approx(1 - dairy.SEASONAL_TROUGH, abs=0.01)
    assert dairy.seasonal_factor(invierno) == pytest.approx(1.0, abs=0.01)


def test_seasonal_factor_acotado_todo_el_ano():
    """El multiplicador nunca se sale de [1 − trough, 1] en ningún mes."""
    for mes in range(1, 13):
        factor = dairy.seasonal_factor(datetime.date(2025, mes, 15))
        assert 1 - dairy.SEASONAL_TROUGH <= factor <= 1.0


def test_parity_factor_penaliza_a_las_primiparas():
    """Las primíparas rinden menos; a partir de la tercera lactación se estabiliza."""
    assert dairy.parity_factor(1) < dairy.parity_factor(2) < dairy.parity_factor(3)
    assert dairy.parity_factor(5) == dairy.parity_factor(3)
