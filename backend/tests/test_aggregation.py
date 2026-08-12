"""Tests de los servicios de agregación.

Los valores se comprueban contra números concretos y en `Decimal`: un agregado
mal construido sigue devolviendo un número plausible, y solo un valor esperado
lo delata. El caso que gobierna este fichero es el producto cartesiano — dos
relaciones multivaluadas anotadas sobre el mismo queryset multiplican una serie
por el número de filas de la otra.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import Animal, DailyYield, Farm, MilkRecord
from farms.services.aggregation import farm_summaries


@pytest.fixture
def serie(animal):
    """Dos días de producción y tres controles del mismo animal.

    La asimetría es deliberada: si producción y calidad se anotasen sobre el
    mismo queryset, el JOIN daría seis filas y los 30 litros pasarían a 90.
    """
    for day, liters in ((1, "10.00"), (2, "20.00")):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            liters=Decimal(liters),
        )
    for day, scc in ((1, 100_000), (2, 500_000), (3, 900_000)):
        MilkRecord.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            fat_pct=Decimal("4.00"),
            protein_pct=Decimal("3.00"),
            somatic_cell_count=scc,
        )
    return animal


@pytest.mark.django_db
def test_el_total_de_litros_no_lo_multiplican_los_controles(serie):
    """El total es la suma de la producción, no su producto por la calidad."""
    resumen = farm_summaries().get()

    assert resumen.total_liters == Decimal("30.00")


@pytest.mark.django_db
def test_la_media_diaria_es_por_registro_de_produccion(serie):
    """La media reparte los litros entre los días medidos, no entre los controles."""
    resumen = farm_summaries().get()

    assert resumen.avg_daily_liters == Decimal("15")


@pytest.mark.django_db
def test_las_medias_de_calidad_no_las_diluye_la_produccion(serie):
    """La calidad se promedia sobre los controles, ajenos a cuántos días se ordeñó."""
    resumen = farm_summaries().get()

    assert resumen.avg_fat_pct == Decimal("4")
    assert resumen.avg_protein_pct == Decimal("3")


@pytest.mark.django_db
def test_el_conteo_de_celulas_somaticas_usa_el_limite_legal(serie):
    """Solo cuenta lo que supera el límite: 100.000 queda fuera; 500.000 y 900.000, dentro."""
    resumen = farm_summaries().get()

    assert MilkRecord.LEGAL_SCC_LIMIT == 400_000
    assert resumen.scc_over_limit == 2


@pytest.mark.django_db
def test_un_control_justo_en_el_limite_no_cuenta(animal):
    """El umbral es estricto: 400.000 es el máximo legal, no una infracción."""
    MilkRecord.objects.create(
        animal=animal,
        date=datetime.date(2026, 3, 1),
        somatic_cell_count=MilkRecord.LEGAL_SCC_LIMIT,
    )

    resumen = farm_summaries().get()

    assert resumen.scc_over_limit == 0


@pytest.mark.django_db
def test_la_ventana_de_fechas_acota_las_series(serie):
    """Con la ventana en el día 1 solo entran ese día de producción y ese control."""
    resumen = farm_summaries(
        date_from=datetime.date(2026, 3, 1),
        date_to=datetime.date(2026, 3, 1),
    ).get()

    assert resumen.total_liters == Decimal("10.00")
    assert resumen.scc_over_limit == 0


@pytest.mark.django_db
def test_los_extremos_de_la_ventana_son_independientes(serie):
    """Solo `date_from` deja la serie abierta por la derecha."""
    resumen = farm_summaries(date_from=datetime.date(2026, 3, 2)).get()

    assert resumen.total_liters == Decimal("20.00")


@pytest.mark.django_db
def test_la_ventana_incluye_sus_dos_extremos(serie):
    """El rango es cerrado, como los periodos de vigencia del modelo."""
    resumen = farm_summaries(
        date_from=datetime.date(2026, 3, 1),
        date_to=datetime.date(2026, 3, 2),
    ).get()

    assert resumen.total_liters == Decimal("30.00")


@pytest.mark.django_db
def test_sin_dato_en_la_ventana_la_metrica_es_nula_y_no_cero(serie):
    """`None` es "no medido" y cero sería una lectura: la distinción se conserva."""
    resumen = farm_summaries(date_from=datetime.date(2026, 12, 1)).get()

    assert resumen.total_liters is None
    assert resumen.avg_fat_pct is None
    assert resumen.scc_over_limit is None


@pytest.mark.django_db
def test_la_ventana_no_acota_el_censo(serie):
    """Cuántos animales hay es una pregunta sin fecha: la ventana no la toca."""
    resumen = farm_summaries(date_from=datetime.date(2026, 12, 1)).get()

    assert resumen.active_animals == 1


@pytest.mark.django_db
def test_el_censo_excluye_a_los_animales_de_baja(farm, animal):
    """La baja se representa por `culled_date`, no por un campo de estado."""
    Animal.objects.create(
        farm=farm,
        ear_tag="ES221100010002",
        birth_date=datetime.date(2021, 3, 1),
        culled_date=datetime.date(2026, 1, 10),
    )

    resumen = farm_summaries().get()

    assert resumen.active_animals == 1


@pytest.mark.django_db
def test_los_litros_de_una_explotacion_no_se_le_suman_a_otra(serie):
    """Cada subconsulta está correlacionada con la fila externa que anota."""
    otra = Farm.objects.create(
        name="Souto Vello",
        code="souto-vello",
        municipality="Chantada",
        province="Lugo",
    )

    resumenes = {resumen.code: resumen for resumen in farm_summaries()}

    assert resumenes["casa-grande"].total_liters == Decimal("30.00")
    assert resumenes[otra.code].total_liters is None
    assert resumenes[otra.code].active_animals == 0


@pytest.mark.django_db
def test_los_nulos_no_entran_en_la_media_ni_en_el_total(animal):
    """Un día sin lectura no baja la media: la media es de lo medido."""
    DailyYield.objects.create(
        animal=animal,
        date=datetime.date(2026, 3, 1),
        liters=Decimal("10.00"),
    )
    DailyYield.objects.create(animal=animal, date=datetime.date(2026, 3, 2), liters=None)

    resumen = farm_summaries().get()

    assert resumen.total_liters == Decimal("10.00")
    assert resumen.avg_daily_liters == Decimal("10")


@pytest.mark.django_db
def test_las_seis_metricas_salen_en_una_sola_consulta(serie, django_assert_num_queries):
    """Las subconsultas viajan dentro del SELECT: no hay una consulta por fila."""
    with django_assert_num_queries(1):
        list(farm_summaries())


@pytest.mark.django_db
def test_el_resumen_no_consulta_al_construirlo(django_assert_num_queries):
    """La función devuelve un QuerySet perezoso: la vista aún puede filtrarlo."""
    with django_assert_num_queries(0):
        farm_summaries(date_from=datetime.date(2026, 3, 1))
