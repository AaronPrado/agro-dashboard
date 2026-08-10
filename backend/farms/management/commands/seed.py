"""Comando de management que puebla la base con datos mockeados reproducibles."""

import random
from datetime import date, timedelta
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from farms.services import ingest
from farms.services.adapters.field_notebook import FieldNotebookAdapter
from farms.services.adapters.milk_recording import MilkRecordingAdapter
from farms.services.adapters.milking_robot import MilkingRobotAdapter
from farms.services.feeds import field_notebook_feed, milk_recording_feeds, milking_robot_feed
from farms.services.generation import FarmData, GenerationParams, generate
from farms.services.ingest import LoadSummary

DEFAULT_SEED = 42
DEFAULT_FARMS = 5
DEFAULT_ANIMALS_PER_FARM = 40
DEFAULT_WINDOW_DAYS = 365


class Command(BaseCommand):
    """Genera los datos, los emite como entregas de cada fuente y los ingiere.

    El comando no escribe en la base: genera, serializa el crudo que exportaría
    cada sistema, se lo pasa a su adaptador y carga el resultado canónico. Es el
    mismo recorrido que haría con ficheros reales, con el mock sustituyendo solo
    al sistema de origen.
    """

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
            help="Primer día de la ventana de producción (ISO YYYY-MM-DD).",
        )
        parser.add_argument(
            "--end",
            type=date.fromisoformat,
            default=None,
            help="Último día de la ventana de producción (ISO YYYY-MM-DD).",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Vacía las explotaciones y las cargas antes de sembrar.",
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
        if options["clear"]:
            ingest.clear()

        summary = LoadSummary()
        for farm_data in farms_data:
            summary += self._ingest_milk_recording(farm_data)
            summary += self._ingest_field_notebook(farm_data)
            summary += self._ingest_milking_robot(rng, farm_data)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sembrado: {summary.farms} altas de explotación, "
                f"{summary.plots} parcelas, {summary.crops} campañas, "
                f"{summary.silages} silos, {summary.rations} raciones "
                f"con {summary.ration_ingredients} ingredientes, "
                f"{summary.batches} lotes con {summary.memberships} pertenencias "
                f"y {summary.batch_rations} periodos de ración, "
                f"{summary.animals} altas de animal, "
                f"{summary.daily_yields} producciones diarias, "
                f"{summary.milk_records} controles, "
                f"{summary.rejected} registros rechazados "
                f"(semilla {seed})."
            )
        )

    def _ingest_milk_recording(self, farm_data: FarmData) -> LoadSummary:
        """Ingiere los informes mensuales del núcleo de control.

        Van primero porque son los que declaran la explotación y el censo: la
        producción se ancla al animal por su crotal, y una entrega que hable de
        animales desconocidos aborta.
        """
        summary = LoadSummary()
        adapter = MilkRecordingAdapter()
        for control_date, report in milk_recording_feeds(farm_data).items():
            batch = adapter.parse(report)
            _, partial = ingest.load(
                batch, reference=f"control-{farm_data.code}-{control_date:%Y%m}.txt"
            )
            summary += partial
        return summary

    def _ingest_field_notebook(self, farm_data: FarmData) -> LoadSummary:
        """Ingiere el cuaderno de campo: parcelas, campañas y silos.

        Va después del control lechero porque el cuaderno solo declara el código
        de la explotación, no su nombre ni su concello: quien la da de alta es el
        informe oficial.
        """
        adapter = FieldNotebookAdapter()
        batch = adapter.parse(field_notebook_feed(farm_data))
        _, partial = ingest.load(batch, reference=f"cuaderno-{farm_data.code}.txt")
        return partial

    def _ingest_milking_robot(self, rng: random.Random, farm_data: FarmData) -> LoadSummary:
        """Ingiere la exportación del robot de ordeño de la explotación."""
        adapter = MilkingRobotAdapter(farm_code=farm_data.code)
        batch = adapter.parse(milking_robot_feed(rng, farm_data))
        _, partial = ingest.load(batch, reference=f"robot-{farm_data.code}.csv")
        return partial
