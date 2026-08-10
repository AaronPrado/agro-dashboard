"""Modelo canónico de la ingesta: la forma única en la que entra todo dato.

Cada fuente tiene su formato, su codificación de nulos y su idea de qué es una
fecha; lo que sale de cualquier adaptador es siempre este mismo conjunto de
dataclasses. Aquí no hay ORM: los hechos se refieren entre sí por *clave
natural* —el código de la explotación, el crotal del animal, el código del
silo—, nunca por clave primaria, porque una fuente externa no conoce los
identificadores internos de esta base de datos.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from farms.models import SourceSystem


@dataclass(frozen=True, slots=True)
class FarmRegistration:
    """Explotación tal como la declara la fuente que la conoce."""

    code: str
    name: str
    municipality: str
    province: str


@dataclass(frozen=True, slots=True)
class AnimalRegistration:
    """Alta o estado de un animal según la fuente que lo declara."""

    farm_code: str
    ear_tag: str
    birth_date: date
    breed: str
    lactation_number: int
    last_calving_date: date | None
    culled_date: date | None


@dataclass(frozen=True, slots=True)
class ProductionReading:
    """Producción de un animal en un día. `liters` nulo = registrado sin lectura."""

    farm_code: str
    ear_tag: str
    date: date
    liters: Decimal | None


@dataclass(frozen=True, slots=True)
class MilkQualityRecord:
    """Control lechero individual: la analítica básica de un animal en una fecha."""

    farm_code: str
    ear_tag: str
    date: date
    fat_pct: Decimal | None
    protein_pct: Decimal | None
    somatic_cell_count: int | None


@dataclass(frozen=True, slots=True)
class Reject:
    """Registro que la fuente entregó y el adaptador no supo interpretar.

    Se conserva el contenido original: un motivo sin la fila no sirve para
    corregir el fichero de origen.
    """

    line_number: int
    raw: str
    reason: str


@dataclass(frozen=True, slots=True)
class PlotRecord:
    """Parcela de cultivo tal como la declara quien lleva el cuaderno."""

    farm_code: str
    code: str
    name: str
    area_ha: Decimal


@dataclass(frozen=True, slots=True)
class CropRecord:
    """Campaña sobre una parcela. La identifican parcela, año y especie."""

    farm_code: str
    plot_code: str
    species: str
    season: int
    sowing_date: date | None
    harvest_date: date | None


@dataclass(frozen=True, slots=True)
class SilageRecord:
    """Silo conservado. Cuelga de una campaña, que hay que identificar entera."""

    farm_code: str
    plot_code: str
    season: int
    species: str
    code: str
    sealed_date: date | None
    opened_date: date | None


@dataclass(frozen=True, slots=True)
class RawMaterialRecord:
    """Materia prima comprada. Es catálogo común, no de una explotación."""

    name: str
    category: str


@dataclass(frozen=True, slots=True)
class RationRecord:
    """Ración formulada. La identifican explotación, nombre y fecha."""

    farm_code: str
    name: str
    formulated_on: date


@dataclass(frozen=True, slots=True)
class RationIngredientRecord:
    """Componente de una ración, referido a ella por su clave natural entera.

    `silage_code` y `raw_material_name` son excluyentes, igual que en el modelo:
    el componente es un silo propio o algo comprado, nunca las dos cosas.
    """

    farm_code: str
    ration_name: str
    formulated_on: date
    silage_code: str | None
    raw_material_name: str | None
    dry_matter_kg: Decimal


@dataclass(slots=True)
class CanonicalBatch:
    """Lo que entrega un adaptador tras normalizar una entrega de su fuente.

    Es un contenedor ancho a propósito: cada fuente rellena solo las listas que
    conoce y deja el resto vacías. El cargador recibe siempre esta misma forma y
    no ramifica por origen — esa es la diferencia entre integrar y acumular.
    """

    source: SourceSystem
    farms: list[FarmRegistration] = field(default_factory=list)
    animals: list[AnimalRegistration] = field(default_factory=list)
    production: list[ProductionReading] = field(default_factory=list)
    quality: list[MilkQualityRecord] = field(default_factory=list)
    plots: list[PlotRecord] = field(default_factory=list)
    crops: list[CropRecord] = field(default_factory=list)
    silages: list[SilageRecord] = field(default_factory=list)
    raw_materials: list[RawMaterialRecord] = field(default_factory=list)
    rations: list[RationRecord] = field(default_factory=list)
    ration_ingredients: list[RationIngredientRecord] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)
