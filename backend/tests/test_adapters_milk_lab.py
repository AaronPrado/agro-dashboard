"""Tests del adaptador del laboratorio de análisis de leche.

Quinta fuente, y la única con forma de tabla ancha: un analito por columna. Lo
que se comprueba aquí es sobre todo el despivote y dónde está la frontera entre
apartar una fila y abortar la entrega, que en esta fuente no cae donde en el NIR.
"""

import datetime
import random
from decimal import Decimal

import pytest

from farms.models import SourceSystem
from farms.services.adapters.base import AdapterError
from farms.services.adapters.milk_lab import (
    ANALYTE_COLUMNS,
    FARM_KEY,
    LABORATORY_KEY,
    RESULT_COLUMNS,
    SECTION_ANALYTES,
    SECTION_RESULTS,
    SEPARATOR,
    TITLE,
    MilkLabAdapter,
)
from farms.services.feeds import milk_lab_feed
from farms.services.generation import GenerationParams, generate

LAB = "Laboratorio de análisis de leche"
FARM = "casa-grande"

ANALITOS = (
    ("CLA", "Ácido linoleico conjugado (c9,t11)", "% de AG totales"),
    ("BCAR", "β-caroteno", "µg/g de grasa"),
)


def _row(lote="Alta producción", fecha="01.03.2026", valores=("1,23", "4,50")):
    return SEPARATOR.join((lote, fecha, *valores))


def _feed(*filas, analitos=ANALITOS, titulo=TITLE, cabecera=None, con_resultados=True):
    """Informe completo: cabecera, catálogo declarado y tabla de resultados."""
    lineas = [
        titulo,
        *(
            cabecera
            if cabecera is not None
            else [
                f"{LABORATORY_KEY}{SEPARATOR}{LAB}",
                f"{FARM_KEY}{SEPARATOR}{FARM}",
            ]
        ),
        SECTION_ANALYTES,
        SEPARATOR.join(ANALYTE_COLUMNS),
        *(SEPARATOR.join(analito) for analito in analitos),
    ]
    if con_resultados:
        lineas += [
            SECTION_RESULTS,
            SEPARATOR.join((*RESULT_COLUMNS, *(codigo for codigo, _, _ in analitos))),
            *(filas or (_row(),)),
        ]
    return "\n".join(lineas)


@pytest.fixture
def adapter():
    return MilkLabAdapter()


# --- Lo que el informe declara ---


def test_la_cabecera_del_informe_identifica_explotacion_y_laboratorio(adapter):
    batch = adapter.parse(_feed())

    sample = batch.milk_samples[0]
    assert sample.farm_code == FARM
    assert sample.laboratory == LAB
    assert sample.batch_name == "Alta producción"
    assert sample.date == datetime.date(2026, 3, 1)


def test_el_catalogo_de_analitos_lo_trae_el_propio_informe(adapter):
    """Quien mide es quien sabe qué mide: los códigos del modelo salen del mapeo."""
    batch = adapter.parse(_feed())

    assert [analyte.code for analyte in batch.analytes] == ["cla", "beta_caroteno"]
    assert batch.analytes[0].name == "Ácido linoleico conjugado (c9,t11)"
    assert batch.analytes[1].unit == "µg/g de grasa"


# --- El despivote ---


def test_la_tabla_ancha_se_despivota_en_un_resultado_por_analito(adapter):
    """Una fila de la fuente son tantos hechos del modelo como analitos mida."""
    batch = adapter.parse(_feed())

    assert len(batch.milk_samples) == 1
    assert len(batch.milk_results) == 2
    assert {result.analyte_code for result in batch.milk_results} == {"cla", "beta_caroteno"}


def test_los_resultados_apuntan_a_su_muestra_por_clave_natural(adapter):
    """Explotación, lote y fecha: la fuente no conoce las claves primarias."""
    batch = adapter.parse(_feed())

    sample = batch.milk_samples[0]
    for result in batch.milk_results:
        assert (result.farm_code, result.batch_name, result.date) == (
            sample.farm_code,
            sample.batch_name,
            sample.date,
        )


def test_una_celda_vacia_no_genera_resultado(adapter):
    """La celda en blanco es «no determinado», y eso no es un valor."""
    batch = adapter.parse(_feed(_row(valores=("1,23", ""))))

    assert len(batch.milk_samples) == 1
    assert [result.analyte_code for result in batch.milk_results] == ["cla"]


def test_el_valor_conserva_la_coma_decimal_de_la_fuente(adapter):
    batch = adapter.parse(_feed(_row(valores=("1,23", "4,50"))))

    assert batch.milk_results[0].value == Decimal("1.23")


def test_varias_muestras_entran_como_filas_independientes(adapter):
    batch = adapter.parse(
        _feed(
            _row(lote="Alta producción", fecha="01.03.2026"),
            _row(lote="Baja producción", fecha="01.03.2026"),
        )
    )

    assert len(batch.milk_samples) == 2
    assert len(batch.milk_results) == 4


# --- Fila apartada frente a entrega abortada ---


def test_una_fila_con_celdas_de_menos_se_aparta_con_su_linea(adapter):
    """Sin recuento de columnas, los valores se leerían corridos una posición."""
    batch = adapter.parse(_feed(_row(valores=("1,23",))))

    assert not batch.milk_samples
    assert len(batch.rejects) == 1
    assert batch.rejects[0].line_number == 10
    assert "celdas" in batch.rejects[0].reason


def test_un_valor_no_numerico_no_deja_media_muestra_cargada(adapter):
    """La fila es atómica: media muestra no se distingue de una no determinada."""
    batch = adapter.parse(_feed(_row(valores=("no es un número", "4,50"))))

    assert not batch.milk_samples
    assert not batch.milk_results
    assert len(batch.rejects) == 1


def test_un_lote_sin_nombre_se_aparta(adapter):
    batch = adapter.parse(_feed(_row(lote="")))

    assert not batch.milk_samples
    assert "lote sin nombre" in batch.rejects[0].reason


def test_una_fecha_ilegible_aparta_la_fila(adapter):
    batch = adapter.parse(_feed(_row(fecha="45.13.2026")))

    assert not batch.milk_samples
    assert len(batch.rejects) == 1


def test_el_resto_de_filas_entra_aunque_una_se_rechace(adapter):
    """Apartar es apartar una fila, no la entrega."""
    batch = adapter.parse(
        _feed(
            _row(lote="Alta producción"),
            _row(lote="Baja producción", fecha="99.99.9999"),
            _row(lote="Secas"),
        )
    )

    assert [sample.batch_name for sample in batch.milk_samples] == ["Alta producción", "Secas"]
    assert len(batch.rejects) == 1
    assert batch.rejects[0].line_number == 11


# --- Fallos estructurales ---


def test_un_analito_desconocido_aborta_la_entrega_entera(adapter):
    """Aquí el analito es una columna, no una fila.

    En el informe del laboratorio de forrajes un parámetro desconocido rechaza su
    muestra y las demás entran. En una tabla ancha no se sabe qué contiene
    ninguna de las celdas que hay debajo de esa columna, así que no hay nada que
    rescatar.
    """
    with pytest.raises(AdapterError, match="parámetro desconocido"):
        adapter.parse(_feed(analitos=(("ADL", "Lignina", "% MS"),)))


def test_un_informe_sin_titulo_aborta_la_entrega(adapter):
    with pytest.raises(AdapterError):
        adapter.parse(_feed(titulo="OTRA COSA"))


def test_un_informe_sin_las_claves_de_cabecera_aborta_la_entrega(adapter):
    cabecera = [f"LABORATORIO{SEPARATOR}{LAB}", f"CONCELLO{SEPARATOR}Sarria"]

    with pytest.raises(AdapterError, match="cabecera"):
        adapter.parse(_feed(cabecera=cabecera))


def test_un_informe_sin_tabla_de_resultados_aborta_la_entrega(adapter):
    with pytest.raises(AdapterError, match=SECTION_RESULTS):
        adapter.parse(_feed(con_resultados=False))


def test_una_tabla_que_no_declara_ningun_analito_aborta_la_entrega(adapter):
    """Sin columnas de valor no hay analítica, solo una lista de fechas."""
    with pytest.raises(AdapterError, match="encabezados"):
        adapter.parse(_feed(analitos=()))


def test_el_lote_declara_de_que_fuente_viene(adapter):
    """La procedencia viaja con el dato desde el primer momento."""
    assert adapter.parse(_feed()).source == SourceSystem.MILK_LAB


# --- El par emisor/adaptador ---


def test_lo_que_emite_el_mock_lo_entiende_el_adaptador(adapter):
    """Emisor y adaptador son un solo contrato y se comprueban juntos.

    Es lo que caza una divergencia de separador o de formato de fecha, que no se
    ve leyendo ninguno de los dos por separado.
    """
    params = GenerationParams(
        farms=1,
        animals_per_farm=8,
        start=datetime.date(2024, 1, 1),
        end=datetime.date(2024, 12, 31),
    )
    farm = generate(random.Random(42), params)[0]
    assert farm.milk_samples

    batch = adapter.parse(milk_lab_feed(farm))

    assert not batch.rejects
    assert len(batch.milk_samples) == len(farm.milk_samples)
    assert len(batch.milk_results) == sum(len(sample.results) for sample in farm.milk_samples)
