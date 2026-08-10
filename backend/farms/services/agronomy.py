"""Modelo agronómico: calendario de cultivo del forraje gallego.

Mismo criterio que `dairy.py`: funciones puras y deterministas con el azar
inyectado desde fuera, y cada valor con su procedencia al lado — fuente citada
cuando la hay, marca «modelado» cuando no la hay.
"""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

# La rotación dominante en el vacuno de leche gallego es maíz forrajero como
# cultivo de verano con raigrás italiano como cultivo de invierno: se practica en
# el 51,7 % de las explotaciones (Revista Pastos, «Productividad de la rotación
# anual raigrás-maíz en Galicia»). El reparto exacto entre parcelas en rotación y
# praderas permanentes de una explotación concreta es una elección.  [modelado]
ROTATION_SHARE = 0.70

# Tamaño de la base territorial de una explotación lechera gallega.  [modelado]
PLOTS_PER_FARM = (3, 6)
PLOT_AREA_HA = (Decimal("0.80"), Decimal("4.50"))

# El silo se cierra el día de la cosecha o al día siguiente, y no se abre hasta
# que la fermentación ha terminado.  [modelado]
SEALING_DELAY_DAYS = (0, 2)
FERMENTATION_DAYS = (25, 45)

# Topónimos de parcela habituales en el rural gallego.
PLOT_NAMES = (
    "Leira do Souto",
    "A Veiga",
    "Agro Novo",
    "Chousa Grande",
    "O Cortiño",
    "Prado da Fonte",
    "Leira Longa",
    "A Devesa",
)


@dataclass(frozen=True, slots=True)
class CropCalendar:
    """Ventanas de siembra y cosecha de una especie, expresadas como (mes, día).

    `sowing` nulo describe un cultivo que no se siembra cada campaña, como una
    pradera ya establecida. `sown_previous_year` marca las campañas que cruzan
    dos años naturales, que es el caso del cultivo de invierno.
    """

    sowing: tuple[tuple[int, int], tuple[int, int]] | None
    harvest: tuple[tuple[int, int], tuple[int, int]]
    sown_previous_year: bool


# Siembra del maíz de finales de abril a lo largo de mayo según la zona (Campo
# Galego) y raigrás italiano sembrado en octubre que no se ensila hasta bien
# entrado marzo (SERIDA, «Manejo de forrajes invernales para rotaciones de
# cultivos»).  [verificado]
# Los extremos exactos de cada ventana, y la ventana de cosecha del maíz, están
# ajustados dentro de esas descripciones pero no tomados de una fuente.  [modelado]
CROP_CALENDAR = {
    "maize": CropCalendar(
        sowing=((4, 25), (5, 31)),
        harvest=((9, 10), (10, 15)),
        sown_previous_year=False,
    ),
    "italian_ryegrass": CropCalendar(
        sowing=((10, 1), (10, 31)),
        harvest=((3, 20), (4, 30)),
        sown_previous_year=True,
    ),
    "grass_mix": CropCalendar(
        sowing=None,
        harvest=((5, 5), (6, 15)),
        sown_previous_year=False,
    ),
}


def crop_dates(rng: random.Random, species: str, season: int) -> tuple[date | None, date]:
    """Siembra y cosecha de una campaña, sorteadas dentro de sus ventanas.

    `season` es el año de cosecha, que es como se identifica una campaña en el
    modelo. El cultivo de invierno se siembra en el otoño anterior, así que su
    campaña cruza dos años naturales y la siembra cae en `season - 1`.
    """
    calendar = CROP_CALENDAR[species]
    harvest = _date_in_window(rng, season, calendar.harvest)
    if calendar.sowing is None:
        return None, harvest
    sowing_year = season - 1 if calendar.sown_previous_year else season
    return _date_in_window(rng, sowing_year, calendar.sowing), harvest


def silage_dates(rng: random.Random, harvest_date: date) -> tuple[date, date]:
    """Cierre y apertura del silo a partir de la fecha de cosecha."""
    sealed = harvest_date + timedelta(days=rng.randint(*SEALING_DELAY_DAYS))
    opened = sealed + timedelta(days=rng.randint(*FERMENTATION_DAYS))
    return sealed, opened


def plot_area_ha(rng: random.Random) -> Decimal:
    """Superficie de una parcela, con la escala del campo del modelo."""
    low, high = PLOT_AREA_HA
    span = int((high - low) * 100)
    return (low + Decimal(rng.randint(0, span)) / 100).quantize(Decimal("0.0001"))


def _date_in_window(
    rng: random.Random, year: int, window: tuple[tuple[int, int], tuple[int, int]]
) -> date:
    """Sortea un día dentro de la ventana (mes, día)-(mes, día) de ese año."""
    (start_month, start_day), (end_month, end_day) = window
    start = date(year, start_month, start_day)
    end = date(year, end_month, end_day)
    return start + timedelta(days=rng.randint(0, (end - start).days))
