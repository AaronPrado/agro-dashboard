"""Comando de management que puebla la base con datos mockeados reproducibles."""

import random
from datetime import date, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from farms.services.generation import GenerationParams, generate
from farms.services.ingest import load_farms

DEFAULT_SEED = 42
DEFAULT_FARMS = 5
DEFAULT_ANIMALS_PER_FARM = 40
DEFAULT_WINDOW_DAYS = 365


class Command(BaseCommand):
    """Genera granjas, animales y sus series de producción de forma determinista."""

    help = "Puebla la base de datos con datos lecheros mockeados y reproducibles."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--seed",
            type=int,
            default=DEFAULT_SEED,
            help="Semilla del generador (misma semilla ⇒ mismos datos).",
        )
        parser.add_argument(
            "--farms",
            type=int,
            default=DEFAULT_FARMS,
            help="Número de granjas a generar.",
        )
        parser.add_argument(
            "--animals-per-farm",
            type=int,
            default=DEFAULT_ANIMALS_PER_FARM,
            help="Número de animales por granja.",
        )
        parser.add_argument(
            "--start",
            type=date.fromisoformat,
            default=None,
            help="Primer día de la ventana de ordeños (ISO YYYY-MM-DD).",
        )
        parser.add_argument(
            "--end",
            type=date.fromisoformat,
            default=None,
            help="Último día de la ventana de ordeños (ISO YYYY-MM-DD).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Borra las granjas existentes antes de sembrar.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        farms_count: int = options["farms"]
        animals_per_farm: int = options["animals_per_farm"]
        seed: int = options["seed"]

        end: date = options["end"] or date.today()
        start: date = options["start"] or end - timedelta(days=DEFAULT_WINDOW_DAYS)

        if farms_count < 1 or animals_per_farm < 1:
            raise CommandError("--farms y --animals-per-farm deben ser >= 1.")
        if start > end:
            raise CommandError("--start no puede ser posterior a --end.")

        rng = random.Random(seed)  # noqa: S311
        params = GenerationParams(
            farms=farms_count,
            animals_per_farm=animals_per_farm,
            start=start,
            end=end,
        )

        farms_data = generate(rng, params)
        summary = load_farms(farms_data, clear=options["clear"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Sembrado: {summary.farms} granjas, {summary.animals} animales, "
                f"{summary.daily_yields} producciones diarias, "
                f"{summary.milk_records} controles "
                f"(semilla {seed})."
            )
        )
