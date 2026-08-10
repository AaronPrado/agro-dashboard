"""Cargador: única capa que escribe en el ORM.

Recibe lotes canónicos, vengan de la fuente que vengan, y los persiste bajo una
carga registrada. No sabe qué formato tenía el fichero de origen ni ramifica por
procedencia: toda esa asimetría vive en los adaptadores y termina antes de aquí.
Los hechos se refieren a otros por clave natural —código de explotación, crotal—
y resolverlos a clave primaria es el trabajo de este módulo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Self

from django.db import transaction

from farms.models import (
    AnalysisResult,
    Animal,
    BatchRation,
    Crop,
    DailyYield,
    Farm,
    IngestionReject,
    IngestionRun,
    MilkRecord,
    Plot,
    Ration,
    RationIngredient,
    RawMaterial,
    Silage,
)
from farms.services.canonical import (
    AnimalRegistration,
    CanonicalBatch,
    CropRecord,
    FarmRegistration,
    MilkQualityRecord,
    PlotRecord,
    ProductionReading,
    RationIngredientRecord,
    RationRecord,
    RawMaterialRecord,
    Reject,
    SilageRecord,
)

BATCH_SIZE = 1000


class IngestionError(Exception):
    """Un hecho canónico apunta a algo que no existe en la base.

    Es un fallo de la entrega completa, no de una fila: si el censo no cuadra,
    cargar la parte que sí casa dejaría una base coherente en apariencia y
    silenciosamente incompleta.
    """


@dataclass(slots=True)
class LoadSummary:
    """Contadores de lo persistido, para el resumen del comando."""

    farms: int = 0
    animals: int = 0
    daily_yields: int = 0
    milk_records: int = 0
    rejected: int = 0
    plots: int = 0
    crops: int = 0
    silages: int = 0
    raw_materials: int = 0
    rations: int = 0
    ration_ingredients: int = 0

    @property
    def loaded(self) -> int:
        """Filas efectivamente escritas, sin contar las rechazadas."""
        return (
            self.farms
            + self.plots
            + self.crops
            + self.silages
            + self.raw_materials
            + self.rations
            + self.ration_ingredients
            + self.animals
            + self.daily_yields
            + self.milk_records
        )

    def __iadd__(self, other: Self) -> Self:
        """Acumula el resultado de varias entregas en un solo resumen."""
        self.farms += other.farms
        self.animals += other.animals
        self.daily_yields += other.daily_yields
        self.milk_records += other.milk_records
        self.rejected += other.rejected
        self.plots += other.plots
        self.crops += other.crops
        self.silages += other.silages
        self.raw_materials += other.raw_materials
        self.rations += other.rations
        self.ration_ingredients += other.ration_ingredients
        return self


def clear() -> None:
    """Vacía lo sembrado, en el orden que exigen las claves ajenas protegidas.

    `PROTECT` está puesto donde borrar destruiría historia —un silo usado en una
    ración, una ración asignada a un lote, el analito de un resultado, la carga
    que trajo una fila—, así que el borrado no puede ir de la raíz hacia abajo:
    hay que quitar antes a quien referencia. Cada línea de este cuerpo es una de
    esas protecciones, y por eso están comentadas una a una.
    """
    RationIngredient.objects.all().delete()  # protege Silage y RawMaterial
    BatchRation.objects.all().delete()  # protege Ration
    AnalysisResult.objects.all().delete()  # protege Analyte
    Farm.objects.all().delete()  # el CASCADE arrastra el resto del dominio
    RawMaterial.objects.all().delete()  # catálogo sembrado por el cuaderno
    IngestionRun.objects.all().delete()  # protegida por toda fila con procedencia


@transaction.atomic
def load(batch: CanonicalBatch, *, reference: str = "") -> tuple[IngestionRun, LoadSummary]:
    """Persiste un lote canónico bajo una carga nueva, todo o nada.

    La firma no menciona la fuente: viaja dentro del lote y solo sirve para
    etiquetar la carga. Que cuatro formatos distintos terminen en esta función
    sin un solo condicional por origen es el objetivo entero del diseño.
    """
    run = IngestionRun.objects.create(source=batch.source, reference=reference)
    summary = LoadSummary()

    _load_farms(batch.farms, run, summary)
    _load_plots(batch.plots, run, summary)
    _load_crops(batch.crops, run, summary)
    _load_silages(batch.silages, run, summary)
    _load_raw_materials(batch.raw_materials, summary)
    _load_rations(batch.rations, run, summary)
    _load_ration_ingredients(batch.ration_ingredients, run, summary)
    _load_animals(batch.animals, run, summary)
    _load_production(batch.production, run, summary)
    _load_quality(batch.quality, run, summary)
    _load_rejects(batch.rejects, run, summary)

    run.records_loaded = summary.loaded
    run.records_rejected = summary.rejected
    run.save(update_fields=["records_loaded", "records_rejected"])
    return run, summary


def _load_farms(
    registrations: Iterable[FarmRegistration], run: IngestionRun, summary: LoadSummary
) -> None:
    """Alta o actualización de explotaciones por su código."""
    for registration in registrations:
        Farm.objects.update_or_create(
            code=registration.code,
            defaults={
                "name": registration.name,
                "municipality": registration.municipality,
                "province": registration.province,
                "ingestion_run": run,
            },
        )
        summary.farms += 1


def _load_plots(records: Iterable[PlotRecord], run: IngestionRun, summary: LoadSummary) -> None:
    """Alta o actualización de parcelas, resueltas contra su explotación."""
    records = list(records)
    if not records:
        return
    farms = _farm_ids({record.farm_code for record in records})
    for record in records:
        Plot.objects.update_or_create(
            farm_id=farms[record.farm_code],
            code=record.code,
            defaults={
                "name": record.name,
                "area_ha": record.area_ha,
                "ingestion_run": run,
            },
        )
        summary.plots += 1


def _load_crops(records: Iterable[CropRecord], run: IngestionRun, summary: LoadSummary) -> None:
    """Alta o actualización de campañas: parcela, año y especie las identifican."""
    records = list(records)
    if not records:
        return
    plots = _plot_ids({(record.farm_code, record.plot_code) for record in records})
    for record in records:
        Crop.objects.update_or_create(
            plot_id=plots[(record.farm_code, record.plot_code)],
            season=record.season,
            species=record.species,
            defaults={
                "sowing_date": record.sowing_date,
                "harvest_date": record.harvest_date,
                "ingestion_run": run,
            },
        )
        summary.crops += 1


def _load_silages(records: Iterable[SilageRecord], run: IngestionRun, summary: LoadSummary) -> None:
    """Alta o actualización de silos, colgados de la campaña que los produjo."""
    records = list(records)
    if not records:
        return
    crops = _crop_ids({(r.farm_code, r.plot_code, r.season, r.species) for r in records})
    for record in records:
        Silage.objects.update_or_create(
            crop_id=crops[(record.farm_code, record.plot_code, record.season, record.species)],
            code=record.code,
            defaults={
                "sealed_date": record.sealed_date,
                "opened_date": record.opened_date,
                "ingestion_run": run,
            },
        )
        summary.silages += 1


def _load_raw_materials(records: Iterable[RawMaterialRecord], summary: LoadSummary) -> None:
    """Alta de materias primas en el catálogo común.

    No recibe la carga: `RawMaterial` es catálogo, no observación. Es la misma
    frontera que separa lo que alguien entrega de lo que la plataforma mantiene,
    y por eso este modelo no lleva procedencia.
    """
    for record in records:
        RawMaterial.objects.update_or_create(
            name=record.name,
            defaults={"category": record.category},
        )
        summary.raw_materials += 1


def _load_rations(records: Iterable[RationRecord], run: IngestionRun, summary: LoadSummary) -> None:
    """Alta o actualización de raciones: explotación, nombre y fecha las identifican.

    Una ración es una formulación cerrada, así que reformular es crear otra, no
    editar esta: por eso la fecha forma parte de la clave natural.
    """
    records = list(records)
    if not records:
        return
    farms = _farm_ids({record.farm_code for record in records})
    for record in records:
        Ration.objects.update_or_create(
            farm_id=farms[record.farm_code],
            name=record.name,
            formulated_on=record.formulated_on,
            defaults={"ingestion_run": run},
        )
        summary.rations += 1


def _load_ration_ingredients(
    records: Iterable[RationIngredientRecord], run: IngestionRun, summary: LoadSummary
) -> None:
    """Escribe los componentes de cada ración, resolviendo sus dos orígenes.

    El origen es excluyente en el modelo —silo propio o materia prima, nunca las
    dos cosas— y llega ya separado del adaptador, así que aquí solo hay que
    traducir cada referencia a su clave primaria.
    """
    records = list(records)
    if not records:
        return
    rations = _ration_ids(
        {(record.farm_code, record.ration_name, record.formulated_on) for record in records}
    )
    silages = _silage_ids(
        {(r.farm_code, r.silage_code) for r in records if r.silage_code is not None}
    )
    materials = _raw_material_ids(
        {r.raw_material_name for r in records if r.raw_material_name is not None}
    )
    for record in records:
        ration_id = rations[(record.farm_code, record.ration_name, record.formulated_on)]
        RationIngredient.objects.update_or_create(
            ration_id=ration_id,
            silage_id=(
                silages[(record.farm_code, record.silage_code)]
                if record.silage_code is not None
                else None
            ),
            raw_material_id=(
                materials[record.raw_material_name]
                if record.raw_material_name is not None
                else None
            ),
            defaults={"dry_matter_kg": record.dry_matter_kg, "ingestion_run": run},
        )
        summary.ration_ingredients += 1


def _load_animals(
    registrations: Iterable[AnimalRegistration], run: IngestionRun, summary: LoadSummary
) -> None:
    """Alta o actualización de animales, resueltos contra su explotación."""
    registrations = list(registrations)
    if not registrations:
        return
    farms = _farm_ids({registration.farm_code for registration in registrations})
    for registration in registrations:
        Animal.objects.update_or_create(
            farm_id=farms[registration.farm_code],
            ear_tag=registration.ear_tag,
            defaults={
                "birth_date": registration.birth_date,
                "breed": registration.breed,
                "lactation_number": registration.lactation_number,
                "last_calving_date": registration.last_calving_date,
                "culled_date": registration.culled_date,
                "ingestion_run": run,
            },
        )
        summary.animals += 1


def _load_production(
    readings: Iterable[ProductionReading], run: IngestionRun, summary: LoadSummary
) -> None:
    """Escribe la producción diaria, actualizando la que ya estuviera cargada.

    `update_conflicts` traduce a un `ON CONFLICT DO UPDATE` de PostgreSQL sobre
    el índice único `(animal, date)`: reingerir la misma entrega corrige en vez
    de duplicar, que es lo que hace falta cuando una fuente rectifica un dato.
    """
    readings = list(readings)
    if not readings:
        return
    animals = _animal_ids({(r.farm_code, r.ear_tag) for r in readings})
    DailyYield.objects.bulk_create(
        [
            DailyYield(
                animal_id=animals[(reading.farm_code, reading.ear_tag)],
                date=reading.date,
                liters=reading.liters,
                ingestion_run=run,
            )
            for reading in readings
        ],
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        update_fields=["liters", "ingestion_run"],
        unique_fields=["animal", "date"],
    )
    summary.daily_yields += len(readings)


def _load_quality(
    records: Iterable[MilkQualityRecord], run: IngestionRun, summary: LoadSummary
) -> None:
    """Escribe los controles lecheros individuales con la misma política."""
    records = list(records)
    if not records:
        return
    animals = _animal_ids({(r.farm_code, r.ear_tag) for r in records})
    MilkRecord.objects.bulk_create(
        [
            MilkRecord(
                animal_id=animals[(record.farm_code, record.ear_tag)],
                date=record.date,
                fat_pct=record.fat_pct,
                protein_pct=record.protein_pct,
                somatic_cell_count=record.somatic_cell_count,
                ingestion_run=run,
            )
            for record in records
        ],
        batch_size=BATCH_SIZE,
        update_conflicts=True,
        update_fields=["fat_pct", "protein_pct", "somatic_cell_count", "ingestion_run"],
        unique_fields=["animal", "date"],
    )
    summary.milk_records += len(records)


def _load_rejects(rejects: Iterable[Reject], run: IngestionRun, summary: LoadSummary) -> None:
    """Conserva lo que el adaptador no supo interpretar, con su motivo."""
    rejects = list(rejects)
    IngestionReject.objects.bulk_create(
        [
            IngestionReject(
                run=run,
                line_number=reject.line_number,
                raw=reject.raw,
                reason=reject.reason,
            )
            for reject in rejects
        ],
        batch_size=BATCH_SIZE,
    )
    summary.rejected += len(rejects)


def _farm_ids(codes: set[str]) -> dict[str, int]:
    """Resuelve códigos de explotación a claves primarias en una sola consulta."""
    found = dict(Farm.objects.filter(code__in=codes).values_list("code", "id"))
    missing = codes - found.keys()
    if missing:
        raise IngestionError(f"explotaciones no registradas: {sorted(missing)}")
    return found


def _animal_ids(keys: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Resuelve (código de explotación, crotal) a clave primaria en una consulta.

    El crotal es único por explotación, no globalmente, así que la clave natural
    de un animal son las dos cosas juntas.
    """
    tags = {ear_tag for _, ear_tag in keys}
    rows = Animal.objects.filter(ear_tag__in=tags).values_list("farm__code", "ear_tag", "id")
    found = {(code, ear_tag): pk for code, ear_tag, pk in rows}
    missing = keys - found.keys()
    if missing:
        raise IngestionError(f"animales no registrados: {sorted(missing)[:5]}")
    return found


def _plot_ids(keys: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Resuelve (código de explotación, código de parcela) a clave primaria.

    El código de parcela es único por explotación, no globalmente: dos ganaderos
    pueden llamar `P-01` a parcelas distintas.
    """
    codes = {plot_code for _, plot_code in keys}
    rows = Plot.objects.filter(code__in=codes).values_list("farm__code", "code", "id")
    found = {(farm_code, plot_code): pk for farm_code, plot_code, pk in rows}
    missing = keys - found.keys()
    if missing:
        raise IngestionError(f"parcelas no registradas: {sorted(missing)}")
    return found


def _crop_ids(keys: set[tuple[str, str, int, str]]) -> dict[tuple[str, str, int, str], int]:
    """Resuelve una campaña por explotación, parcela, año y especie.

    Las cuatro señas hacen falta: la misma parcela lleva dos especies el mismo
    año, que es exactamente lo que hace la rotación de verano e invierno.
    """
    seasons = {season for _, _, season, _ in keys}
    rows = Crop.objects.filter(season__in=seasons).values_list(
        "plot__farm__code", "plot__code", "season", "species", "id"
    )
    found = {(farm, plot, season, species): pk for farm, plot, season, species, pk in rows}
    missing = keys - found.keys()
    if missing:
        raise IngestionError(f"campañas no registradas: {sorted(missing)}")
    return found


def _silage_ids(keys: set[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """Resuelve (código de explotación, código de silo) a clave primaria.

    El esquema garantiza el código único por campaña, no por explotación, así que
    dos campañas de la misma granja podrían repetirlo. Quien formula una ración
    escribe solo el código del silo, de modo que si eso ocurre la referencia es
    ambigua y hay que decirlo en vez de quedarse con una de las dos.
    """
    codes = {silage_code for _, silage_code in keys}
    rows = Silage.objects.filter(code__in=codes).values_list("crop__plot__farm__code", "code", "id")
    found: dict[tuple[str, str], int] = {}
    for farm_code, silage_code, pk in rows:
        key = (farm_code, silage_code)
        if key in found:
            raise IngestionError(f"código de silo ambiguo en la explotación: {key}")
        found[key] = pk
    missing = keys - found.keys()
    if missing:
        raise IngestionError(f"silos no registrados: {sorted(missing)}")
    return found


def _ration_ids(keys: set[tuple[str, str, date]]) -> dict[tuple[str, str, date], int]:
    """Resuelve (explotación, nombre, fecha de formulación) a clave primaria."""
    names = {name for _, name, _ in keys}
    rows = Ration.objects.filter(name__in=names).values_list(
        "farm__code", "name", "formulated_on", "id"
    )
    found = {(farm, name, formulated_on): pk for farm, name, formulated_on, pk in rows}
    missing = keys - found.keys()
    if missing:
        raise IngestionError(f"raciones no registradas: {sorted(missing)}")
    return found


def _raw_material_ids(names: set[str]) -> dict[str, int]:
    """Resuelve nombres de materia prima a clave primaria en una sola consulta."""
    found = dict(RawMaterial.objects.filter(name__in=names).values_list("name", "id"))
    missing = names - found.keys()
    if missing:
        raise IngestionError(f"materias primas no registradas: {sorted(missing)}")
    return found
