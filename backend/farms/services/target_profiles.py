"""Perfiles de destino comercial: qué leche pide cada comprador.

Catálogo que mantiene la plataforma, no un hecho que entregue ninguna fuente.
Por eso ni el perfil ni sus rangos llevan procedencia, y su carga tiene firma
propia sin carga de ingesta asociada.

Los umbrales son interpretación de esta propuesta, no un requisito de ningún
comprador real: un destino comercial se describe en el sector por raza y manejo
—queso azul de quesería artesana con leche de vaca en pastoreo—, no por umbrales
analíticos, y traducirlo a rangos por analito es la decisión que se modela aquí.
Lo que no se inventa son los números: cada mínimo se deriva del rango publicado
del analito, y lo propio es solo qué fracción de ese rango exige cada perfil.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from farms.services.milk_quality import MILK_ANALYTE_RANGES

# Qué parte alta del rango publicado exige un destino. Es la única cifra propia
# del módulo: gradúa cuán exigente es un perfil, no cuánto vale una leche.  [modelado]
UPPER_HALF = Decimal("0.50")
UPPER_THIRD = Decimal("0.67")


@dataclass(frozen=True, slots=True)
class TargetProfileSpec:
    """Destino comercial y lo que exige de cada analito.

    `demands` lleva el código del analito a la fracción del rango publicado por
    debajo de la cual la leche no sirve para ese destino. Solo hay mínimos: un
    comprador pide al menos tanto de un componente valioso, y ponerle techo a un
    ácido graso sería inventar una exigencia que nadie formula.
    """

    code: str
    name: str
    description: str
    demands: dict[str, Decimal]


TARGET_PROFILES = (
    TargetProfileSpec(
        code="queso-azul-artesano",
        name="Queso azul de quesería artesana",
        description=(
            "Destino de alto valor añadido para leche de base forrajera de hierba. "
            "Exige la mitad alta del rango publicado en los cuatro analitos del "
            "perfil extendido."
        ),
        demands={
            "cla": UPPER_HALF,
            "omega3": UPPER_HALF,
            "beta_caroteno": UPPER_HALF,
            "alfa_tocoferol": UPPER_HALF,
        },
    ),
    TargetProfileSpec(
        code="perfil-graso-diferenciado",
        name="Leche de perfil graso diferenciado",
        description=(
            "Destino que solo mira el perfil de ácidos grasos y exige su tercio "
            "superior. Los antioxidantes no entran, así que un lote puede servir "
            "para este destino y no para uno más completo."
        ),
        demands={"cla": UPPER_THIRD, "omega3": UPPER_THIRD},
    ),
    TargetProfileSpec(
        code="antioxidantes-altos",
        name="Leche rica en antioxidantes liposolubles",
        description=(
            "Destino simétrico al anterior sobre el β-caroteno y el α-tocoferol. "
            "Los tres perfiles se solapan a propósito: lo que responde el catálogo "
            "es a qué destinos puede orientarse un lote, no si aprueba."
        ),
        demands={"beta_caroteno": UPPER_THIRD, "alfa_tocoferol": UPPER_THIRD},
    ),
)


def minimum_values(spec: TargetProfileSpec) -> dict[str, Decimal]:
    """Umbral mínimo de cada analito del perfil, en la unidad del analito.

    Sitúa la fracción exigida dentro del rango publicado, que es el mismo que
    acota lo que puede medir una muestra: así el umbral es siempre alcanzable y
    siempre exigente, sin depender de qué datos haya sembrados.
    """
    return {
        code: _within_published_range(code, fraction) for code, fraction in spec.demands.items()
    }


def _within_published_range(analyte_code: str, fraction: Decimal) -> Decimal:
    """Punto del rango publicado que deja por debajo esa fracción del recorrido."""
    low, high = MILK_ANALYTE_RANGES[analyte_code]
    return (low + (high - low) * fraction).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
