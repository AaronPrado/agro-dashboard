"""Modelo agronómico: calendario de cultivo del forraje gallego.

Mismo criterio que `dairy.py`: funciones puras y deterministas con el azar
inyectado desde fuera, y cada valor con su procedencia al lado — fuente citada
cuando la hay, marca «modelado» cuando no la hay.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from farms.services.dairy import LACTATION_DAYS

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


# --- Alimentación: cómo se lotea el rebaño y qué come cada lote ---

# Ingesta de materia seca: las fuentes divulgativas del sector sitúan el consumo
# entre el 3 % y el 4 % del peso vivo, con ~3,2 % para una vaca en producción.
# Con un peso vivo de referencia de unos 650 kg para Frisona adulta —que está
# [sin verificar]— salen unos 21 kg de MS al día. Los valores por grupo se
# separan a partir de ahí.  [orden de magnitud verificado; reparto modelado]
#
# La proporción de forraje sobre materia seca y el umbral de días en leche que
# separa alta de baja producción son decisiones de manejo, no constantes del
# sector: varían de una explotación a otra.  [modelado]


@dataclass(frozen=True, slots=True)
class FeedingGroup:
    """Grupo de manejo: un lote de animales y la ración que se le formula.

    `max_days_in_milk` marca hasta qué día de lactación pertenece un animal a
    este grupo; nulo identifica al grupo de las secas, que es donde caen las que
    ya han pasado el secado.
    """

    batch_name: str
    ration_name: str
    dry_matter_kg: Decimal
    forage_share: Decimal
    max_days_in_milk: int | None


FEEDING_GROUPS = (
    FeedingGroup("Alta producción", "Lactación alta", Decimal("23.0"), Decimal("0.58"), 120),
    FeedingGroup(
        "Baja producción", "Lactación baja", Decimal("19.0"), Decimal("0.66"), LACTATION_DAYS
    ),
    FeedingGroup("Secas", "Secado", Decimal("12.0"), Decimal("0.90"), None),
)

# Materias primas habituales en el vacuno de leche. Los nombres y su categoría
# son nomenclatura estándar del sector; las proporciones entre ellas son una
# formulación plausible construida para que sume, no una recomendación
# nutricional, y ningún valor de este bloque debe leerse como tal.  [modelado]
RAW_MATERIALS = (
    ("Maíz grano", "concentrate"),
    ("Harina de soja 44", "concentrate"),
    ("Pulpa de remolacha", "byproduct"),
    ("Corrector mineral-vitamínico", "mineral"),
)
CONCENTRATE_MIX = {
    "Maíz grano": Decimal("0.45"),
    "Harina de soja 44": Decimal("0.28"),
    "Pulpa de remolacha": Decimal("0.24"),
    "Corrector mineral-vitamínico": Decimal("0.03"),
}

# Cada cuántos días se reformula, y cuántos silos entran a la vez en la ración.
RATION_INTERVAL_DAYS = 120  # [modelado]
SILAGES_PER_RATION = 2  # [modelado]


def ration_ingredients(
    group: FeedingGroup, silage_codes: Sequence[str]
) -> tuple[list[tuple[str, Decimal]], list[tuple[str, Decimal]]]:
    """Reparte los kg de materia seca del grupo entre silos y materias primas.

    Devuelve dos listas de (referencia, kg de MS). El último componente de cada
    mitad absorbe el resto del redondeo, de modo que la suma de los ingredientes
    es exactamente la ingesta declarada del grupo y no un céntimo menos.
    """
    forage_kg = (group.dry_matter_kg * group.forage_share).quantize(Decimal("0.01"))
    silages = _split_evenly(forage_kg, list(silage_codes))
    concentrate = _split_by_share(group.dry_matter_kg - forage_kg, CONCENTRATE_MIX)
    return silages, concentrate


def _split_evenly(total: Decimal, keys: list[str]) -> list[tuple[str, Decimal]]:
    """Reparte a partes iguales conservando la suma exacta."""
    share = (total / len(keys)).quantize(Decimal("0.01"))
    parts = [(key, share) for key in keys[:-1]]
    return [*parts, (keys[-1], total - share * (len(keys) - 1))]


def _split_by_share(total: Decimal, shares: dict[str, Decimal]) -> list[tuple[str, Decimal]]:
    """Reparte según proporciones dadas, con el último absorbiendo el resto."""
    keys = list(shares)
    parts = [(key, (total * shares[key]).quantize(Decimal("0.01"))) for key in keys[:-1]]
    return [*parts, (keys[-1], total - sum(kg for _, kg in parts))]


# --- Análisis NIR del forraje ---

# Los parámetros mínimos de un análisis de ensilado son materia seca, proteína
# bruta, fibra ácido detergente, fibra neutro detergente y cenizas; el almidón se
# añade en los ensilados de maíz. (Campo Galego, sobre qué debe traer una
# analítica de forraje.)  [verificado]
ANALYTES = (
    ("ms", "Materia seca", "%"),
    ("pb", "Proteína bruta", "% MS"),
    ("fnd", "Fibra neutro detergente", "% MS"),
    ("fad", "Fibra ácido detergente", "% MS"),
    ("almidon", "Almidón", "% MS"),
    ("cenizas", "Cenizas", "% MS"),
)

# El almidón distingue el ensilado de maíz del de hierba: solo el maíz lo
# determina. Es lo que permite estimar la composición del forraje de una ración.
STARCH_ANALYTE = "almidon"

# Rangos de composición por forraje, tomados de las tablas FEDNA de forrajes
# (fundacionfedna.org): «Ensilado de maíz», «Ray-grass, silo» y «Hierba, silo».
# Los extremos de cada rango son los de las clases de calidad que publica FEDNA,
# salvo tres excepciones que se declaran aquí:
#
#   - Maíz, materia seca: se usa 30-35 % porque es el momento óptimo de corte
#     según la propia ficha de FEDNA, no el rango completo de sus clases.
#   - Raigrás, materia seca: se usa 28-35 % en vez del rango completo (23-61 %),
#     porque el extremo alto corresponde a forraje pasado y el bajo a ensilado
#     sin preoreo, y la práctica descrita para Galicia es preorear hasta >=30 %
#     (SERIDA).  [interpretación declarada]
#   - Hierba, materia seca: derivada del rango de humedad publicado (71,7-84,0 %
#     sobre materia natural), que es como lo da la tabla.
#
# `None` significa que ese parámetro no se determina en esa especie: el almidón
# solo tiene sentido en el maíz. **Ningún valor que produce el generador cae
# fuera del rango publicado para ese forraje**; la distribución uniforme dentro
# del rango sí es una elección.  [modelado]
FORAGE_RANGES: dict[str, dict[str, tuple[Decimal, Decimal] | None]] = {
    "maize": {
        "ms": (Decimal("30.0"), Decimal("35.0")),
        "pb": (Decimal("6.95"), Decimal("8.78")),
        "fnd": (Decimal("44.9"), Decimal("57.0")),
        "fad": (Decimal("25.3"), Decimal("40.3")),
        "almidon": (Decimal("10.3"), Decimal("34.2")),
        "cenizas": (Decimal("4.01"), Decimal("7.28")),
    },
    "italian_ryegrass": {
        "ms": (Decimal("28.0"), Decimal("35.0")),
        "pb": (Decimal("10.7"), Decimal("18.6")),
        "fnd": (Decimal("41.1"), Decimal("64.8")),
        "fad": (Decimal("23.6"), Decimal("40.7")),
        "almidon": None,
        "cenizas": (Decimal("10.2"), Decimal("12.2")),
    },
    "grass_mix": {
        "ms": (Decimal("16.0"), Decimal("28.3")),
        "pb": (Decimal("9.50"), Decimal("18.6")),
        "fnd": (Decimal("39.2"), Decimal("68.7")),
        "fad": (Decimal("27.1"), Decimal("48.6")),
        "almidon": None,
        "cenizas": (Decimal("9.10"), Decimal("15.5")),
    },
}

# Nombre genérico: no se atribuye la analítica a ningún laboratorio real.
LABORATORY = "Laboratorio de análisis de forrajes"


def forage_analysis(rng: random.Random, species: str) -> dict[str, Decimal | None]:
    """Resultados de un análisis NIR de un ensilado de esa especie.

    Devuelve el valor de cada analito del catálogo, o `None` cuando el parámetro
    no se determina en ese forraje. Los códigos son los del modelo, no los del
    laboratorio: traducirlos es trabajo del adaptador.
    """
    ranges = FORAGE_RANGES[species]
    return {
        code: None if ranges[code] is None else _uniform_decimal(rng, *ranges[code])
        for code, _, _ in ANALYTES
    }


def _uniform_decimal(rng: random.Random, low: Decimal, high: Decimal) -> Decimal:
    """Sortea un valor en [low, high] con dos decimales."""
    span = int((high - low) * 100)
    return (low + Decimal(rng.randint(0, span)) / 100).quantize(Decimal("0.01"))
