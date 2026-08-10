"""Cargador: única capa que escribe en el ORM.

Recibe lotes canónicos, vengan de la fuente que vengan, y los persiste bajo una
carga registrada. No sabe qué formato tenía el fichero de origen ni ramifica por
procedencia: toda esa asimetría vive en los adaptadores y termina antes de aquí.
Los hechos se refieren a otros por clave natural —código de explotación, crotal—
y resolverlos a clave primaria es el trabajo de este módulo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

from django.db import transaction

from farms.models import (
    Animal,
    DailyYield,
    Farm,
    IngestionReject,
    IngestionRun,
    MilkRecord,
)
from farms.services.canonical import (
    AnimalRegistration,
    CanonicalBatch,
    FarmRegistration,
    MilkQualityRecord,
    ProductionReading,
    Reject,
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

    @property
    def loaded(self) -> int:
        """Filas efectivamente escritas, sin contar las rechazadas."""
        return self.farms + self.animals + self.daily_yields + self.milk_records

    def __iadd__(self, other: Self) -> Self:
        """Acumula el resultado de varias entregas en un solo resumen."""
        self.farms += other.farms
        self.animals += other.animals
        self.daily_yields += other.daily_yields
        self.milk_records += other.milk_records
        self.rejected += other.rejected
        return self


def clear() -> None:
    """Vacía lo sembrado: primero los hechos, después las cargas.

    El orden no es opcional. La procedencia va con `PROTECT`, así que borrar una
    carga antes que sus filas lo rechaza la base de datos.
    """
    Farm.objects.all().delete()
    IngestionRun.objects.all().delete()


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
