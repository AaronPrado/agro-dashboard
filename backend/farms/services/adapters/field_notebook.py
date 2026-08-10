"""Adaptador del cuaderno de campo.

La entrega es la exportación plana de un cuaderno llevado en hoja de cálculo:
secciones entre corchetes, una fila de encabezados por sección y filas separadas
por tabulador. Aporta la base territorial de la explotación —parcelas, campañas
y los silos que salen de ellas— y escribe las fechas como las teclea quien lleva
el cuaderno, con el año en dos cifras.
"""

from datetime import date
from typing import ClassVar

from farms.models import Crop, SourceSystem
from farms.services.adapters.base import (
    AdapterError,
    parse_decimal,
    parse_short_year_date,
)
from farms.services.canonical import (
    CanonicalBatch,
    CropRecord,
    PlotRecord,
    Reject,
    SilageRecord,
)

TITLE = "CUADERNO DE CAMPO"
FARM_KEY = "EXPLOTACION"
HEADER_SEPARATOR = "--"
SEPARATOR = "\t"
MISSING = "-"

SECTION_PLOTS = "[PARCELAS]"
SECTION_CROPS = "[CULTIVOS]"
SECTION_SILAGES = "[SILOS]"

# Encabezados de cada sección: el contrato con la fuente, en un solo sitio, para
# que el emisor del mock y este adaptador no puedan divergir sin que se note.
COLUMNS = {
    SECTION_PLOTS: ("codigo", "nombre", "superficie_ha"),
    SECTION_CROPS: ("parcela", "especie", "campaña", "siembra", "cosecha"),
    SECTION_SILAGES: ("parcela", "campaña", "especie", "codigo", "cierre", "apertura"),
}

# Códigos de especie del cuaderno traducidos al vocabulario del modelo.
SPECIES_CODES = {
    "MAIZ": Crop.Species.MAIZE,
    "RAIGRAS": Crop.Species.ITALIAN_RYEGRASS,
    "PRADERA": Crop.Species.GRASS_MIX,
}


class FieldNotebookAdapter:
    """Traduce la exportación de un cuaderno de campo al modelo canónico."""

    source: ClassVar[SourceSystem] = SourceSystem.FIELD_NOTEBOOK

    def parse(self, payload: str) -> CanonicalBatch:
        """Recorre las secciones y traduce cada fila a su hecho canónico.

        Lo que rompe la estructura —título, cabecera, sección desconocida o
        encabezados que no cuadran— aborta la entrega: si el fichero ha cambiado
        de forma, ninguna fila es de fiar. Lo que rompe una fila la aparta.
        """
        lines = payload.splitlines()
        farm_code, start = self._parse_header(lines)

        batch = CanonicalBatch(source=self.source)
        section: str | None = None
        expect_columns = False
        for number, raw in enumerate(lines[start:], start=start + 1):
            if not raw.strip():
                continue
            if raw.startswith("["):
                section = self._open_section(raw)
                expect_columns = True
                continue
            if section is None:
                raise AdapterError(f"[{self.source}] fila fuera de toda sección: {raw!r}")
            if expect_columns:
                self._check_columns(section, raw)
                expect_columns = False
                continue
            try:
                self._parse_row(section, raw, farm_code, batch)
            except ValueError as exc:
                batch.rejects.append(Reject(line_number=number, raw=raw, reason=str(exc)))
        return batch

    def _parse_header(self, lines: list[str]) -> tuple[str, int]:
        """Título, explotación y separador; devuelve dónde empiezan las secciones."""
        if len(lines) < 3 or lines[0].strip() != TITLE:
            raise AdapterError(f"[{self.source}] no es una exportación de cuaderno de campo")
        key, _, value = lines[1].partition(SEPARATOR)
        if key.strip() != FARM_KEY or not value.strip():
            raise AdapterError(f"[{self.source}] la cabecera no declara la explotación")
        if lines[2].strip() != HEADER_SEPARATOR:
            raise AdapterError(f"[{self.source}] la cabecera no termina en {HEADER_SEPARATOR!r}")
        return value.strip(), 3

    def _open_section(self, raw: str) -> str:
        """Valida el marcador de sección y lo devuelve."""
        section = raw.strip()
        if section not in COLUMNS:
            raise AdapterError(f"[{self.source}] sección desconocida: {section!r}")
        return section

    def _check_columns(self, section: str, raw: str) -> None:
        """Comprueba que los encabezados son los esperados para esa sección."""
        found = tuple(raw.split(SEPARATOR))
        if found != COLUMNS[section]:
            raise AdapterError(f"[{self.source}] encabezados inesperados en {section}: {found}")

    def _parse_row(self, section: str, raw: str, farm_code: str, batch: CanonicalBatch) -> None:
        """Reparte la fila al hecho que le corresponde según su sección."""
        if section == SECTION_PLOTS:
            code, name, area = _fields(raw, 3)
            batch.plots.append(
                PlotRecord(
                    farm_code=farm_code,
                    code=code,
                    name=name,
                    area_ha=parse_decimal(area, decimal_separator=","),
                )
            )
        elif section == SECTION_CROPS:
            plot_code, species, season, sowing, harvest = _fields(raw, 5)
            batch.crops.append(
                CropRecord(
                    farm_code=farm_code,
                    plot_code=plot_code,
                    species=_species(species),
                    season=int(season),
                    sowing_date=_optional_date(sowing),
                    harvest_date=_optional_date(harvest),
                )
            )
        else:
            plot_code, season, species, code, sealed, opened = _fields(raw, 6)
            batch.silages.append(
                SilageRecord(
                    farm_code=farm_code,
                    plot_code=plot_code,
                    season=int(season),
                    species=_species(species),
                    code=code,
                    sealed_date=_optional_date(sealed),
                    opened_date=_optional_date(opened),
                )
            )


def _fields(raw: str, expected: int) -> list[str]:
    """Trocea una fila por el tabulador exigiendo el número de columnas."""
    parts = raw.split(SEPARATOR)
    if len(parts) != expected:
        raise ValueError(f"se esperaban {expected} columnas y hay {len(parts)}")
    return [part.strip() for part in parts]


def _species(code: str) -> str:
    """Traduce el código de especie del cuaderno al del modelo."""
    if code not in SPECIES_CODES:
        raise ValueError(f"especie desconocida: {code!r}")
    return SPECIES_CODES[code]


def _optional_date(raw: str) -> date | None:
    """Fecha corta que el cuaderno deja marcada cuando no aplica."""
    return None if raw == MISSING else parse_short_year_date(raw)
