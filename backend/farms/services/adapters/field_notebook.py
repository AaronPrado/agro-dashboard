"""Adaptador del cuaderno de campo.

La entrega es la exportación plana de un cuaderno llevado en hoja de cálculo:
secciones entre corchetes, una fila de encabezados por sección y filas separadas
por tabulador. Aporta la base territorial de la explotación —parcelas, campañas
y los silos que salen de ellas— y lo que se formula con ese forraje: las
raciones con sus ingredientes. Escribe las fechas como las teclea quien lleva el
cuaderno, con el año en dos cifras.
"""

from collections.abc import Callable
from datetime import date
from typing import ClassVar

from farms.models import Crop, RawMaterial, SourceSystem
from farms.services.adapters.base import (
    AdapterError,
    parse_decimal,
    parse_short_year_date,
)
from farms.services.canonical import (
    CanonicalBatch,
    CropRecord,
    PlotRecord,
    RationIngredientRecord,
    RationRecord,
    RawMaterialRecord,
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
SECTION_RAW_MATERIALS = "[MATERIAS_PRIMAS]"
SECTION_RATIONS = "[RACIONES]"
SECTION_INGREDIENTS = "[INGREDIENTES]"

# Encabezados de cada sección: el contrato con la fuente, en un solo sitio, para
# que el emisor del mock y este adaptador no puedan divergir sin que se note.
COLUMNS = {
    SECTION_PLOTS: ("codigo", "nombre", "superficie_ha"),
    SECTION_CROPS: ("parcela", "especie", "campaña", "siembra", "cosecha"),
    SECTION_SILAGES: ("parcela", "campaña", "especie", "codigo", "cierre", "apertura"),
    SECTION_RAW_MATERIALS: ("nombre", "categoria"),
    SECTION_RATIONS: ("nombre", "formulacion"),
    SECTION_INGREDIENTS: ("racion", "formulacion", "tipo", "referencia", "kg_ms"),
}

# Códigos de especie del cuaderno traducidos al vocabulario del modelo.
SPECIES_CODES = {
    "MAIZ": Crop.Species.MAIZE,
    "RAIGRAS": Crop.Species.ITALIAN_RYEGRASS,
    "PRADERA": Crop.Species.GRASS_MIX,
}

# Categorías de materia prima, con el mismo criterio que las especies.
CATEGORY_CODES = {
    "CONCENTRADO": RawMaterial.Category.CONCENTRATE,
    "FORRAJE": RawMaterial.Category.FORAGE,
    "SUBPRODUCTO": RawMaterial.Category.BYPRODUCT,
    "MINERAL": RawMaterial.Category.MINERAL,
    "OTRA": RawMaterial.Category.OTHER,
}

# Origen de un ingrediente. En el modelo son dos claves ajenas excluyentes; en el
# fichero son una columna de tipo y otra de referencia, que es como lo escribe
# quien formula: «de mi silo tal» o «del saco tal».
INGREDIENT_SILAGE = "SILO"
INGREDIENT_RAW_MATERIAL = "MATERIA_PRIMA"


class FieldNotebookAdapter:
    """Traduce la exportación de un cuaderno de campo al modelo canónico."""

    source: ClassVar[SourceSystem] = SourceSystem.FIELD_NOTEBOOK

    def __init__(self) -> None:
        self._parsers: dict[str, Callable[[list[str], str, CanonicalBatch], None]] = {
            SECTION_PLOTS: self._parse_plot,
            SECTION_CROPS: self._parse_crop,
            SECTION_SILAGES: self._parse_silage,
            SECTION_RAW_MATERIALS: self._parse_raw_material,
            SECTION_RATIONS: self._parse_ration,
            SECTION_INGREDIENTS: self._parse_ingredient,
        }

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
                fields = _fields(raw, len(COLUMNS[section]))
                self._parsers[section](fields, farm_code, batch)
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

    def _parse_plot(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        code, name, area = fields
        batch.plots.append(
            PlotRecord(
                farm_code=farm_code,
                code=code,
                name=name,
                area_ha=parse_decimal(area, decimal_separator=","),
            )
        )

    def _parse_crop(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        plot_code, species, season, sowing, harvest = fields
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

    def _parse_silage(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        plot_code, season, species, code, sealed, opened = fields
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

    def _parse_raw_material(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        """La materia prima es catálogo común: no lleva explotación."""
        name, category = fields
        if category not in CATEGORY_CODES:
            raise ValueError(f"categoría desconocida: {category!r}")
        batch.raw_materials.append(RawMaterialRecord(name=name, category=CATEGORY_CODES[category]))

    def _parse_ration(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        name, formulated_on = fields
        batch.rations.append(
            RationRecord(
                farm_code=farm_code,
                name=name,
                formulated_on=parse_short_year_date(formulated_on),
            )
        )

    def _parse_ingredient(self, fields: list[str], farm_code: str, batch: CanonicalBatch) -> None:
        """Un componente, con su origen en una columna en vez de en dos campos.

        El fichero dice de qué tipo es y a qué se refiere; el canónico lo separa
        en las dos referencias excluyentes que espera el modelo.
        """
        ration_name, formulated_on, kind, reference, kg = fields
        if kind not in (INGREDIENT_SILAGE, INGREDIENT_RAW_MATERIAL):
            raise ValueError(f"tipo de ingrediente desconocido: {kind!r}")
        batch.ration_ingredients.append(
            RationIngredientRecord(
                farm_code=farm_code,
                ration_name=ration_name,
                formulated_on=parse_short_year_date(formulated_on),
                silage_code=reference if kind == INGREDIENT_SILAGE else None,
                raw_material_name=reference if kind == INGREDIENT_RAW_MATERIAL else None,
                dry_matter_kg=parse_decimal(kg, decimal_separator=","),
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
