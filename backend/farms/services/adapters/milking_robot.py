"""Adaptador del robot o sala de ordeño.

La entrega es un CSV por explotación con una fila por ordeño. Tres cosas separan
ese fichero del modelo: el crotal viene sin el código de país, los kilos hay que
pasarlos a litros y el grano es el ordeño mientras que el modelo guarda el día.
Reconciliar las tres es todo el trabajo de este módulo.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import ClassVar

from farms.models import SourceSystem
from farms.services.adapters.base import (
    AdapterError,
    normalize_ear_tag,
    parse_decimal,
    parse_dmy_date,
)
from farms.services.canonical import CanonicalBatch, ProductionReading, Reject

EXPECTED_HEADER = "crotal;fecha;hora;kg"
FIELD_SEPARATOR = ";"
FIELD_COUNT = 4

# Densidad de la leche para pasar de kilos a litros; ~1.03 kg/L es el valor de
# referencia habitual.  [orden de magnitud verificado]
# Vive aquí y no en el modelo porque normalizar la unidad de cada fuente es
# trabajo del adaptador: el litro es la unidad canónica de la plataforma.
MILK_DENSITY_KG_PER_L = Decimal("1.03")


def to_liters(kg: Decimal) -> Decimal:
    """Convierte kilos de leche a litros, con la escala del campo del modelo."""
    return (kg / MILK_DENSITY_KG_PER_L).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class _Day:
    """Ordeños acumulados de un animal en un día mientras se lee el fichero."""

    total: Decimal = Decimal("0")
    measured: int = 0
    blank_line: int | None = None


class MilkingRobotAdapter:
    """Traduce la exportación de un robot de ordeño al modelo canónico.

    La explotación no viaja dentro del fichero: llega por fuera de la entrega,
    como ocurre en cualquier integración real, y por eso se recibe al construir.
    """

    source: ClassVar[SourceSystem] = SourceSystem.MILKING_ROBOT

    def __init__(self, farm_code: str) -> None:
        self.farm_code = farm_code

    def parse(self, payload: str) -> CanonicalBatch:
        """Lee la entrega entera y devuelve lo interpretado junto a lo rechazado.

        Una cabecera inesperada aborta: cargar la mitad de un fichero de origen
        desconocido es peor que no cargar nada. Una fila rota, en cambio, se
        aparta con su motivo y la entrega continúa.
        """
        lines = payload.splitlines()
        if not lines or lines[0].strip() != EXPECTED_HEADER:
            raise AdapterError(
                f"[{self.source}] cabecera inesperada: se esperaba {EXPECTED_HEADER!r}"
            )

        batch = CanonicalBatch(source=self.source)
        days: dict[tuple[str, date], _Day] = {}
        for number, raw in enumerate(lines[1:], start=2):
            if not raw.strip():
                continue
            try:
                ear_tag, day, kg = self._parse_line(raw)
            except ValueError as exc:
                batch.rejects.append(Reject(line_number=number, raw=raw, reason=str(exc)))
                continue
            entry = days.setdefault((ear_tag, day), _Day())
            if kg is None:
                entry.blank_line = number
            else:
                entry.total += kg
                entry.measured += 1

        self._close_days(days, batch)
        return batch

    def _parse_line(self, raw: str) -> tuple[str, date, Decimal | None]:
        """Trocea una fila y normaliza sus campos útiles.

        La hora se descarta: el modelo guarda el día, y conservar el instante
        obligaría a decidir zona horaria para un dato que nadie consulta.
        """
        parts = raw.split(FIELD_SEPARATOR)
        if len(parts) != FIELD_COUNT:
            raise ValueError(f"se esperaban {FIELD_COUNT} campos y hay {len(parts)}")
        local_tag, day, _clock, kg = parts
        return (
            normalize_ear_tag(local_tag),
            parse_dmy_date(day),
            parse_decimal(kg, decimal_separator=",") if kg.strip() else None,
        )

    def _close_days(self, days: dict[tuple[str, date], _Day], batch: CanonicalBatch) -> None:
        """Cierra cada día acumulado como una lectura canónica.

        Un día entero en blanco es un día registrado sin lectura, que el modelo
        distingue de un hueco. Un día a medias no se completa: sumar solo lo
        medido daría un total corto con aspecto de bueno, así que se rechaza.
        """
        for (ear_tag, day), entry in days.items():
            if entry.blank_line is not None and entry.measured:
                batch.rejects.append(
                    Reject(
                        line_number=entry.blank_line,
                        raw=f"{ear_tag};{day.isoformat()}",
                        reason="el día mezcla ordeños sin lectura con ordeños medidos",
                    )
                )
                continue
            liters = None if entry.blank_line is not None else to_liters(entry.total)
            batch.production.append(
                ProductionReading(
                    farm_code=self.farm_code,
                    ear_tag=ear_tag,
                    date=day,
                    liters=liters,
                )
            )
