"""Adaptador del laboratorio de análisis de leche.

La entrega es una tabla ancha: un bloque que declara qué se ha medido y otro con
una muestra por fila y un analito por columna. Es la forma contraria a la del
laboratorio de forrajes, que cuelga los resultados de cada muestra, así que aquí
hay que deshacer el pivote para llegar al grano del modelo: un valor por analito
y muestra. Trae su propio catálogo, porque quien analiza es quien sabe qué mide.
"""

from typing import ClassVar

from farms.models import SourceSystem
from farms.services.adapters.base import AdapterError, parse_decimal, parse_dmy_date
from farms.services.canonical import (
    AnalyteRecord,
    CanonicalBatch,
    MilkResultRecord,
    MilkSampleRecord,
    Reject,
)

TITLE = "INFORME DE ANALITICA DE LECHE"
LABORATORY_KEY = "LABORATORIO"
FARM_KEY = "EXPLOTACION"
SEPARATOR = ";"
DATE_SEPARATOR = "."
DECIMAL_SEPARATOR = ","
MISSING = ""  # celda vacía: el laboratorio no determinó ese parámetro
HEADER_LINES = 3  # el título y las dos claves de cabecera

SECTION_ANALYTES = "#ANALITOS"
SECTION_RESULTS = "#RESULTADOS"

# Encabezados fijos de cada bloque; en el de resultados, detrás de estos dos van
# tantas columnas como analitos declare el informe.
ANALYTE_COLUMNS = ("codigo", "nombre", "unidad")
RESULT_COLUMNS = ("lote", "fecha")

# Códigos del laboratorio traducidos al vocabulario del modelo.
MILK_ANALYTE_CODES = {
    "CLA": "cla",
    "ALN": "omega3",
    "BCAR": "beta_caroteno",
    "TOCO": "alfa_tocoferol",
}


class MilkLabAdapter:
    """Traduce un informe de analítica de leche al modelo canónico."""

    source: ClassVar[SourceSystem] = SourceSystem.MILK_LAB

    def parse(self, payload: str) -> CanonicalBatch:
        """Lee la cabecera, el catálogo y la tabla de resultados.

        Lo que rompe la estructura —título, claves de cabecera, secciones o
        encabezados— invalida la entrega entera. Una fila que no cuadra con las
        columnas declaradas se aparta con su motivo y su número de línea.
        """
        lines = payload.splitlines()
        farm_code, laboratory = self._parse_header(lines)
        batch = CanonicalBatch(source=self.source)
        index = self._parse_analytes(lines, HEADER_LINES, batch)
        self._parse_results(lines, index, farm_code, laboratory, batch)
        return batch

    def _parse_header(self, lines: list[str]) -> tuple[str, str]:
        """Comprueba que el documento es un informe de este laboratorio."""
        if not lines or lines[0].strip() != TITLE:
            raise AdapterError(f"[{self.source}] el informe no empieza por {TITLE!r}")
        values: dict[str, str] = {}
        for offset, key in enumerate((LABORATORY_KEY, FARM_KEY), start=1):
            cells = lines[offset].split(SEPARATOR) if offset < len(lines) else []
            if len(cells) != 2 or cells[0].strip() != key:
                raise AdapterError(f"[{self.source}] falta la clave {key!r} en la cabecera")
            values[key] = cells[1].strip()
        return values[FARM_KEY], values[LABORATORY_KEY]

    def _parse_analytes(self, lines: list[str], index: int, batch: CanonicalBatch) -> int:
        """Catálogo del informe; devuelve la línea donde empiezan los resultados."""
        self._expect(lines, index, SECTION_ANALYTES)
        self._expect(lines, index + 1, SEPARATOR.join(ANALYTE_COLUMNS))
        index += 2
        while index < len(lines) and lines[index].strip() != SECTION_RESULTS:
            cells = [cell.strip() for cell in lines[index].split(SEPARATOR)]
            if len(cells) != len(ANALYTE_COLUMNS):
                batch.rejects.append(
                    Reject(
                        line_number=index + 1,
                        raw=lines[index],
                        reason=f"el analito trae {len(cells)} celdas y se esperaban 3",
                    )
                )
            else:
                code, name, unit = cells
                batch.analytes.append(
                    AnalyteRecord(code=self._model_code(code), name=name, unit=unit)
                )
            index += 1
        return index

    def _parse_results(
        self,
        lines: list[str],
        index: int,
        farm_code: str,
        laboratory: str,
        batch: CanonicalBatch,
    ) -> None:
        """Deshace el pivote: cada celda de la tabla es un resultado del modelo."""
        self._expect(lines, index, SECTION_RESULTS)
        codes = self._result_codes(lines, index + 1)
        for number, raw in enumerate(lines[index + 2 :], start=index + 3):
            try:
                self._parse_row(raw, codes, farm_code, laboratory, batch)
            except ValueError as exc:
                batch.rejects.append(Reject(line_number=number, raw=raw, reason=str(exc)))

    def _result_codes(self, lines: list[str], index: int) -> list[str]:
        """Analitos que declara la fila de encabezados, en su orden de columna."""
        header = lines[index] if index < len(lines) else ""
        cells = [cell.strip() for cell in header.split(SEPARATOR)]
        fixed, declared = cells[: len(RESULT_COLUMNS)], cells[len(RESULT_COLUMNS) :]
        if tuple(fixed) != RESULT_COLUMNS or not declared:
            raise AdapterError(f"[{self.source}] encabezados de resultados inesperados: {cells}")
        return [self._model_code(cell) for cell in declared]

    def _parse_row(
        self,
        raw: str,
        codes: list[str],
        farm_code: str,
        laboratory: str,
        batch: CanonicalBatch,
    ) -> None:
        """Interpreta una muestra entera: su cabecera y una columna por analito.

        Los valores se construyen antes de añadir nada, para que una celda mala
        invalide la muestra completa: media muestra cargada es peor que ninguna,
        porque no se distingue de una que el laboratorio no determinó.
        """
        cells = raw.split(SEPARATOR)
        expected = len(RESULT_COLUMNS) + len(codes)
        if len(cells) != expected:
            raise ValueError(f"la fila trae {len(cells)} celdas y se esperaban {expected}")
        batch_name = cells[0].strip()
        if not batch_name:
            raise ValueError("lote sin nombre")
        sampled_on = parse_dmy_date(cells[1], DATE_SEPARATOR)
        results = [
            MilkResultRecord(
                farm_code=farm_code,
                batch_name=batch_name,
                date=sampled_on,
                analyte_code=code,
                value=parse_decimal(cell, decimal_separator=DECIMAL_SEPARATOR),
            )
            for code, cell in zip(codes, cells[len(RESULT_COLUMNS) :], strict=True)
            if cell.strip() != MISSING
        ]
        batch.milk_samples.append(
            MilkSampleRecord(
                farm_code=farm_code,
                batch_name=batch_name,
                date=sampled_on,
                laboratory=laboratory,
            )
        )
        batch.milk_results.extend(results)

    def _expect(self, lines: list[str], index: int, literal: str) -> None:
        """Exige una línea concreta: marcador de sección o fila de encabezados."""
        if index >= len(lines) or lines[index].strip() != literal:
            raise AdapterError(f"[{self.source}] se esperaba {literal!r} en la línea {index + 1}")

    def _model_code(self, raw: str) -> str:
        """Traduce el código de analito del laboratorio al del modelo.

        Un código desconocido aborta la entrega en vez de apartar una fila. Aquí
        el analito es una **columna**, no un registro: si no se sabe qué mide,
        no se sabe qué contiene ninguna de las celdas que hay debajo.
        """
        if raw not in MILK_ANALYTE_CODES:
            raise AdapterError(f"[{self.source}] parámetro desconocido: {raw!r}")
        return MILK_ANALYTE_CODES[raw]
