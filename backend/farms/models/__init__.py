"""Modelos del dominio, repartidos por área y reexportados como un solo espacio.

El paquete conserva la importación canónica `from farms.models import X`, de modo
que la división en módulos no altera el resto del proyecto. Un modelo solo queda
registrado en la app si su módulo se importa aquí.
"""

from farms.models.agronomy import Crop, NIRAnalysis, Plot, RawMaterial, Silage
from farms.models.analysis import (
    AnalysisResult,
    Analyte,
    BatchMilkSample,
    TargetProfile,
    TargetRange,
)
from farms.models.batch import (
    AnimalBatch,
    AnimalBatchMembership,
    BatchRation,
    Ration,
    RationIngredient,
)
from farms.models.dairy import Animal, DailyYield, MilkRecord
from farms.models.farm import Farm
from farms.models.ingestion import IngestionReject, IngestionRun, Sourced, SourceSystem

__all__ = [
    "AnalysisResult",
    "Analyte",
    "Animal",
    "AnimalBatch",
    "AnimalBatchMembership",
    "BatchMilkSample",
    "BatchRation",
    "Crop",
    "DailyYield",
    "Farm",
    "IngestionReject",
    "IngestionRun",
    "MilkRecord",
    "NIRAnalysis",
    "Plot",
    "Ration",
    "RationIngredient",
    "RawMaterial",
    "Silage",
    "Sourced",
    "SourceSystem",
    "TargetProfile",
    "TargetRange",
]
