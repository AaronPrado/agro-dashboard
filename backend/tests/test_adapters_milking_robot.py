"""Tests del adaptador del robot de ordeño.

Se le dan entregas escritas a mano, que es lo que permite el diseño de texto
crudo: cada caso es un fichero de tres líneas donde se ve exactamente qué separa
la forma de la fuente de la forma del modelo.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import SourceSystem
from farms.services.adapters.base import AdapterError
from farms.services.adapters.milking_robot import MilkingRobotAdapter, to_liters

HEADER = "crotal;fecha;hora;kg"
FARM_CODE = "casa-grande"


def _feed(*rows: str) -> str:
    """Monta una entrega con su cabecera y las filas dadas."""
    return "\n".join([HEADER, *rows])


@pytest.fixture
def adapter():
    """Adaptador atado a una explotación: el fichero no dice de quién es."""
    return MilkingRobotAdapter(farm_code=FARM_CODE)


def test_los_ordenos_del_dia_se_suman_y_se_convierten_a_litros(adapter):
    """El grano de la fuente es el ordeño; el del modelo, el día. Y kg → L."""
    batch = adapter.parse(
        _feed(
            "221100010001;10/02/2026;06:14;15,80",
            "221100010001;10/02/2026;17:42;12,60",
        )
    )

    reading = batch.production[0]
    assert len(batch.production) == 1
    assert reading.farm_code == FARM_CODE
    assert reading.ear_tag == "ES221100010001"
    assert reading.date == datetime.date(2026, 2, 10)
    # 28,40 kg / 1.03 = 27.57 L
    assert reading.liters == Decimal("27.57")


def test_el_crotal_llega_sin_codigo_de_pais_y_con_separadores(adapter):
    """La fuente escribe el crotal a su manera; el canónico es uno solo."""
    batch = adapter.parse(_feed("22 11 0001-0001;10/02/2026;06:14;15,80"))

    assert batch.production[0].ear_tag == "ES221100010001"


def test_un_dia_sin_ninguna_lectura_se_registra_sin_litros(adapter):
    """Hueco y nulo no son lo mismo: aquí hay fila, pero la báscula no midió."""
    batch = adapter.parse(_feed("221100010001;10/02/2026;06:14;"))

    assert batch.production[0].liters is None
    assert not batch.rejects


def test_un_dia_con_lectura_parcial_se_rechaza(adapter):
    """Sumar solo lo medido daría un total corto con aspecto de bueno."""
    batch = adapter.parse(
        _feed(
            "221100010001;10/02/2026;06:14;15,80",
            "221100010001;10/02/2026;17:42;",
        )
    )

    assert not batch.production
    assert len(batch.rejects) == 1
    assert "sin lectura" in batch.rejects[0].reason


def test_una_fila_mal_formada_se_rechaza_y_el_resto_entra(adapter):
    """Una fila rota no tumba la entrega: se aparta con su motivo y se sigue."""
    batch = adapter.parse(
        _feed(
            "221100010001;10/02/2026;06:14;15,80",
            "221100010002;10/02/2026;12,30",
            "221100010003;10/02/2026;06:20;18,10",
        )
    )

    assert len(batch.production) == 2
    assert len(batch.rejects) == 1
    reject = batch.rejects[0]
    assert reject.line_number == 3
    assert "campos" in reject.reason
    assert reject.raw == "221100010002;10/02/2026;12,30"


def test_una_fecha_imposible_se_rechaza(adapter):
    """El 31 de febrero pasa el formato y no existe: lo caza el parseo, no un regex."""
    batch = adapter.parse(_feed("221100010001;31/02/2026;06:14;15,80"))

    assert not batch.production
    assert len(batch.rejects) == 1


def test_una_cabecera_inesperada_aborta_la_entrega(adapter):
    """Fallo estructural: cargar medio fichero de origen desconocido es peor."""
    with pytest.raises(AdapterError):
        adapter.parse("crotal,fecha,kg\n221100010001,10/02/2026,15.80")


def test_el_lote_declara_de_que_fuente_viene(adapter):
    """La procedencia viaja con el dato desde el primer momento."""
    batch = adapter.parse(_feed("221100010001;10/02/2026;06:14;15,80"))

    assert batch.source == SourceSystem.MILKING_ROBOT


def test_to_liters_convierte_y_cuantiza_a_dos_decimales():
    """30,9 kg / 1.03 = 30,00 L exactos, con la escala del DecimalField."""
    assert to_liters(Decimal("30.9")) == Decimal("30.00")
    assert to_liters(Decimal("35.0")).as_tuple().exponent == -2
