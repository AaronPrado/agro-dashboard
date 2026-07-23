"""Modelo biológico del dominio lechero: curva de lactación, estacionalidad y
composición de la leche.

Funciones puras y deterministas — el azar se inyecta aparte, en el generador.
Reúne en un único sitio los valores del sector junto a su procedencia: cuando un
valor carece de respaldo publicado directo, el comentario lo marca como
«modelado» (elegido para dar forma realista, no medido en una fuente).
"""

import math
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

# --- Curva de lactación: función de Wood (1967), y(t) = a·t^b·e^(−c·t) ---
# Parámetros para Holstein estimados por REML/Bayes sobre ganado Holstein
# (Ghavi Hossein-Zadeh, J. of Applied Animal Research, 2022). Rinden kg/día:
# `a` ≈ producción inicial, `b` pendiente de subida al pico, `c` pendiente de bajada.
WOOD_A = 12.1
WOOD_B = 0.285
WOOD_C = 0.00328

# Duración de la lactación hasta el secado; 305 días es el estándar del control
# lechero oficial.  [modelado sobre práctica estándar del sector]
LACTATION_DAYS = 305

# Densidad de la leche para convertir kg→L (la producción se publica en kg).
# ~1.03 kg/L es el valor de referencia habitual.  [orden de magnitud verificado]
MILK_DENSITY_KG_PER_L = Decimal("1.03")

# Factor multiplicativo sobre `a` de Wood por raza, relativo a la Holstein (=1.0).
# Derivado de rangos divulgativos de producción diaria (Holstein 30–40, Brown
# Swiss 20–25, Jersey 15–25 L/día): órdenes de magnitud del sector, no de un
# paper. Procross ≈ intermedio; «other» ≈ Holstein.  [modelado]
BREED_YIELD_FACTOR = {
    "holstein": 1.00,
    "brown_swiss": 0.70,
    "procross": 0.80,
    "jersey": 0.60,
    "other": 0.90,
}

# Composición media de la leche por raza (grasa %, proteína %). Anclas verificadas:
# Holstein (3.7, 3.1) y Jersey (4.9, 3.8) (NCBI, «Designing Foods»). Las razas
# intermedias se interpolan entre esos dos extremos.  [interpolado / modelado]
BREED_COMPOSITION = {
    "holstein": (3.7, 3.1),
    "brown_swiss": (4.0, 3.4),
    "procross": (4.2, 3.5),
    "jersey": (4.9, 3.8),
    "other": (3.8, 3.2),
}

# Umbrales de recuento de células somáticas (cél/ml), verificados (National
# Mastitis Council; límite legal a granel en MilkRecord.LEGAL_SCC_LIMIT):
# sana <100k; subclínica 100–200k; probable infección ≥300k.
SCC_HEALTHY_MAX = 100_000
SCC_SUBCLINICAL_MAX = 200_000
SCC_INFECTED_MIN = 300_000

# Caída estival por estrés térmico: la bibliografía sitúa la pérdida en ~15% al
# pasar de 18 a 30 °C. Se toma esa magnitud como amplitud pico-valle del ciclo
# anual, con el valle en pleno verano.  [orden de magnitud verificado]
SEASONAL_TROUGH = 0.15
# Día del año del máximo calor (~1 de agosto, hemisferio norte).  [modelado]
SUMMER_PEAK_DOY = 213


def wood_yield_kg(dim: int) -> float:
    """Producción diaria en kg según Wood para el día `dim` de lactación.

    `dim` = *days in milk* (días desde el parto). Fuera del intervalo
    [1, LACTATION_DAYS] la vaca está seca y no produce: devuelve 0.0.
    """
    if dim < 1 or dim > LACTATION_DAYS:
        return 0.0
    return WOOD_A * (dim**WOOD_B) * math.exp(-WOOD_C * dim)


def parity_factor(lactation_number: int) -> float:
    """Factor de producción por número de lactación.

    La bibliografía confirma que la paridad modula la producción (las primíparas
    rinden menos, con pico más bajo y plano), pero sin multiplicador citable:
    estos valores son modelados, no medidos.  [modelado / sin verificar]
    """
    if lactation_number <= 1:
        return 0.75
    if lactation_number == 2:
        return 0.90
    return 1.00


def seasonal_factor(day: date) -> float:
    """Multiplicador estacional en [1 − SEASONAL_TROUGH, 1] según la época del año.

    Coseno anual centrado en el verano: máxima caída en SUMMER_PEAK_DOY, sin
    penalización en pleno invierno.
    """
    doy = day.timetuple().tm_yday
    phase = 2 * math.pi * (doy - SUMMER_PEAK_DOY) / 365
    return 1.0 - SEASONAL_TROUGH * (1 + math.cos(phase)) / 2


def to_liters(kg: float) -> Decimal:
    """Convierte kg de leche a litros (÷densidad) cuantizando a 2 decimales.

    Cuantizar aquí respeta el `DecimalField(max_digits=5, decimal_places=2)` de
    `Milking.liters` y evita sorpresas de redondeo al persistir.
    """
    liters = Decimal(str(kg)) / MILK_DENSITY_KG_PER_L
    return liters.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
