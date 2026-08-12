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

from farms.models import (
    AnalysisResult,
    Animal,
    AnimalBatchMembership,
    BatchMilkSample,
    BatchRation,
    DailyYield,
    Farm,
    MilkRecord,
)
from farms.services.aggregation import (
    batch_daily_yields,
    batch_milk_samples,
    batch_ration_periods,
    batch_summary,
    batch_timeline,
    farm_summaries,
)


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


@pytest.fixture
def lote_poblado(batch, animal, farm):
    """Un animal en el lote desde el 5 de marzo, con producción antes y después.

    El animal existe desde antes de entrar al lote a propósito: lo que el
    resumen del lote tiene que contar son los días de pertenencia, no la serie
    completa del animal.
    """
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 5),
    )
    for day, liters in ((3, "10.00"), (5, "20.00"), (7, "30.00")):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            liters=Decimal(liters),
        )
    return batch


@pytest.mark.django_db
def test_el_lote_solo_cuenta_los_dias_de_pertenencia(lote_poblado):
    """Los 10 litros del día 3 son del animal, pero todavía no del lote."""
    resumen = batch_summary(lote_poblado)

    assert resumen["total_liters"] == Decimal("50.00")


@pytest.mark.django_db
def test_el_dia_de_alta_en_el_lote_ya_cuenta(lote_poblado):
    """El periodo es cerrado por la izquierda: el 5 de marzo entra."""
    resumen = batch_summary(
        lote_poblado,
        date_from=datetime.date(2026, 3, 5),
        date_to=datetime.date(2026, 3, 5),
    )

    assert resumen["total_liters"] == Decimal("20.00")


@pytest.mark.django_db
def test_lo_producido_tras_salir_del_lote_deja_de_contar(batch, animal):
    """Cerrar la pertenencia corta la serie del lote, no la del animal."""
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 1),
        date_to=datetime.date(2026, 3, 5),
    )
    for day, liters in ((4, "10.00"), (6, "40.00")):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            liters=Decimal(liters),
        )

    resumen = batch_summary(batch)

    assert resumen["total_liters"] == Decimal("10.00")
    assert resumen["active_animals"] == 0


@pytest.mark.django_db
def test_dos_pertenencias_disjuntas_no_duplican_los_litros(batch, animal):
    """Un animal que va y vuelve al lote no cuenta dos veces.

    El JOIN produce una fila por pertenencia; que sobreviva solo una la
    garantiza el no-solape de los periodos. Si ese invariante se rompiera, este
    test avisaría antes que ningún otro.
    """
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 1, 1),
        date_to=datetime.date(2026, 1, 31),
    )
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 1),
    )
    DailyYield.objects.create(
        animal=animal,
        date=datetime.date(2026, 1, 15),
        liters=Decimal("25.00"),
    )

    resumen = batch_summary(batch)

    assert resumen["total_liters"] == Decimal("25.00")


@pytest.mark.django_db
def test_los_controles_del_lote_usan_el_mismo_limite_legal(batch, animal):
    """La alerta de células somáticas es la misma en lote y en explotación."""
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 1),
    )
    for day, scc in ((1, 300_000), (2, 800_000)):
        MilkRecord.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            fat_pct=Decimal("4.00"),
            somatic_cell_count=scc,
        )

    resumen = batch_summary(batch)

    assert resumen["milk_records"] == 2
    assert resumen["scc_over_limit"] == 1


@pytest.mark.django_db
def test_un_lote_sin_controles_declara_el_denominador(batch):
    """Cero de cero no puede leerse como "ninguno supera el límite"."""
    resumen = batch_summary(batch)

    assert resumen["milk_records"] == 0
    assert resumen["scc_over_limit"] == 0
    assert resumen["avg_fat_pct"] is None


@pytest.mark.django_db
def test_los_analitos_del_lote_salen_promediados_con_su_unidad(batch, analyte, milk_sample):
    """Cada analito viaja con su nombre, su unidad y sobre cuántas muestras se calcula."""
    otra_muestra = BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 3, 10))
    AnalysisResult.objects.create(
        milk_sample=milk_sample,
        analyte=analyte,
        value=Decimal("10.0000"),
    )
    AnalysisResult.objects.create(
        milk_sample=otra_muestra,
        analyte=analyte,
        value=Decimal("20.0000"),
    )

    analitos = list(batch_summary(batch)["milk_analytes"])

    assert len(analitos) == 1
    assert analitos[0]["analyte__code"] == "dry-matter"
    assert analitos[0]["analyte__unit"] == "%"
    assert analitos[0]["avg_value"] == Decimal("15")
    assert analitos[0]["samples"] == 2


@pytest.mark.django_db
def test_los_resultados_de_forraje_no_se_cuelan_entre_los_de_leche(
    batch, analyte, milk_sample, nir_analysis
):
    """`AnalysisResult` guarda dos matrices; el JOIN por lote solo alcanza a una."""
    AnalysisResult.objects.create(
        milk_sample=milk_sample,
        analyte=analyte,
        value=Decimal("10.0000"),
    )
    AnalysisResult.objects.create(
        nir_analysis=nir_analysis,
        analyte=analyte,
        value=Decimal("900.0000"),
    )

    analitos = list(batch_summary(batch)["milk_analytes"])

    assert analitos[0]["samples"] == 1
    assert analitos[0]["avg_value"] == Decimal("10")


@pytest.mark.django_db
def test_la_ventana_acota_los_analitos_por_la_fecha_de_la_muestra(batch, analyte, milk_sample):
    """La muestra se fecha en `BatchMilkSample`, no en el resultado."""
    AnalysisResult.objects.create(
        milk_sample=milk_sample,
        analyte=analyte,
        value=Decimal("10.0000"),
    )

    analitos = list(batch_summary(batch, date_from=datetime.date(2026, 6, 1))["milk_analytes"])

    assert analitos == []


# --- La serie temporal del lote ---


def _segundo_animal(farm) -> Animal:
    return Animal.objects.create(
        farm=farm,
        ear_tag="ES221100010002",
        birth_date=datetime.date(2021, 3, 1),
    )


@pytest.mark.django_db
def test_la_serie_diaria_solo_cubre_los_dias_de_pertenencia(lote_poblado):
    """El día 3 el animal producía, pero todavía no para este lote."""
    serie = list(batch_daily_yields(lote_poblado))

    assert [punto["date"].day for punto in serie] == [5, 7]
    assert [punto["total_liters"] for punto in serie] == [Decimal("20.00"), Decimal("30.00")]


@pytest.mark.django_db
def test_la_serie_agrupa_por_dia_y_no_por_animal(batch, animal, farm):
    """`DailyYield` ordena por `-date, animal`, y ese orden entra en el GROUP BY.

    Sin limpiarlo, dos vacas del mismo día saldrían como dos puntos de la serie
    en vez de sumarse en uno.
    """
    otro = _segundo_animal(farm)
    dia = datetime.date(2026, 3, 5)
    for vaca, liters in ((animal, "20.00"), (otro, "30.00")):
        AnimalBatchMembership.objects.create(animal=vaca, batch=batch, date_from=dia)
        DailyYield.objects.create(animal=vaca, date=dia, liters=Decimal(liters))

    serie = list(batch_daily_yields(batch))

    assert len(serie) == 1
    assert serie[0]["total_liters"] == Decimal("50.00")
    assert serie[0]["avg_liters"] == Decimal("25")
    assert serie[0]["animals"] == 2


@pytest.mark.django_db
def test_la_serie_declara_cuantos_animales_sostienen_cada_dia(lote_poblado):
    """Sin el censo diario, una caída por bajas se leería como una de rendimiento."""
    serie = list(batch_daily_yields(lote_poblado))

    assert [punto["animals"] for punto in serie] == [1, 1]


@pytest.mark.django_db
def test_la_serie_diaria_va_hacia_adelante(lote_poblado):
    """El `Meta` del modelo ordena de más reciente a más antigua; una serie no."""
    serie = list(batch_daily_yields(lote_poblado))

    assert [punto["date"] for punto in serie] == sorted(punto["date"] for punto in serie)


@pytest.mark.django_db
def test_la_ventana_acota_la_serie_diaria(lote_poblado):
    serie = list(batch_daily_yields(lote_poblado, date_from=datetime.date(2026, 3, 6)))

    assert [punto["date"].day for punto in serie] == [7]


@pytest.mark.django_db
def test_las_muestras_de_leche_traen_sus_analitos(batch, analyte, milk_sample):
    AnalysisResult.objects.create(
        milk_sample=milk_sample, analyte=analyte, value=Decimal("35.0000")
    )

    muestras = list(batch_milk_samples(batch))

    assert len(muestras) == 1
    resultados = list(muestras[0].results.all())
    assert [(r.analyte.code, r.value) for r in resultados] == [("dry-matter", Decimal("35.0000"))]


@pytest.mark.django_db
def test_las_muestras_van_de_mas_antigua_a_mas_reciente(batch, milk_sample):
    """`BatchMilkSample.Meta` ordena por `-date`: una serie temporal no puede."""
    BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 1, 10))

    fechas = [muestra.date for muestra in batch_milk_samples(batch)]

    assert fechas == sorted(fechas)


@pytest.mark.django_db
def test_la_ventana_acota_las_muestras_por_su_fecha(batch, milk_sample):
    BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 1, 10))

    muestras = list(batch_milk_samples(batch, date_from=datetime.date(2026, 2, 1)))

    assert [muestra.date for muestra in muestras] == [datetime.date(2026, 2, 10)]


@pytest.mark.django_db
def test_las_muestras_no_consultan_una_vez_por_resultado(
    batch, analyte, milk_sample, django_assert_num_queries
):
    """El `prefetch_related` fija el coste: dos consultas, haya las muestras que haya."""
    AnalysisResult.objects.create(
        milk_sample=milk_sample, analyte=analyte, value=Decimal("35.0000")
    )
    otra = BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 1, 10))
    AnalysisResult.objects.create(milk_sample=otra, analyte=analyte, value=Decimal("31.0000"))

    with django_assert_num_queries(2):
        [list(muestra.results.all()) for muestra in batch_milk_samples(batch)]


# --- Los periodos de ración, recortados a la ventana ---


@pytest.fixture
def racion_larga(batch, ration):
    """Un periodo que empieza antes de cualquier ventana y sigue vigente."""
    return BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 1, 1),
    )


@pytest.mark.django_db
def test_un_periodo_que_empieza_antes_se_recorta_al_inicio_de_la_ventana(racion_larga):
    """La banda no puede arrancar fuera del eje que va a pintarse."""
    periodo = batch_ration_periods(
        racion_larga.batch,
        datetime.date(2026, 3, 1),
        datetime.date(2026, 3, 31),
    ).get()

    assert periodo.starts_on == datetime.date(2026, 3, 1)
    assert periodo.date_from == datetime.date(2026, 1, 1)


@pytest.mark.django_db
def test_un_periodo_vigente_se_cierra_en_el_fin_de_la_ventana(racion_larga):
    """`date_to` nulo no es una fecha, y una banda necesita dos."""
    periodo = batch_ration_periods(
        racion_larga.batch,
        datetime.date(2026, 3, 1),
        datetime.date(2026, 3, 31),
    ).get()

    assert periodo.ends_on == datetime.date(2026, 3, 31)
    assert periodo.date_to is None


@pytest.mark.django_db
def test_un_periodo_contenido_en_la_ventana_no_se_toca(batch, ration):
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 3, 10),
        date_to=datetime.date(2026, 3, 20),
    )

    periodo = batch_ration_periods(
        batch, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
    ).get()

    assert periodo.starts_on == datetime.date(2026, 3, 10)
    assert periodo.ends_on == datetime.date(2026, 3, 20)


@pytest.mark.django_db
def test_un_periodo_anterior_a_la_ventana_no_aparece(batch, ration):
    """Solape, no pertenencia: lo que acabó antes de empezar la gráfica no se pinta."""
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 1, 1),
        date_to=datetime.date(2026, 2, 1),
    )

    periodos = batch_ration_periods(batch, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))

    assert list(periodos) == []


@pytest.mark.django_db
def test_un_periodo_posterior_a_la_ventana_no_aparece(batch, ration):
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 5, 1),
    )

    periodos = batch_ration_periods(batch, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31))

    assert list(periodos) == []


@pytest.mark.django_db
def test_un_periodo_que_solo_toca_el_extremo_de_la_ventana_sigue_contando(batch, ration):
    """Los intervalos son cerrados: compartir un solo día ya es solape."""
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 1, 1),
        date_to=datetime.date(2026, 3, 1),
    )

    periodo = batch_ration_periods(
        batch, datetime.date(2026, 3, 1), datetime.date(2026, 3, 31)
    ).get()

    assert periodo.starts_on == periodo.ends_on == datetime.date(2026, 3, 1)


# --- El ensamblado de la serie ---


@pytest.mark.django_db
def test_la_serie_completa_trae_las_tres_colecciones_y_su_ventana(lote_poblado, ration):
    BatchRation.objects.create(
        batch=lote_poblado,
        ration=ration,
        date_from=datetime.date(2026, 1, 1),
    )

    timeline = batch_timeline(lote_poblado)

    assert timeline["window"] == {
        "date_from": datetime.date(2026, 3, 5),
        "date_to": datetime.date(2026, 3, 7),
    }
    assert len(timeline["daily_yields"]) == 2
    assert [p.starts_on for p in timeline["ration_periods"]] == [datetime.date(2026, 3, 5)]
    assert [p.ends_on for p in timeline["ration_periods"]] == [datetime.date(2026, 3, 7)]


@pytest.mark.django_db
def test_la_ventana_efectiva_sale_de_la_produccion_y_no_de_lo_pedido(lote_poblado):
    """Se pide marzo entero y el lote solo tiene datos del 5 al 7: manda el dato."""
    timeline = batch_timeline(
        lote_poblado,
        date_from=datetime.date(2026, 3, 1),
        date_to=datetime.date(2026, 3, 31),
    )

    assert timeline["window"]["date_from"] == datetime.date(2026, 3, 5)
    assert timeline["window"]["date_to"] == datetime.date(2026, 3, 7)


@pytest.mark.django_db
def test_un_lote_sin_produccion_no_devuelve_bandas_sin_recortar(batch, ration):
    """Sin eje temporal no hay dónde dibujar, y un periodo a medio recortar engaña."""
    BatchRation.objects.create(batch=batch, ration=ration, date_from=datetime.date(2026, 1, 1))

    timeline = batch_timeline(batch)

    assert list(timeline["daily_yields"]) == []
    assert list(timeline["ration_periods"]) == []


@pytest.mark.django_db
def test_la_serie_completa_declara_que_los_analitos_son_sinteticos(lote_poblado):
    """Es el endpoint que más enseña el efecto plantado: callarlo aquí sería peor."""
    assert "sintéticos" in batch_timeline(lote_poblado)["milk_analytes_notice"]
