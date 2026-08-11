"""Tests del efecto de la ración sobre la calidad de la leche.

No se comprueba que el efecto exista, que es una decisión, sino que esté acotado:
ningún valor fuera del rango publicado y la dirección que declara el módulo.
"""

import random
from decimal import Decimal

import pytest

from farms.services.agronomy import FORAGE_RANGES
from farms.services.milk_quality import (
    MAIZE_STARCH_REFERENCE,
    MILK_ANALYTE_RANGES,
    MILK_ANALYTES,
    SilagePortion,
    grass_forage_share,
    milk_analysis,
)

MAIZE_STARCH_RANGE = FORAGE_RANGES["maize"]["almidon"]


def _rng() -> random.Random:
    return random.Random(42)  # noqa: S311


def _portion(kg: str, starch: str | None) -> SilagePortion:
    return SilagePortion(
        dry_matter_kg=Decimal(kg),
        starch_pct=None if starch is None else Decimal(starch),
    )


# --- La estimación del forraje desde el análisis NIR ---


def test_la_referencia_de_almidon_es_el_punto_medio_del_rango_de_maiz_de_fedna():
    """Ata la constante al rango de FEDNA que ya usa el generador de forrajes."""
    low, high = MAIZE_STARCH_RANGE
    assert (low + high) / 2 == MAIZE_STARCH_REFERENCE


def test_un_forraje_sin_almidon_es_todo_hierba():
    portions = [_portion("6.00", None), _portion("6.00", None)]

    assert grass_forage_share(portions) == Decimal("1")


def test_un_maiz_rico_en_almidon_deja_la_fraccion_de_hierba_en_cero():
    _, high = MAIZE_STARCH_RANGE
    portions = [_portion("12.00", str(high))]

    assert grass_forage_share(portions) == Decimal("0")


def test_una_mezcla_de_maiz_y_hierba_cae_estrictamente_entre_los_extremos():
    portions = [_portion("6.00", "22.25"), _portion("6.00", None)]

    share = grass_forage_share(portions)

    assert Decimal("0") < share < Decimal("1")


def test_la_fraccion_de_hierba_se_pondera_por_materia_seca():
    """Dos raciones con los mismos silos y distinto reparto no son iguales."""
    poco_maiz = [_portion("2.00", "22.25"), _portion("10.00", None)]
    mucho_maiz = [_portion("10.00", "22.25"), _portion("2.00", None)]

    assert grass_forage_share(poco_maiz) > grass_forage_share(mucho_maiz)


def test_mas_almidon_es_siempre_menos_hierba():
    valores = [Decimal("0"), Decimal("8.00"), Decimal("15.00"), Decimal("22.25")]

    shares = [grass_forage_share([_portion("12.00", str(v))]) for v in valores]

    assert shares == sorted(shares, reverse=True)


def test_una_racion_sin_forraje_analizado_es_un_error_explicito():
    with pytest.raises(ValueError, match="sin forraje analizado"):
        grass_forage_share([])


def test_una_racion_con_forraje_de_materia_seca_nula_tambien_lo_es():
    with pytest.raises(ValueError, match="sin forraje analizado"):
        grass_forage_share([_portion("0.00", "20.00")])


# --- Los analitos de la muestra de leche ---


def test_la_muestra_trae_los_cuatro_analitos_del_catalogo():
    resultados = milk_analysis(_rng(), Decimal("0.5"))

    assert set(resultados) == {code for code, _, _ in MILK_ANALYTES}


@pytest.mark.parametrize("share", ["0", "0.25", "0.5", "0.75", "1"])
def test_ningun_valor_cae_fuera_del_rango_publicado(share: str):
    """Es el mismo compromiso que el generador mantiene con las tablas de FEDNA."""
    rng = _rng()

    for _ in range(500):
        for code, value in milk_analysis(rng, Decimal(share)).items():
            low, high = MILK_ANALYTE_RANGES[code]
            assert low <= value <= high, f"{code} fuera de rango con hierba={share}"


def test_los_cuatro_analitos_suben_con_la_proporcion_de_hierba():
    """La dirección del efecto es la que declara el docstring del módulo."""
    maiz = _medias(Decimal("0"))
    hierba = _medias(Decimal("1"))

    for code, _, _ in MILK_ANALYTES:
        assert hierba[code] > maiz[code], f"{code} no sube con la hierba"


def test_el_efecto_es_monotono_y_no_solo_distinto_en_los_extremos():
    medias = [_medias(Decimal(str(share))) for share in (0.0, 0.25, 0.5, 0.75, 1.0)]

    for code, _, _ in MILK_ANALYTES:
        serie = [tramo[code] for tramo in medias]
        assert serie == sorted(serie), f"{code} no crece de forma monótona"


def test_misma_semilla_y_mismo_forraje_dan_la_misma_muestra():
    assert milk_analysis(_rng(), Decimal("0.4")) == milk_analysis(_rng(), Decimal("0.4"))


def test_muestras_sucesivas_del_mismo_forraje_no_son_identicas():
    """Sin dispersión de muestreo la serie sería una escalera perfecta."""
    rng = _rng()

    primera = milk_analysis(rng, Decimal("0.5"))
    segunda = milk_analysis(rng, Decimal("0.5"))

    assert primera != segunda


def test_los_valores_respetan_la_escala_de_dos_decimales():
    """`AnalysisResult.value` admite cuatro, pero un laboratorio informa de dos."""
    for value in milk_analysis(_rng(), Decimal("0.6")).values():
        assert value == value.quantize(Decimal("0.01"))


def _medias(share: Decimal) -> dict[str, Decimal]:
    """Media de cada analito sobre muchas muestras del mismo forraje."""
    rng = _rng()
    muestras = [milk_analysis(rng, share) for _ in range(300)]
    return {
        code: sum((m[code] for m in muestras), Decimal("0")) / len(muestras)
        for code, _, _ in MILK_ANALYTES
    }
