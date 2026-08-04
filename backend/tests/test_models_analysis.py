"""Tests de la analítica multiparamétrica y de los perfiles de destino comercial.

Fijan las dos decisiones que sostienen el bloque: que un mismo par
muestra/resultado sirva para el forraje y para la leche, y que el catálogo de
analitos no guarde criterio —qué valor es deseable depende del destino, no del
esquema—.
"""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

from farms.models import (
    AnalysisResult,
    Analyte,
    BatchMilkSample,
    TargetProfile,
    TargetRange,
)


@pytest.mark.django_db
def test_analyte_str_incluye_la_unidad(analyte):
    """Un valor analítico sin unidad no se puede interpretar."""
    assert str(analyte) == "Materia seca (%)"


@pytest.mark.django_db
def test_analyte_code_es_unico(analyte):
    """El código identifica el analito frente a fuentes externas."""
    with pytest.raises(IntegrityError):
        Analyte.objects.create(code="dry-matter", name="Otro nombre", unit="g/kg")


@pytest.mark.django_db
def test_analyte_no_guarda_rangos_de_referencia(analyte):
    """El catálogo aporta identidad y unidad, nunca criterio.

    Guardar aquí un rango "normal" obligaría a afirmar qué valor es bueno con
    independencia del destino comercial, que es justo lo que el proyecto no puede
    inventarse. Los rangos viven en `TargetRange`, colgando de un perfil.
    """
    campos = {field.name for field in Analyte._meta.fields}

    assert campos == {"id", "code", "name", "unit"}


@pytest.mark.django_db
def test_una_muestra_de_leche_por_lote_y_fecha(milk_sample, batch):
    """El unique da idempotencia a la ingesta del laboratorio."""
    with pytest.raises(IntegrityError):
        BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 2, 10))


@pytest.mark.django_db
def test_muestra_de_leche_str_identifica_lote_y_fecha(milk_sample):
    """La muestra se lee por el lote al que pertenece, que es la unidad de tratamiento."""
    assert str(milk_sample) == "Alta producción · muestra 2026-02-10"


@pytest.mark.django_db
def test_el_mismo_analito_sirve_para_forraje_y_para_leche(analyte, nir_analysis, milk_sample):
    """La razón de ser de la decisión de analítica híbrida.

    Un único catálogo y un único modelo de resultado cubren las dos mitades del
    hilo. Si forraje y leche tuvieran esquemas separados, esta prueba exigiría
    duplicar catálogo, modelo y serializers.
    """
    AnalysisResult.objects.create(
        nir_analysis=nir_analysis, analyte=analyte, value=Decimal("32.5000")
    )
    AnalysisResult.objects.create(
        milk_sample=milk_sample, analyte=analyte, value=Decimal("12.8000")
    )

    assert analyte.results.count() == 2


@pytest.mark.django_db
def test_resultado_rechaza_las_dos_muestras_a_la_vez(analyte, nir_analysis, milk_sample):
    """El XOR es el mismo patrón que en los ingredientes de la ración."""
    with pytest.raises(IntegrityError):
        AnalysisResult.objects.create(
            nir_analysis=nir_analysis,
            milk_sample=milk_sample,
            analyte=analyte,
            value=Decimal("1.0000"),
        )


@pytest.mark.django_db
def test_resultado_rechaza_quedarse_sin_muestra(analyte):
    """Un valor sin muestra de la que proceda no es trazable."""
    with pytest.raises(IntegrityError):
        AnalysisResult.objects.create(analyte=analyte, value=Decimal("1.0000"))


@pytest.mark.django_db
def test_un_analito_no_se_repite_en_la_misma_muestra(analyte, nir_analysis):
    """Dos valores del mismo parámetro en una muestra serían una carga duplicada."""
    AnalysisResult.objects.create(
        nir_analysis=nir_analysis, analyte=analyte, value=Decimal("32.5000")
    )

    with pytest.raises(IntegrityError):
        AnalysisResult.objects.create(
            nir_analysis=nir_analysis, analyte=analyte, value=Decimal("30.0000")
        )


@pytest.mark.django_db
def test_los_resultados_se_borran_con_su_analisis(analyte, nir_analysis):
    """Un resultado sin su muestra no significa nada: CASCADE hacia la muestra."""
    AnalysisResult.objects.create(
        nir_analysis=nir_analysis, analyte=analyte, value=Decimal("32.5000")
    )

    nir_analysis.delete()

    assert AnalysisResult.objects.count() == 0


@pytest.mark.django_db
def test_no_se_puede_borrar_un_analito_con_resultados(analyte, nir_analysis):
    """PROTECT hacia el catálogo: borrarlo dejaría el histórico sin interpretar."""
    AnalysisResult.objects.create(
        nir_analysis=nir_analysis, analyte=analyte, value=Decimal("32.5000")
    )

    with pytest.raises(ProtectedError):
        analyte.delete()


@pytest.mark.django_db
def test_target_profile_str_es_el_nombre_comercial():
    """El perfil se nombra por su destino, que es como lo pide el ganadero."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")

    assert str(perfil) == "Queso azul artesano"


@pytest.mark.django_db
def test_el_perfil_de_destino_no_pertenece_a_una_explotacion():
    """Es catálogo global: lo que exige un comprador es un hecho de mercado.

    Cada ganadería o lote lo cumple o no lo cumple, pero el patrón es el mismo
    para todas, y eso es lo que permitiría compararlas entre socios.
    """
    campos = {field.name for field in TargetProfile._meta.fields}

    assert campos == {"id", "code", "name", "description"}


@pytest.mark.django_db
def test_rango_admite_un_solo_extremo(analyte):
    """Un destino puede exigir solo un mínimo, o solo un máximo."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")

    solo_minimo = TargetRange.objects.create(
        profile=perfil, analyte=analyte, min_value=Decimal("3.5000")
    )

    assert solo_minimo.max_value is None


@pytest.mark.django_db
def test_rango_rechaza_quedarse_sin_extremos(analyte):
    """Un rango sin mínimo ni máximo no expresa exigencia y ensuciaría la comparación."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")

    with pytest.raises(IntegrityError):
        TargetRange.objects.create(profile=perfil, analyte=analyte)


@pytest.mark.django_db
def test_rango_rechaza_un_maximo_menor_que_el_minimo(analyte):
    """Restricción aritmética: se prohíbe lo imposible, no lo improbable."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")

    with pytest.raises(IntegrityError):
        TargetRange.objects.create(
            profile=perfil,
            analyte=analyte,
            min_value=Decimal("4.0000"),
            max_value=Decimal("3.0000"),
        )


@pytest.mark.django_db
def test_un_analito_no_se_repite_dentro_de_un_perfil(analyte):
    """Dos exigencias sobre el mismo parámetro serían contradictorias o redundantes."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")
    TargetRange.objects.create(profile=perfil, analyte=analyte, min_value=Decimal("3.5000"))

    with pytest.raises(IntegrityError):
        TargetRange.objects.create(profile=perfil, analyte=analyte, max_value=Decimal("5.0000"))


@pytest.mark.django_db
def test_borrar_un_perfil_arrastra_sus_rangos(analyte):
    """Los rangos no tienen sentido fuera de su perfil: CASCADE."""
    perfil = TargetProfile.objects.create(code="queso-azul", name="Queso azul artesano")
    TargetRange.objects.create(profile=perfil, analyte=analyte, min_value=Decimal("3.5000"))

    perfil.delete()

    assert TargetRange.objects.count() == 0
