"""Tests del adaptador del laboratorio NIR.

Cuarta y última fuente, y la única cuya forma no es plana: los resultados
cuelgan de la muestra. Las entregas se escriben como diccionarios y se serializan
en el propio test, para que se vea el documento que llegaría del laboratorio.
"""

import datetime
import json
from decimal import Decimal

import pytest

from farms.models import SourceSystem
from farms.services.adapters.base import AdapterError
from farms.services.adapters.nir_lab import NIRLabAdapter


def _row(parametro, nombre, unidad, valor):
    return {"parametro": parametro, "nombre": nombre, "unidad": unidad, "valor": valor}


def _sample(silo="S-2025-P01-M", fecha="2025-10-28", resultados=None):
    return {
        "silo": silo,
        "fecha": fecha,
        "resultados": resultados
        if resultados is not None
        else [_row("PB", "Proteína bruta", "% MS", 7.8)],
    }


def _feed(*muestras):
    return json.dumps(
        {
            "laboratorio": "Laboratorio de análisis de forrajes",
            "explotacion": "casa-grande",
            "muestras": list(muestras) or [_sample()],
        },
        ensure_ascii=False,
    )


@pytest.fixture
def adapter():
    return NIRLabAdapter()


def test_la_cabecera_del_informe_identifica_explotacion_y_laboratorio(adapter):
    """El informe se identifica solo, como el del núcleo de control."""
    batch = adapter.parse(_feed())

    analysis = batch.forage_analyses[0]
    assert analysis.farm_code == "casa-grande"
    assert analysis.laboratory == "Laboratorio de análisis de forrajes"
    assert analysis.silage_code == "S-2025-P01-M"
    assert analysis.date == datetime.date(2025, 10, 28)


def test_el_catalogo_de_analitos_lo_trae_el_propio_informe(adapter):
    """Quien mide es quien sabe qué mide y en qué unidad: no se codifica aquí."""
    batch = adapter.parse(_feed())

    analyte = batch.analytes[0]
    assert analyte.code == "pb"
    assert analyte.name == "Proteína bruta"
    assert analyte.unit == "% MS"


def test_el_analito_no_se_repite_aunque_aparezca_en_varias_muestras(adapter):
    """El catálogo se deduplica en el adaptador, no a base de escrituras."""
    batch = adapter.parse(_feed(_sample(silo="S-1"), _sample(silo="S-2")))

    assert len(batch.forage_analyses) == 2
    assert len(batch.analytes) == 1


def test_el_valor_conserva_lo_que_escribio_el_laboratorio(adapter):
    """JSON no tiene decimales: pasar por `str` evita el error del flotante."""
    batch = adapter.parse(_feed(_sample(resultados=[_row("PB", "Proteína", "% MS", 7.8)])))

    assert batch.analysis_results[0].value == Decimal("7.8")
    assert batch.analysis_results[0].value != Decimal(7.8)


def test_un_parametro_no_determinado_no_genera_resultado(adapter):
    """«No lo medimos» no es un valor, y el modelo lo dice: `value` no es nulable."""
    batch = adapter.parse(
        _feed(
            _sample(
                resultados=[
                    _row("PB", "Proteína bruta", "% MS", 12.4),
                    _row("ALM", "Almidón", "% MS", None),
                ]
            )
        )
    )

    assert len(batch.analysis_results) == 1
    assert batch.analysis_results[0].analyte_code == "pb"
    # El analito sí entra al catálogo: el laboratorio lo contempla aunque no lo mida.
    assert {analyte.code for analyte in batch.analytes} == {"pb", "almidon"}


def test_un_parametro_desconocido_rechaza_su_muestra(adapter):
    """El laboratorio puede añadir un parámetro que el modelo no contempla."""
    batch = adapter.parse(_feed(_sample(resultados=[_row("ADL", "Lignina", "% MS", 3.2)])))

    assert not batch.analysis_results
    assert len(batch.rejects) == 1
    assert "parámetro desconocido" in batch.rejects[0].reason


def test_el_mismo_parametro_en_dos_unidades_rechaza_la_muestra(adapter):
    """Conciliar unidades a ojo sería inventar una conversión."""
    batch = adapter.parse(
        _feed(
            _sample(silo="S-1", resultados=[_row("PB", "Proteína", "% MS", 12.4)]),
            _sample(silo="S-2", resultados=[_row("PB", "Proteína", "g/kg", 124.0)]),
        )
    )

    assert len(batch.rejects) == 1
    assert "unidades" in batch.rejects[0].reason


def test_una_muestra_rota_se_aparta_y_el_resto_entra(adapter):
    """El rechazo se numera por el orden de la muestra: en JSON no hay líneas."""
    rota = {"silo": "S-2", "fecha": "2025-13-45", "resultados": []}
    batch = adapter.parse(_feed(_sample(silo="S-1"), rota, _sample(silo="S-3")))

    assert len(batch.forage_analyses) == 2
    assert len(batch.rejects) == 1
    assert batch.rejects[0].line_number == 2


def test_un_json_ilegible_aborta_la_entrega(adapter):
    """Fallo estructural: no hay nada que rescatar de un documento roto."""
    with pytest.raises(AdapterError):
        adapter.parse("{esto no es json")


def test_un_informe_sin_sus_claves_aborta_la_entrega(adapter):
    """Sin explotación ni muestras, ningún resultado se puede anclar."""
    with pytest.raises(AdapterError):
        adapter.parse(json.dumps({"muestras": []}))


def test_el_lote_declara_de_que_fuente_viene(adapter):
    """La procedencia viaja con el dato desde el primer momento."""
    assert adapter.parse(_feed()).source == SourceSystem.NIR_LAB
