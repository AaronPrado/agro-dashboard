"""Adaptador del laboratorio de análisis NIR.

La entrega es un JSON con una cabecera de informe y una lista de muestras, cada
una con sus filas de resultado. Es la única fuente del proyecto cuya forma no es
plana: los resultados cuelgan de la muestra, no viven al mismo nivel. Trae
además el catálogo de lo que mide —código, nombre y unidad de cada parámetro—,
porque quien analiza es quien sabe qué está midiendo.
"""

import json
from decimal import Decimal, InvalidOperation
from typing import ClassVar

from farms.models import SourceSystem
from farms.services.adapters.base import AdapterError, parse_iso_date
from farms.services.canonical import (
    AnalysisResultRecord,
    AnalyteRecord,
    CanonicalBatch,
    ForageAnalysisRecord,
    Reject,
)

FARM_KEY = "explotacion"
LABORATORY_KEY = "laboratorio"
SAMPLES_KEY = "muestras"
SILAGE_KEY = "silo"
DATE_KEY = "fecha"
RESULTS_KEY = "resultados"
PARAMETER_KEY = "parametro"
NAME_KEY = "nombre"
UNIT_KEY = "unidad"
VALUE_KEY = "valor"

# Códigos de parámetro del laboratorio traducidos al vocabulario del modelo.
ANALYTE_CODES = {
    "MS": "ms",
    "PB": "pb",
    "FND": "fnd",
    "FAD": "fad",
    "ALM": "almidon",
    "CEN": "cenizas",
}


class NIRLabAdapter:
    """Traduce un informe de laboratorio de forrajes al modelo canónico."""

    source: ClassVar[SourceSystem] = SourceSystem.NIR_LAB

    def parse(self, payload: str) -> CanonicalBatch:
        """Lee el informe entero y devuelve catálogo, cabeceras y resultados.

        Un JSON ilegible o sin las claves del informe aborta la entrega. Una
        muestra que no se puede interpretar se aparta con su motivo, igual que
        una fila en las otras fuentes; como aquí no hay líneas, el rechazo se
        numera por el orden de la muestra dentro del informe.
        """
        document = self._parse_document(payload)
        farm_code = document[FARM_KEY]
        laboratory = document[LABORATORY_KEY]

        batch = CanonicalBatch(source=self.source)
        analytes: dict[str, AnalyteRecord] = {}
        for ordinal, sample in enumerate(document[SAMPLES_KEY], start=1):
            try:
                self._parse_sample(sample, farm_code, laboratory, batch, analytes)
            except (ValueError, TypeError, KeyError, InvalidOperation) as exc:
                batch.rejects.append(
                    Reject(
                        line_number=ordinal,
                        raw=json.dumps(sample, ensure_ascii=False, sort_keys=True),
                        reason=str(exc),
                    )
                )
        batch.analytes.extend(analytes.values())
        return batch

    def _parse_document(self, payload: str) -> dict:
        """Comprueba que el documento es un informe de este laboratorio."""
        try:
            document = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise AdapterError(f"[{self.source}] el informe no es un JSON válido: {exc}") from exc
        if not isinstance(document, dict):
            raise AdapterError(f"[{self.source}] el informe no es un objeto JSON")
        missing = [key for key in (FARM_KEY, LABORATORY_KEY, SAMPLES_KEY) if key not in document]
        if missing:
            raise AdapterError(f"[{self.source}] faltan claves del informe: {missing}")
        return document

    def _parse_sample(
        self,
        sample: dict,
        farm_code: str,
        laboratory: str,
        batch: CanonicalBatch,
        analytes: dict[str, AnalyteRecord],
    ) -> None:
        """Interpreta una muestra: su cabecera y las filas de resultado."""
        silage_code = sample[SILAGE_KEY]
        sampled_on = parse_iso_date(sample[DATE_KEY])
        batch.forage_analyses.append(
            ForageAnalysisRecord(
                farm_code=farm_code,
                silage_code=silage_code,
                date=sampled_on,
                laboratory=laboratory,
            )
        )
        for row in sample[RESULTS_KEY]:
            code = _analyte_code(row[PARAMETER_KEY])
            _register_analyte(analytes, code, row[NAME_KEY], row[UNIT_KEY])
            if row[VALUE_KEY] is None:
                continue  # parámetro no determinado: no hay resultado que guardar
            batch.analysis_results.append(
                AnalysisResultRecord(
                    farm_code=farm_code,
                    silage_code=silage_code,
                    date=sampled_on,
                    analyte_code=code,
                    value=_decimal(row[VALUE_KEY]),
                )
            )


def _analyte_code(raw: str) -> str:
    """Traduce el código de parámetro del laboratorio al del modelo."""
    if raw not in ANALYTE_CODES:
        raise ValueError(f"parámetro desconocido: {raw!r}")
    return ANALYTE_CODES[raw]


def _register_analyte(analytes: dict[str, AnalyteRecord], code: str, name: str, unit: str) -> None:
    """Añade el analito al catálogo del informe y vigila que la unidad no baile.

    Un mismo parámetro con dos unidades distintas dentro de un informe no se
    concilia a la brava: sin saber cuál es la buena, cualquier conversión sería
    inventada.
    """
    known = analytes.get(code)
    if known is not None and known.unit != unit:
        raise ValueError(f"el parámetro {code!r} llega en dos unidades: {known.unit!r} y {unit!r}")
    analytes.setdefault(code, AnalyteRecord(code=code, name=name, unit=unit))


def _decimal(value: object) -> Decimal:
    """Convierte un número de JSON a `Decimal` pasando por su representación.

    JSON no tiene decimales: lo que llega es un flotante binario, y construir un
    `Decimal` directamente desde él arrastra el error de representación
    (`Decimal(7.8)` no es `7.8`). Pasar por `str` conserva el número que escribió
    el laboratorio, que es el que hay que guardar.
    """
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        raise ValueError(f"valor no numérico: {value!r}")
    return Decimal(str(value))
