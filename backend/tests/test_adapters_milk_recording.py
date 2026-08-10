"""Tests del adaptador del núcleo de control lechero.

El cuerpo es de ancho fijo, así que las entregas de prueba se escriben columna a
columna: es la única forma de ver que el contrato con la fuente son posiciones y
no separadores. Un espacio de más desplaza un campo entero.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import Animal, SourceSystem
from farms.services.adapters.base import AdapterError
from farms.services.adapters.milk_recording import MilkRecordingAdapter

HEADER = [
    "CONTROL LECHERO OFICIAL",
    "EXPLOTACION: casa-grande",
    "NOMBRE     : Casa Grande",
    "CONCELLO   : Sarria",
    "PROVINCIA  : Lugo",
    "FECHA      : 20260201",
    "--",
]

# Anchos:  crotal 20 | nacim. 8 | raza 2 | lactación 2 | parto 8 | baja 8 |
#          control 1 | grasa 5 | proteína 5 | recuento 7   → 66 en total
CON_CONTROL = "ES 2211 0001 0001   20210301HO0220251104        S 3,70 3,100000068"
SIN_CONTROL = "ES 2211 0001 0002   20200714JE0120250903        N"
SIN_RECUENTO = "ES 2211 0001 0003   20190522PA0320251201        S 4,10 3,409999999"
CON_BAJA = "ES 2211 0001 0004   20180110XX042025080120260115S 3,90 3,200000120"
RAZA_DESCONOCIDA = "ES 2211 0001 0005   20210301ZZ0220251104        N"


def _feed(*rows: str) -> str:
    return "\n".join([*HEADER, *rows])


@pytest.fixture
def adapter():
    return MilkRecordingAdapter()


def test_la_cabecera_identifica_la_explotacion(adapter):
    """A diferencia del robot, esta fuente se identifica sola."""
    batch = adapter.parse(_feed(CON_CONTROL))

    farm = batch.farms[0]
    assert farm.code == "casa-grande"
    assert farm.name == "Casa Grande"
    assert farm.municipality == "Sarria"
    assert farm.province == "Lugo"


def test_el_censo_traduce_crotal_raza_y_fechas(adapter):
    """Cuatro traducciones en una sola línea de ancho fijo."""
    batch = adapter.parse(_feed(CON_CONTROL))

    animal = batch.animals[0]
    assert animal.ear_tag == "ES221100010001"
    assert animal.breed == Animal.Breed.HOLSTEIN
    assert animal.birth_date == datetime.date(2021, 3, 1)
    assert animal.lactation_number == 2
    assert animal.last_calving_date == datetime.date(2025, 11, 4)
    assert animal.culled_date is None


def test_la_fecha_del_control_viene_de_la_cabecera(adapter):
    """El hecho no lleva fecha propia: la comparte todo el informe."""
    batch = adapter.parse(_feed(CON_CONTROL))

    assert batch.quality[0].date == datetime.date(2026, 2, 1)


def test_el_recuento_llega_en_miles_y_se_normaliza(adapter):
    """La fuente cuenta en miles por mililitro; el modelo, en células."""
    batch = adapter.parse(_feed(CON_CONTROL))

    quality = batch.quality[0]
    assert quality.somatic_cell_count == 68_000
    assert quality.fat_pct == Decimal("3.70")
    assert quality.protein_pct == Decimal("3.10")


def test_el_centinela_de_no_medido_no_entra_como_medida(adapter):
    """9999999 es un número válido: sin traducirlo entrarían 9,9 millones."""
    batch = adapter.parse(_feed(SIN_RECUENTO))

    assert batch.quality[0].somatic_cell_count is None


def test_un_animal_sin_control_ese_mes_entra_al_censo_y_no_a_la_analitica(adapter):
    """El informe lista el rebaño entero, no solo lo medido."""
    batch = adapter.parse(_feed(SIN_CONTROL))

    assert len(batch.animals) == 1
    assert not batch.quality


def test_la_baja_viaja_en_el_informe_del_mes_en_que_ocurre(adapter):
    """El censo es también el registro de altas y bajas de la explotación."""
    batch = adapter.parse(_feed(CON_BAJA))

    assert batch.animals[0].culled_date == datetime.date(2026, 1, 15)


def test_una_raza_desconocida_se_rechaza(adapter):
    """Absorberla como «otra» escondería el día en que la fuente añade una raza."""
    batch = adapter.parse(_feed(RAZA_DESCONOCIDA))

    assert not batch.animals
    assert len(batch.rejects) == 1
    assert "raza" in batch.rejects[0].reason


def test_una_linea_corta_se_rechaza_y_el_resto_entra(adapter):
    """En ancho fijo una línea truncada no es un campo vacío: es basura."""
    batch = adapter.parse(_feed(CON_CONTROL, "ES 2211 0001 0006   2021", SIN_CONTROL))

    assert len(batch.animals) == 2
    assert len(batch.rejects) == 1
    assert batch.rejects[0].line_number == 9


def test_un_informe_sin_su_titulo_se_rechaza_entero(adapter):
    """Sin cabecera no hay explotación ni fecha: ninguna fila significa nada."""
    with pytest.raises(AdapterError):
        adapter.parse("LISTADO CUALQUIERA\nEXPLOTACION: casa-grande\n--\n")


def test_una_cabecera_incompleta_se_rechaza_entera(adapter):
    """Falta la fecha: cargar la analítica sin saber de cuándo es sería inventarla."""
    incompleta = "\n".join(
        [
            "CONTROL LECHERO OFICIAL",
            "EXPLOTACION: casa-grande",
            "NOMBRE     : Casa Grande",
            "CONCELLO   : Sarria",
            "PROVINCIA  : Lugo",
            "--",
        ]
    )

    with pytest.raises(AdapterError):
        adapter.parse(incompleta)


def test_el_lote_declara_de_que_fuente_viene(adapter):
    """La procedencia viaja con el dato desde el primer momento."""
    batch = adapter.parse(_feed(CON_CONTROL))

    assert batch.source == SourceSystem.MILK_RECORDING
