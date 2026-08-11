"""Efecto de la composición de la ración sobre la calidad de la leche del lote.

Único sitio del proyecto donde dos series se relacionan a propósito: lo que sale
de aquí es una construcción, no un hallazgo. La dirección del efecto y el rango
de cada analito están publicados; la forma de interpolar entre ellos, modelada.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# --- El perfil extendido: dos ácidos grasos y dos antioxidantes liposolubles ---

MILK_ANALYTES = (
    ("cla", "Ácido linoleico conjugado (c9,t11)", "% de AG totales"),
    ("omega3", "Ácido α-linolénico (C18:3 n-3)", "% de AG totales"),
    ("beta_caroteno", "β-caroteno", "µg/g de grasa"),
    ("alfa_tocoferol", "α-tocoferol", "µg/g de grasa"),
)

# Los cuatro suben con la proporción de hierba del forraje: el ensilado de hierba
# aporta C18:3, tocoferol y caroteno donde el de maíz aporta C18:2 (Wang et al.,
# Foods 12(2):303, 2023).  [dirección verificada]

# Rangos publicados para leche de vaca; el generador no sale de ellos y la ración
# solo decide en qué punto de cada rango cae la muestra.
#   cla             0,31-0,69 (White et al., J. Dairy Sci. 84(10):2295, 2001) y
#                   0,99-2,01 (Șanta et al., Animals 12(7):908, 2022). Se toma la
#                   unión: el nivel varía entre estudios, la dirección no.
#   omega3          0,58-1,33 (Șanta et al., 2022).
#   beta_caroteno   0,8-9,7 y
#   alfa_tocoferol  11,2-16,2, por estación de pastoreo (Dairy Sci. Technol.,
#                   doi 10.1007/s13594-012-0069-2, 2012).
# Los antioxidantes van en µg/g de grasa porque las fuentes difieren unas
# cincuenta veces al pasarlos a µg/100 g de leche. Y todos los rangos son del
# contraste entre pasto y ración completa, más ancho que el contraste entre
# ensilados que aquí se modela: el efecto queda exagerado para verse en una
# gráfica.
MILK_ANALYTE_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "cla": (Decimal("0.31"), Decimal("2.01")),
    "omega3": (Decimal("0.58"), Decimal("1.33")),
    "beta_caroteno": (Decimal("0.80"), Decimal("9.70")),
    "alfa_tocoferol": (Decimal("11.20"), Decimal("16.20")),
}

# Punto medio del rango de almidón que FEDNA publica para el ensilado de maíz
# (10,3-34,2 % MS) y que ya usa el generador de forrajes. Equiparar almidón alto
# a maíz es interpretación propia: la literatura contrasta especies forrajeras.
MAIZE_STARCH_REFERENCE = Decimal("22.25")

# Dispersión entre muestras del mismo lote y del método analítico, aplicada sobre
# la posición dentro del rango.  [modelado]
SAMPLING_SIGMA = 0.06

# Nombre genérico: no se atribuye la analítica a ningún laboratorio real.
MILK_LABORATORY = "Laboratorio de análisis de leche"


@dataclass(frozen=True, slots=True)
class SilagePortion:
    """Aportación de un silo a una ración: su materia seca y el almidón del NIR.

    `starch_pct` nulo es un forraje que no lo determina, que es la señal de que
    no es maíz.
    """

    dry_matter_kg: Decimal
    starch_pct: Decimal | None


def grass_forage_share(portions: Sequence[SilagePortion]) -> Decimal:
    """Fracción del forraje de la ración que no es maíz, estimada desde el NIR.

    El almidón discrimina: los ensilados de hierba y de raigrás no lo determinan
    y el de maíz lo tiene en cantidad. Solo entran los silos — las materias
    primas compradas no llevan análisis, así que su almidón no se supone.
    """
    total_kg = sum((portion.dry_matter_kg for portion in portions), Decimal("0"))
    if total_kg <= 0:
        raise ValueError("una ración sin forraje analizado no permite estimar su composición")
    starch = (
        sum(
            (portion.dry_matter_kg * (portion.starch_pct or Decimal("0")) for portion in portions),
            Decimal("0"),
        )
        / total_kg
    )
    return _clamp(Decimal("1") - starch / MAIZE_STARCH_REFERENCE)


def milk_analysis(rng: random.Random, grass_share: Decimal) -> dict[str, Decimal]:
    """Analitos de una muestra de leche de lote para un forraje dado.

    Cada valor cae dentro de su rango publicado en proporción a `grass_share`,
    con dispersión de muestreo. Los códigos son los del modelo, no los de un
    laboratorio: traducirlos es trabajo del adaptador.
    """
    return {
        code: _sample_within(rng, MILK_ANALYTE_RANGES[code], grass_share)
        for code, _, _ in MILK_ANALYTES
    }


def _sample_within(
    rng: random.Random, bounds: tuple[Decimal, Decimal], position: Decimal
) -> Decimal:
    """Sitúa un valor dentro del rango según `position`, con ruido de muestreo.

    El ruido va sobre la posición y no sobre el valor, de modo que ningún
    resultado puede caer fuera del rango publicado.
    """
    low, high = bounds
    jittered = _clamp(Decimal(str(round(float(position) + rng.gauss(0.0, SAMPLING_SIGMA), 4))))
    return (low + (high - low) * jittered).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal) -> Decimal:
    """Acota al intervalo [0, 1], donde viven las posiciones de este módulo."""
    return min(max(value, Decimal("0")), Decimal("1"))
