"""Generador puro de datos lecheros mockeados.

No escribe en el ORM: produce dataclasses con forma de dominio a partir de un RNG
sembrado, usando el modelo biológico de `dairy`. Es la capa intercambiable —
sustituir el mock por una ingesta real es reemplazar este módulo, dejando intacto
el cargador. El azar entra siempre por el `rng` inyectado (nunca estado global),
de modo que misma semilla + mismos parámetros ⇒ mismos datos.
"""

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.utils.text import slugify

from farms.services.agronomy import (
    PLOT_NAMES,
    PLOTS_PER_FARM,
    ROTATION_SHARE,
    crop_dates,
    plot_area_ha,
    silage_dates,
)
from farms.services.dairy import (
    BREED_COMPOSITION,
    BREED_YIELD_FACTOR,
    parity_factor,
    seasonal_factor,
    wood_yield_kg,
)

ONE_DAY = timedelta(days=1)

# Distribución de razas muy sesgada hacia la Frisona, dominante en el vacuno de
# leche gallego.  [magnitud del sesgo: modelado]
BREED_WEIGHTS = {
    "holstein": 0.80,
    "procross": 0.08,
    "brown_swiss": 0.06,
    "jersey": 0.04,
    "other": 0.02,
}

# Intervalo entre partos: ~305 días de lactación + ~60 de secado ≈ un año.
DRY_PERIOD_DAYS = 60  # [modelado sobre práctica estándar]
CALVING_INTERVAL_DAYS = 305 + DRY_PERIOD_DAYS

# Ruido diario multiplicativo (variación individual y de medición).  [modelado]
DAILY_NOISE_SIGMA = 0.08

# Muestreo de células somáticas: log-normal (así se distribuye en la práctica),
# con mediana ~60k cél/ml y cola que cruza los umbrales de mastitis.  [modelado]
SCC_LOGNORM_MU = math.log(60_000)
SCC_LOGNORM_SIGMA = 0.70

# Tasas de casos borde deliberados.  [modelado]
GAP_RATE = 0.02  # probabilidad de iniciar un hueco de avería en un día productivo
GAP_MAX_DAYS = 5  # duración máxima de un hueco
NULL_RATE = 0.01  # día registrado pero sin lectura válida (liters=None)
OUTLIER_RATE = 0.005  # lectura anómala puntual (fallo de sensor)
OUTLIER_MULTIPLIERS = (0.2, 2.5)
CULL_RATE = 0.10  # fracción de animales que causan baja dentro de la ventana

MAX_KG = Decimal("999.99")  # tope defensivo; convertido a litros sigue cabiendo en el modelo
MAX_PCT = Decimal("99.99")  # tope del DecimalField(max_digits=4, decimal_places=2)

# Estructura del crotal bovino español: `ES` más doce dígitos. El código de país
# de dos letras y el máximo de doce dígitos los fija el Reglamento (CE) 1760/2000;
# el desglose de esos doce, el RD 787/2023: dos de especie (22, bovino), dos de
# comunidad autónoma (11, Galicia) y ocho de identificación del animal. Los
# nacidos antes del 30/06/2025 llevaban la estructura anterior, con un dígito de
# control cuyo algoritmo no está publicado: se emite con la vigente antes que
# inventar ese dígito, porque un dígito de control falso es comprobable.
EAR_TAG_PREFIX = "ES2211"

# Nombres de granjas mockeados
FARM_NAMES = (
    "Casa Grande",
    "A Ponte",
    "Leira Nova",
    "O Souto",
    "Vilar",
    "Fonteboa",
    "Rega da Veiga",
    "Outeiro",
)
GALICIAN_PLACES = (
    ("Sarria", "Lugo"),
    ("Chantada", "Lugo"),
    ("Arzúa", "A Coruña"),
    ("Lalín", "Pontevedra"),
    ("A Estrada", "Pontevedra"),
    ("Xinzo de Limia", "Ourense"),
)


@dataclass(slots=True)
class DailyYieldData:
    """Producción de un animal en un día, en kilos, tal como la mide el ordeño."""

    date: date
    kg: Decimal | None


@dataclass(slots=True)
class MilkRecordData:
    """Control lechero mensual (analítica de calidad) de un animal."""

    date: date
    fat_pct: Decimal | None
    protein_pct: Decimal | None
    somatic_cell_count: int | None


@dataclass(slots=True)
class AnimalData:
    """Vaca con su serie de producción diaria y sus controles."""

    ear_tag: str
    birth_date: date
    breed: str
    lactation_number: int
    last_calving_date: date | None
    culled_date: date | None
    daily_yields: list[DailyYieldData]
    milk_records: list[MilkRecordData]


@dataclass(slots=True)
class SilageData:
    """Silo conservado de una campaña, con sus fechas de cierre y apertura."""

    code: str
    sealed_date: date
    opened_date: date


@dataclass(slots=True)
class CropData:
    """Campaña de cultivo sobre una parcela y lo que se ensiló de ella."""

    species: str
    season: int
    sowing_date: date | None
    harvest_date: date
    silages: list[SilageData]


@dataclass(slots=True)
class PlotData:
    """Parcela de la explotación con sus campañas."""

    code: str
    name: str
    area_ha: Decimal
    crops: list[CropData]


@dataclass(slots=True)
class FarmData:
    """Granja con sus animales."""

    name: str
    code: str
    municipality: str
    province: str
    animals: list[AnimalData]
    plots: list[PlotData]


@dataclass(slots=True)
class GenerationParams:
    """Parámetros de alto nivel que gobiernan una generación."""

    farms: int
    animals_per_farm: int
    start: date
    end: date


def generate(rng: random.Random, params: GenerationParams) -> list[FarmData]:
    """Produce la jerarquía completa de datos de forma determinista dado `rng`."""
    return [_make_farm(rng, index, params) for index in range(params.farms)]


def _make_farm(rng: random.Random, index: int, params: GenerationParams) -> FarmData:
    """Genera una granja con su plantilla de animales y su base territorial."""
    name = rng.choice(FARM_NAMES)
    municipality, province = rng.choice(GALICIAN_PLACES)
    animals = [
        _make_animal(rng, params, ear_tag=f"{EAR_TAG_PREFIX}{index + 1:02d}{n + 1:06d}")
        for n in range(params.animals_per_farm)
    ]
    # El índice garantiza un código único aunque se repita el nombre.
    return FarmData(
        name=name,
        code=slugify(f"{name}-{index + 1}"),
        municipality=municipality,
        province=province,
        animals=animals,
        plots=_make_plots(rng, params),
    )


def _make_plots(rng: random.Random, params: GenerationParams) -> list[PlotData]:
    """Base territorial de la explotación: parcelas con sus campañas."""
    names = rng.sample(PLOT_NAMES, k=rng.randint(*PLOTS_PER_FARM))
    return [
        PlotData(
            code=f"P-{number:02d}",
            name=plot_name,
            area_ha=plot_area_ha(rng),
            crops=_make_crops(rng, number, params, rotated=rng.random() < ROTATION_SHARE),
        )
        for number, plot_name in enumerate(names, start=1)
    ]


def _make_crops(
    rng: random.Random, plot_number: int, params: GenerationParams, *, rotated: bool
) -> list[CropData]:
    """Campañas de una parcela: la rotación de verano e invierno, o la pradera.

    Se generan también las campañas del año anterior a la ventana, porque el silo
    que come el rebaño en enero se cosechó el otoño de antes.
    """
    species = ("maize", "italian_ryegrass") if rotated else ("grass_mix",)
    crops: list[CropData] = []
    for season in range(params.start.year - 1, params.end.year + 1):
        for name in species:
            sowing_date, harvest_date = crop_dates(rng, name, season)
            if harvest_date > params.end:
                continue  # todavía no se ha cosechado dentro de la ventana
            crops.append(
                CropData(
                    species=name,
                    season=season,
                    sowing_date=sowing_date,
                    harvest_date=harvest_date,
                    silages=[_make_silage(rng, plot_number, name, season, harvest_date)],
                )
            )
    return crops


def _make_silage(
    rng: random.Random, plot_number: int, species: str, season: int, harvest_date: date
) -> SilageData:
    """Silo de una campaña: se cierra tras cosechar y se abre tras fermentar."""
    sealed_date, opened_date = silage_dates(rng, harvest_date)
    return SilageData(
        code=f"S-{season}-P{plot_number:02d}-{species[0].upper()}",
        sealed_date=sealed_date,
        opened_date=opened_date,
    )


def _make_animal(rng: random.Random, params: GenerationParams, ear_tag: str) -> AnimalData:
    """Construye una vaca: identidad, historial de partos y sus series."""
    breed = _choose_breed(rng)
    birth_date = params.start - timedelta(days=rng.randint(2 * 365, 6 * 365))
    # Primer parto en torno a los 24 meses; luego, un parto al año.
    first_calving = birth_date + timedelta(days=rng.randint(23 * 30, 26 * 30))
    calvings = _calving_timeline(rng, first_calving, params.end)
    culled_date = _maybe_cull(rng, params)
    last_calving_date, lactation_number = _latest_calving(calvings, params.end)

    return AnimalData(
        ear_tag=ear_tag,
        birth_date=birth_date,
        breed=breed,
        lactation_number=lactation_number,
        last_calving_date=last_calving_date,
        culled_date=culled_date,
        daily_yields=_daily_yields(rng, breed, calvings, culled_date, params),
        milk_records=_monthly_records(rng, breed, calvings, culled_date, params),
    )


def _choose_breed(rng: random.Random) -> str:
    """Elige raza con la distribución sesgada a Frisona."""
    breeds = list(BREED_WEIGHTS)
    weights = list(BREED_WEIGHTS.values())
    return rng.choices(breeds, weights=weights, k=1)[0]


def _calving_timeline(rng: random.Random, first_calving: date, end: date) -> list[tuple[date, int]]:
    """Lista de (fecha de parto, número de lactación) desde el primer parto hasta `end`."""
    events: list[tuple[date, int]] = []
    calving = first_calving
    parity = 1
    while calving <= end:
        events.append((calving, parity))
        calving += timedelta(days=CALVING_INTERVAL_DAYS + rng.randint(-15, 30))
        parity += 1
    return events


def _active_calving(calvings: list[tuple[date, int]], day: date) -> tuple[date, int] | None:
    """Parto vigente en `day`: el más reciente anterior o igual; None si aún no ha parido."""
    active: tuple[date, int] | None = None
    for calving_date, parity in calvings:
        if calving_date <= day:
            active = (calving_date, parity)
        else:
            break
    return active


def _latest_calving(calvings: list[tuple[date, int]], ref: date) -> tuple[date | None, int]:
    """Estado escalar del animal: último parto y lactación a fecha `ref` (o novilla)."""
    active = _active_calving(calvings, ref)
    if active is None:
        return None, 0  # novilla que aún no ha parido: coincide con el default del modelo
    return active


def _maybe_cull(rng: random.Random, params: GenerationParams) -> date | None:
    """Con probabilidad CULL_RATE, fija una baja en la segunda mitad de la ventana."""
    if rng.random() >= CULL_RATE:
        return None
    span = (params.end - params.start).days
    return params.start + timedelta(days=rng.randint(span // 2, span))


def _daily_yields(
    rng: random.Random,
    breed: str,
    calvings: list[tuple[date, int]],
    culled_date: date | None,
    params: GenerationParams,
) -> list[DailyYieldData]:
    """Serie diaria de producción con curva de lactación, estacionalidad y casos borde."""
    records: list[DailyYieldData] = []
    yield_factor = BREED_YIELD_FACTOR[breed]
    day = params.start
    gap_days_left = 0
    while day <= params.end:
        if culled_date is not None and day > culled_date:
            break
        active = _active_calving(calvings, day)
        if active is None:
            day += ONE_DAY
            continue
        calving_date, parity = active
        dim = (day - calving_date).days + 1
        base_kg = wood_yield_kg(dim)
        if base_kg == 0.0:
            day += ONE_DAY
            continue  # periodo seco: hueco natural, no avería
        if gap_days_left > 0:
            gap_days_left -= 1
            day += ONE_DAY
            continue  # avería en curso
        if rng.random() < GAP_RATE:
            gap_days_left = rng.randint(1, GAP_MAX_DAYS)
            day += ONE_DAY
            continue
        if rng.random() < NULL_RATE:
            records.append(DailyYieldData(date=day, kg=None))  # registrado sin lectura
            day += ONE_DAY
            continue
        factor = yield_factor * parity_factor(parity) * seasonal_factor(day)
        kg = base_kg * factor * max(0.0, rng.gauss(1.0, DAILY_NOISE_SIGMA))
        if rng.random() < OUTLIER_RATE:
            kg *= rng.choice(OUTLIER_MULTIPLIERS)
        records.append(DailyYieldData(date=day, kg=_quantize_kg(kg)))
        day += ONE_DAY
    return records


def _monthly_records(
    rng: random.Random,
    breed: str,
    calvings: list[tuple[date, int]],
    culled_date: date | None,
    params: GenerationParams,
) -> list[MilkRecordData]:
    """Un control lechero por mes mientras el animal está en producción."""
    fat_mean, protein_mean = BREED_COMPOSITION[breed]
    records: list[MilkRecordData] = []
    for control_day in _monthly_dates(params.start, params.end):
        if culled_date is not None and control_day > culled_date:
            break
        active = _active_calving(calvings, control_day)
        if active is None:
            continue  # novilla que todavía no ha parido
        calving_date, _ = active
        if wood_yield_kg((control_day - calving_date).days + 1) == 0.0:
            continue  # vaca seca: no hay leche que muestrear
        scc: int | None = int(rng.lognormvariate(SCC_LOGNORM_MU, SCC_LOGNORM_SIGMA))
        if rng.random() < NULL_RATE * 5:
            scc = None  # a veces el control no trae recuento
        records.append(
            MilkRecordData(
                date=control_day,
                fat_pct=_quantize_pct(rng.gauss(fat_mean, 0.3)),
                protein_pct=_quantize_pct(rng.gauss(protein_mean, 0.2)),
                somatic_cell_count=scc,
            )
        )
    return records


def _monthly_dates(start: date, end: date):
    """Genera el día 1 de cada mes dentro de [start, end]."""
    year, month = start.year, start.month
    while True:
        current = date(year, month, 1)
        if current > end:
            return
        if current >= start:
            yield current
        month += 1
        if month > 12:
            month, year = 1, year + 1


def _quantize_pct(value: float) -> Decimal:
    """Cuantiza un porcentaje a 2 decimales y lo acota al rango del DecimalField."""
    pct = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(max(pct, Decimal("0")), MAX_PCT)


def _quantize_kg(value: float) -> Decimal:
    """Cuantiza kg a 2 decimales, la escala con la que exporta el sistema de origen."""
    kg = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return min(kg, MAX_KG)
