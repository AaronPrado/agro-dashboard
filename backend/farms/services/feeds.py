"""Emisores del crudo de cada fuente: del dominio al texto que exportaría el sistema.

Estos emisores son andamio del mock y desaparecen el día que las entregas lleguen
de sistemas reales; los adaptadores que las leen, no. Por eso los cuatro viven
juntos aquí mientras que cada adaptador tiene su propio módulo.
"""

import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from farms.services.adapters.base import EAR_TAG_COUNTRY_CODE
from farms.services.generation import FarmData

MILKING_ROBOT_HEADER = "crotal;fecha;hora;kg"

# El robot registra cada ordeño por separado. El reparto del total diario entre
# ellos es arbitrario y no afecta a la suma, que es el dato del generador.
MILKING_HOURS = (6, 17)
EVENING_SHARE_RANGE = (0.45, 0.60)


def milking_robot_feed(rng: random.Random, farm: FarmData) -> str:
    """Exportación del robot de ordeño de una explotación, una fila por ordeño.

    Escribe como escribiría el sistema de origen y no como conviene al modelo: el
    crotal sin el código de país, la fecha en DD/MM/YYYY, la coma decimal y los
    kilos de la báscula. La explotación no aparece: el fichero es de un robot, y
    el robot es de una granja.
    """
    lines = [MILKING_ROBOT_HEADER]
    for animal in farm.animals:
        local_tag = animal.ear_tag.removeprefix(EAR_TAG_COUNTRY_CODE)
        for entry in animal.daily_yields:
            if entry.kg is None:
                lines.append(f"{local_tag};{_dmy(entry.date)};{_clock(rng, 0)};")
                continue
            for index, kg in enumerate(_split_milkings(rng, entry.kg)):
                lines.append(f"{local_tag};{_dmy(entry.date)};{_clock(rng, index)};{_comma(kg)}")
    return "\n".join(lines)


def _split_milkings(rng: random.Random, total: Decimal) -> list[Decimal]:
    """Reparte el total del día entre dos ordeños conservando la suma exacta.

    El segundo se redondea y el primero absorbe la diferencia, de modo que sumar
    las filas devuelve exactamente el kilaje del día y el viaje de ida y vuelta
    por el fichero no pierde ni un gramo.
    """
    share = Decimal(str(round(rng.uniform(*EVENING_SHARE_RANGE), 4)))
    evening = (total * share).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return [total - evening, evening]


def _clock(rng: random.Random, index: int) -> str:
    """Hora del ordeño: la fuente la registra, el modelo no la guarda."""
    return f"{MILKING_HOURS[index]:02d}:{rng.randint(0, 59):02d}"


def _dmy(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _comma(value: Decimal) -> str:
    return str(value).replace(".", ",")
