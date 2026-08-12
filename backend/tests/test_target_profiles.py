"""Tests del catálogo de perfiles de destino comercial.

No se comprueba que los umbrales sean los correctos —son una interpretación
declarada, no un hecho verificable—, sino que estén donde el módulo dice: dentro
del rango publicado de su analito y derivados de él, nunca escritos a mano.
"""

from decimal import Decimal

import pytest

from farms.services.milk_quality import MILK_ANALYTE_RANGES, MILK_ANALYTES
from farms.services.target_profiles import (
    TARGET_PROFILES,
    UPPER_HALF,
    UPPER_THIRD,
    TargetProfileSpec,
    minimum_values,
)

CATALOGUE_CODES = {code for code, _, _ in MILK_ANALYTES}


def _profile(code: str) -> TargetProfileSpec:
    return next(spec for spec in TARGET_PROFILES if spec.code == code)


# --- Integridad del catálogo ---


def test_los_codigos_de_perfil_son_unicos():
    """El código es la clave natural con la que se carga y se consulta un perfil."""
    codes = [spec.code for spec in TARGET_PROFILES]

    assert len(codes) == len(set(codes))


def test_todo_analito_exigido_existe_en_el_catalogo_de_leche():
    """Un código mal escrito dejaría el perfil sin ese rango, en silencio."""
    exigidos = {code for spec in TARGET_PROFILES for code in spec.demands}

    assert exigidos <= CATALOGUE_CODES


def test_ningun_perfil_se_queda_sin_exigencias():
    """Un perfil sin rangos lo cumpliría cualquier leche, incluida la que no se midió."""
    assert all(spec.demands for spec in TARGET_PROFILES)


def test_todo_perfil_declara_de_donde_salen_sus_umbrales():
    """La descripción viaja a la API: es donde se lee que el umbral es una decisión."""
    assert all(spec.description.strip() for spec in TARGET_PROFILES)


# --- Los umbrales salen del rango publicado ---


@pytest.mark.parametrize("spec", TARGET_PROFILES, ids=lambda spec: spec.code)
def test_los_umbrales_caen_dentro_del_rango_publicado(spec: TargetProfileSpec):
    """Un mínimo por encima del máximo publicado sería inalcanzable por construcción."""
    for code, minimum in minimum_values(spec).items():
        low, high = MILK_ANALYTE_RANGES[code]
        assert low <= minimum <= high


@pytest.mark.parametrize("spec", TARGET_PROFILES, ids=lambda spec: spec.code)
def test_el_umbral_deja_sitio_por_encima(spec: TargetProfileSpec):
    """Si el mínimo fuese el techo del rango, ninguna muestra podría cumplirlo."""
    for code, minimum in minimum_values(spec).items():
        _, high = MILK_ANALYTE_RANGES[code]
        assert minimum < high


def test_la_mitad_alta_empieza_en_el_punto_medio_del_rango():
    """Ata la fracción a la aritmética del rango, no a un número transcrito."""
    minimos = minimum_values(_profile("queso-azul-artesano"))

    for code, minimum in minimos.items():
        low, high = MILK_ANALYTE_RANGES[code]
        assert minimum == ((low + high) / 2).quantize(Decimal("0.0001"))


def test_exigir_mas_fraccion_sube_el_umbral():
    """La fracción ordena los perfiles: más exigencia, umbral más alto."""
    mitad = minimum_values(_profile("queso-azul-artesano"))
    tercio = minimum_values(_profile("perfil-graso-diferenciado"))

    assert UPPER_THIRD > UPPER_HALF
    assert tercio["cla"] > mitad["cla"]
    assert tercio["omega3"] > mitad["omega3"]


def test_los_umbrales_respetan_la_escala_del_campo():
    """`TargetRange` guarda cuatro decimales: el módulo cuantiza, no confía en el ORM."""
    for spec in TARGET_PROFILES:
        for minimum in minimum_values(spec).values():
            assert minimum == minimum.quantize(Decimal("0.0001"))


def test_un_perfil_parcial_no_exige_los_analitos_que_no_nombra():
    """Los perfiles parciales son lo que hace que la comparación tenga grados."""
    graso = minimum_values(_profile("perfil-graso-diferenciado"))
    antioxidantes = minimum_values(_profile("antioxidantes-altos"))

    assert set(graso) == {"cla", "omega3"}
    assert set(antioxidantes) == {"beta_caroteno", "alfa_tocoferol"}
