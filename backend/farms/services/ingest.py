"""Cargador: única capa que escribe en el ORM.

Recibe los dataclasses del generador y los persiste. Es el punto por el que
entraría igualmente la ingesta de una fuente externa real. Toda la escritura va
en una única transacción: si algo falla, no queda una siembra a medias.
"""

from dataclasses import dataclass

from django.db import transaction

from farms.models import Animal, Farm, Milking, MilkRecord
from farms.services.generation import FarmData

BATCH_SIZE = 1000


@dataclass(slots=True)
class LoadSummary:
    """Contadores de lo persistido, para el resumen del comando."""

    farms: int = 0
    animals: int = 0
    milkings: int = 0
    milk_records: int = 0


@transaction.atomic
def load_farms(farms: list[FarmData], *, clear: bool = False) -> LoadSummary:
    """Persiste la jerarquía de granjas con `bulk_create` dentro de una transacción.

    Con `clear=True` borra las granjas existentes antes de sembrar (el CASCADE
    arrastra animales y registros): es el camino de idempotencia, misma semilla
    ⇒ misma base al relanzar.
    """
    if clear:
        Farm.objects.all().delete()

    summary = LoadSummary()
    for farm_data in farms:
        farm = Farm.objects.create(
            name=farm_data.name,
            code=farm_data.code,
            municipality=farm_data.municipality,
            province=farm_data.province,
        )
        summary.farms += 1

        animals = [
            Animal(
                farm=farm,
                ear_tag=animal_data.ear_tag,
                birth_date=animal_data.birth_date,
                breed=animal_data.breed,
                lactation_number=animal_data.lactation_number,
                last_calving_date=animal_data.last_calving_date,
                culled_date=animal_data.culled_date,
            )
            for animal_data in farm_data.animals
        ]
        # En PostgreSQL bulk_create rellena la PK de cada objeto, lo que permite
        # colgar de ellos los ordeños y controles sin volver a consultarlos.
        Animal.objects.bulk_create(animals, batch_size=BATCH_SIZE)
        summary.animals += len(animals)

        milkings: list[Milking] = []
        milk_records: list[MilkRecord] = []
        for animal, animal_data in zip(animals, farm_data.animals, strict=True):
            milkings.extend(
                Milking(animal=animal, date=m.date, liters=m.liters) for m in animal_data.milkings
            )
            milk_records.extend(
                MilkRecord(
                    animal=animal,
                    date=r.date,
                    fat_pct=r.fat_pct,
                    protein_pct=r.protein_pct,
                    somatic_cell_count=r.somatic_cell_count,
                )
                for r in animal_data.milk_records
            )

        Milking.objects.bulk_create(milkings, batch_size=BATCH_SIZE)
        MilkRecord.objects.bulk_create(milk_records, batch_size=BATCH_SIZE)
        summary.milkings += len(milkings)
        summary.milk_records += len(milk_records)

    return summary
