"""Tests de los endpoints de lectura de la API.

Aquí se ejercita la API de extremo a extremo (enrutado, paginación, orden y
serialización), a diferencia de `test_serializers.py`, que prueba la
representación de cada modelo en aislamiento.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from farms.models import (
    AnalysisResult,
    Animal,
    AnimalBatch,
    AnimalBatchMembership,
    BatchMilkSample,
    BatchRation,
    DailyYield,
    Farm,
    MilkRecord,
)


@pytest.fixture
def animals(farm):
    """Tres animales de la misma granja, para ejercitar orden y paginación."""
    return [
        Animal.objects.create(
            farm=farm,
            ear_tag=ear_tag,
            birth_date=datetime.date(2021, 3, 1),
        )
        for ear_tag in ("ES0010", "ES0020", "ES0030")
    ]


@pytest.mark.django_db
def test_la_raiz_de_la_api_lista_los_recursos(api_client):
    """El router publica un índice navegable con los endpoints disponibles."""
    response = api_client.get(reverse("farms:api-root"))

    assert response.status_code == 200
    assert set(response.json()) == {
        "farms",
        "animals",
        "daily-yields",
        "milk-records",
        "batches",
    }


@pytest.mark.django_db
def test_el_listado_llega_paginado(api_client, farm):
    """Toda colección viaja envuelta en la estructura de paginación."""
    response = api_client.get(reverse("farms:farm-list"))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 1
    assert body["results"][0]["code"] == "casa-grande"


@pytest.mark.django_db
def test_el_detalle_devuelve_un_unico_recurso(api_client, farm):
    """El detalle no va paginado: es el objeto plano."""
    response = api_client.get(reverse("farms:farm-detail", args=[farm.pk]))

    assert response.status_code == 200
    assert response.json()["name"] == "Casa Grande"


@pytest.mark.django_db
def test_un_recurso_inexistente_devuelve_404(api_client):
    """Un identificador que no existe no puede acabar en un error 500."""
    response = api_client.get(reverse("farms:farm-detail", args=[999_999]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_la_api_no_admite_escritura(api_client):
    """Los datos entran por la capa de ingesta, nunca por HTTP."""
    response = api_client.post(
        reverse("farms:farm-list"),
        {"name": "Nueva", "code": "nueva", "municipality": "Lugo", "province": "Lugo"},
        format="json",
    )

    assert response.status_code == 405


@pytest.mark.django_db
def test_el_listado_de_animales_aplana_granja_y_raza(api_client, animal):
    """Los denormalizados del serializer sobreviven al paso por la vista."""
    response = api_client.get(reverse("farms:animal-list"))

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["farm_name"] == "Casa Grande"
    assert result["breed_display"] == "Frisona"
    assert result["is_active"] is True


@pytest.mark.django_db
def test_el_cliente_puede_reducir_el_tamano_de_pagina(api_client, animals):
    """`page_size` acorta la página sin alterar el total de registros."""
    response = api_client.get(reverse("farms:animal-list"), {"page_size": 2})

    body = response.json()
    assert body["count"] == len(animals)
    assert len(body["results"]) == 2
    assert body["next"] is not None
    assert body["previous"] is None


@pytest.mark.django_db
def test_la_segunda_pagina_continua_la_serie(api_client, animals):
    """Las páginas no se solapan ni se saltan registros."""
    primera = api_client.get(reverse("farms:animal-list"), {"page_size": 2}).json()
    segunda = api_client.get(reverse("farms:animal-list"), {"page_size": 2, "page": 2}).json()

    crotales = [row["ear_tag"] for row in primera["results"] + segunda["results"]]
    assert crotales == ["ES0010", "ES0020", "ES0030"]
    assert segunda["next"] is None


@pytest.mark.django_db
def test_el_parametro_ordering_invierte_el_orden(api_client, animals):
    """`OrderingFilter` permite invertir el orden por omisión del modelo."""
    response = api_client.get(reverse("farms:animal-list"), {"ordering": "-ear_tag"})

    crotales = [row["ear_tag"] for row in response.json()["results"]]
    assert crotales == ["ES0030", "ES0020", "ES0010"]


@pytest.mark.django_db
def test_una_pagina_de_produccion_no_dispara_consultas_por_fila(
    api_client, animals, django_assert_num_queries
):
    """El `select_related` de la vista evita el problema N+1.

    Sin él, cada fila de la página consultaría su animal por separado y el
    número de consultas crecería con el tamaño de página.
    """
    for index, animal in enumerate(animals):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 5, 10 + index),
            liters=Decimal("28.40"),
        )

    # Dos consultas fijas: el recuento de la paginación y la página en sí.
    with django_assert_num_queries(2):
        response = api_client.get(reverse("farms:daily-yield-list"))
        assert len(response.json()["results"]) == len(animals)


@pytest.mark.django_db
def test_el_health_check_sigue_respondiendo_fuera_del_router(api_client):
    """La sonda de infraestructura convive con las rutas generadas por DRF."""
    response = api_client.get(reverse("farms:health"))

    assert response.status_code == 200


@pytest.fixture
def produccion_y_control(animal):
    """Un día de producción y un control, para ejercitar el resumen agregado."""
    DailyYield.objects.create(
        animal=animal,
        date=datetime.date(2026, 3, 1),
        liters=Decimal("30.00"),
    )
    MilkRecord.objects.create(
        animal=animal,
        date=datetime.date(2026, 3, 1),
        fat_pct=Decimal("4.00"),
        protein_pct=Decimal("3.20"),
        somatic_cell_count=500_000,
    )
    return animal


@pytest.mark.django_db
def test_el_resumen_por_explotacion_llega_paginado(api_client, produccion_y_control):
    """La acción agregada conserva el sobre de paginación del resto de la API."""
    response = api_client.get(reverse("farms:farm-summary"))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["results"][0]["total_liters"] == "30.00"
    assert body["results"][0]["active_animals"] == 1
    assert body["results"][0]["scc_over_limit"] == 1


@pytest.mark.django_db
def test_el_resumen_cuantiza_las_medias_a_dos_decimales(api_client, produccion_y_control):
    """La media de Postgres llega con dieciséis decimales y el serializer la recorta."""
    response = api_client.get(reverse("farms:farm-summary"))

    resumen = response.json()["results"][0]
    assert resumen["avg_fat_pct"] == "4.00"
    assert resumen["avg_protein_pct"] == "3.20"


@pytest.mark.django_db
def test_el_rango_de_fechas_acota_el_resumen(api_client, produccion_y_control):
    """Fuera de la ventana no hay medidas, y las métricas viajan nulas."""
    response = api_client.get(
        reverse("farms:farm-summary"),
        {"date_from": "2026-04-01"},
    )

    resumen = response.json()["results"][0]
    assert resumen["total_liters"] is None
    assert resumen["avg_fat_pct"] is None
    # El censo no depende de la ventana: la explotación sigue teniendo su vaca.
    assert resumen["active_animals"] == 1


@pytest.mark.django_db
def test_una_fecha_malformada_da_400(api_client, farm):
    """El parámetro se valida: no se ignora ni revienta con un 500."""
    response = api_client.get(reverse("farms:farm-summary"), {"date_from": "ayer"})

    assert response.status_code == 400
    assert "date_from" in response.json()


@pytest.mark.django_db
def test_un_rango_invertido_da_400(api_client, farm):
    """Un rango imposible es un error del cliente, no un resumen vacío."""
    response = api_client.get(
        reverse("farms:farm-summary"),
        {"date_from": "2026-03-10", "date_to": "2026-03-01"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_el_resumen_no_se_confunde_con_el_detalle(api_client, farm):
    """`/farms/summary/` es la acción, no una explotación con pk "summary"."""
    response = api_client.get("/api/farms/summary/")

    assert response.status_code == 200
    assert "results" in response.json()


@pytest.mark.django_db
def test_el_filtro_de_provincia_sigue_aplicando_sobre_el_resumen(api_client, farm):
    """Filtrar filas y parametrizar columnas son cosas ortogonales y conviven."""
    Farm.objects.create(
        name="Souto Vello",
        code="souto-vello",
        municipality="Ourense",
        province="Ourense",
    )

    response = api_client.get(reverse("farms:farm-summary"), {"province": "Lugo"})

    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["code"] == "casa-grande"


@pytest.mark.django_db
def test_el_listado_de_lotes_cuenta_solo_las_pertenencias_vigentes(api_client, batch, animal, farm):
    """El censo del lote son sus miembros de hoy, no todos los que pasaron por él."""
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 1, 1),
    )
    antiguo = Animal.objects.create(
        farm=farm,
        ear_tag="ES221100010009",
        birth_date=datetime.date(2020, 1, 1),
    )
    AnimalBatchMembership.objects.create(
        animal=antiguo,
        batch=batch,
        date_from=datetime.date(2025, 1, 1),
        date_to=datetime.date(2025, 12, 31),
    )

    response = api_client.get(reverse("farms:batch-list"))

    assert response.status_code == 200
    assert response.json()["results"][0]["active_animals"] == 1


@pytest.mark.django_db
def test_el_listado_de_lotes_trae_la_racion_vigente(api_client, batch, ration):
    """La ración que come el lote es la del periodo abierto."""
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 2, 1),
    )

    response = api_client.get(reverse("farms:batch-list"))

    assert response.json()["results"][0]["current_ration"] == "Lactación alta"


@pytest.mark.django_db
def test_un_lote_sin_racion_asignada_no_inventa_ninguna(api_client, batch, ration):
    """Un periodo cerrado no es la ración vigente: el campo viaja nulo."""
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2025, 1, 1),
        date_to=datetime.date(2025, 6, 30),
    )

    response = api_client.get(reverse("farms:batch-list"))

    assert response.json()["results"][0]["current_ration"] is None


@pytest.mark.django_db
def test_el_listado_de_lotes_se_filtra_por_explotacion(api_client, batch, farm):
    """El lote pertenece a una explotación y el listado se acota por ella."""
    otra = Farm.objects.create(
        name="Souto Vello",
        code="souto-vello",
        municipality="Chantada",
        province="Lugo",
    )
    AnimalBatch.objects.create(farm=otra, name="Secas")

    response = api_client.get(reverse("farms:batch-list"), {"farm": farm.pk})

    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["name"] == "Alta producción"


@pytest.mark.django_db
def test_una_pagina_de_lotes_no_dispara_consultas_por_fila(
    api_client, batch, farm, django_assert_num_queries
):
    """El `select_related` y las anotaciones evitan una consulta por lote."""
    for name in ("Secas", "Novillas"):
        AnimalBatch.objects.create(farm=farm, name=name)

    # Dos consultas fijas: el recuento de la paginación y la página en sí.
    with django_assert_num_queries(2):
        response = api_client.get(reverse("farms:batch-list"))
        assert len(response.json()["results"]) == 3


@pytest.mark.django_db
def test_los_lotes_son_de_solo_lectura(api_client, farm):
    """Los datos entran por la capa de ingesta, no por HTTP."""
    response = api_client.post(reverse("farms:batch-list"), {"farm": farm.pk, "name": "Nuevo"})

    assert response.status_code == 405


@pytest.mark.django_db
def test_el_resumen_del_lote_no_va_paginado(api_client, batch, animal):
    """El resumen de un lote es un objeto, no una colección."""
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 1),
    )
    DailyYield.objects.create(
        animal=animal,
        date=datetime.date(2026, 3, 2),
        liters=Decimal("22.50"),
    )

    response = api_client.get(reverse("farms:batch-summary", args=[batch.pk]))

    assert response.status_code == 200
    body = response.json()
    assert "results" not in body
    assert body["total_liters"] == "22.50"
    assert body["active_animals"] == 1


@pytest.mark.django_db
def test_los_analitos_del_lote_viajan_con_nombre_propio(api_client, batch, analyte, milk_sample):
    """El contrato público no expone los nombres de la travesía del ORM."""
    AnalysisResult.objects.create(
        milk_sample=milk_sample,
        analyte=analyte,
        value=Decimal("12.3400"),
    )

    response = api_client.get(reverse("farms:batch-summary", args=[batch.pk]))

    analitos = response.json()["milk_analytes"]
    assert analitos == [
        {
            "code": "dry-matter",
            "name": "Materia seca",
            "unit": "%",
            "avg_value": "12.3400",
            "samples": 1,
        }
    ]


@pytest.mark.django_db
def test_el_resumen_de_un_lote_inexistente_da_404(api_client):
    """La acción de detalle resuelve el objeto antes de agregar nada."""
    response = api_client.get(reverse("farms:batch-summary", args=[999_999]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_el_resumen_del_lote_valida_las_fechas(api_client, batch):
    """El mismo serializer de ventana protege a los dos agregados."""
    response = api_client.get(
        reverse("farms:batch-summary", args=[batch.pk]),
        {"date_to": "no-es-una-fecha"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_el_resumen_del_lote_declara_que_los_analitos_son_sinteticos(api_client, batch):
    """La correlación ración↔calidad está plantada, y la respuesta lo dice.

    Viaja aunque no haya ninguna muestra en la ventana: lo que se declara es de
    dónde sale el dato, no cuántas medidas hay.
    """
    response = api_client.get(reverse("farms:batch-summary", args=[batch.pk]))

    body = response.json()
    assert body["milk_analytes"] == []
    assert "sintéticos" in body["milk_analytes_notice"]


# --- La serie temporal del lote ---


@pytest.fixture
def lote_con_serie(batch, animal, ration, analyte):
    """Un lote con producción dos días, una muestra de leche y una ración vigente.

    Es el mínimo que ejercita las tres colecciones a la vez, que es lo que el
    endpoint promete devolver en una sola llamada.
    """
    AnimalBatchMembership.objects.create(
        animal=animal,
        batch=batch,
        date_from=datetime.date(2026, 3, 1),
    )
    for day, liters in ((2, "22.50"), (3, "27.50")):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 3, day),
            liters=Decimal(liters),
        )
    BatchRation.objects.create(
        batch=batch,
        ration=ration,
        date_from=datetime.date(2026, 1, 1),
    )
    muestra = BatchMilkSample.objects.create(batch=batch, date=datetime.date(2026, 3, 2))
    AnalysisResult.objects.create(milk_sample=muestra, analyte=analyte, value=Decimal("35.0000"))
    return batch


@pytest.mark.django_db
def test_la_serie_del_lote_trae_las_tres_colecciones_en_una_llamada(api_client, lote_con_serie):
    """El criterio de la sesión: el cliente no tiene que cruzar nada."""
    response = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk]))

    body = response.json()
    assert response.status_code == 200
    assert len(body["daily_yields"]) == 2
    assert len(body["milk_samples"]) == 1
    assert len(body["ration_periods"]) == 1


@pytest.mark.django_db
def test_la_serie_del_lote_no_va_paginada(api_client, lote_con_serie):
    """Paginar una serie temporal obligaría al cliente a concatenar páginas."""
    body = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk])).json()

    assert "results" not in body
    assert "count" not in body


@pytest.mark.django_db
def test_la_produccion_diaria_viaja_ya_agregada_por_dia(api_client, lote_con_serie):
    """Los litros salen sumados del ORM; el cliente pinta el número que recibe."""
    body = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk])).json()

    assert body["daily_yields"][0] == {
        "date": "2026-03-02",
        "total_liters": "22.50",
        "avg_liters": "22.50",
        "animals": 1,
    }


@pytest.mark.django_db
def test_las_bandas_de_racion_llegan_recortadas_al_eje(api_client, lote_con_serie):
    """La ración empezó en enero y sigue vigente; la banda cabe en la gráfica."""
    body = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk])).json()

    periodo = body["ration_periods"][0]
    assert periodo["starts_on"] == "2026-03-02"
    assert periodo["ends_on"] == "2026-03-03"
    assert periodo["date_from"] == "2026-01-01"
    assert periodo["date_to"] is None


@pytest.mark.django_db
def test_la_ventana_efectiva_viaja_con_la_respuesta(api_client, lote_con_serie):
    """Sin ella, el cliente no sabría a qué eje se han recortado las bandas."""
    body = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk])).json()

    assert body["window"] == {"date_from": "2026-03-02", "date_to": "2026-03-03"}


@pytest.mark.django_db
def test_la_muestra_de_leche_llega_con_sus_analitos_anidados(api_client, lote_con_serie):
    """Una muestra es un hecho con varios resultados, y así viaja."""
    body = api_client.get(reverse("farms:batch-timeline", args=[lote_con_serie.pk])).json()

    assert body["milk_samples"][0]["date"] == "2026-03-02"
    assert body["milk_samples"][0]["results"] == [
        {"code": "dry-matter", "name": "Materia seca", "unit": "%", "value": "35.0000"}
    ]


@pytest.mark.django_db
def test_la_serie_del_lote_acota_por_la_ventana_pedida(api_client, lote_con_serie):
    response = api_client.get(
        reverse("farms:batch-timeline", args=[lote_con_serie.pk]),
        {"date_from": "2026-03-03"},
    )

    body = response.json()
    assert [punto["date"] for punto in body["daily_yields"]] == ["2026-03-03"]
    assert body["window"]["date_from"] == "2026-03-03"


@pytest.mark.django_db
def test_la_serie_del_lote_valida_las_fechas(api_client, batch):
    """El mismo serializer de ventana protege a los tres agregados."""
    response = api_client.get(
        reverse("farms:batch-timeline", args=[batch.pk]),
        {"date_from": "2026-03-10", "date_to": "2026-03-01"},
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_la_serie_del_lote_declara_que_los_analitos_son_sinteticos(api_client, batch):
    """Es el endpoint que más enseña el efecto plantado, y lo dice en la respuesta."""
    body = api_client.get(reverse("farms:batch-timeline", args=[batch.pk])).json()

    assert "sintéticos" in body["milk_analytes_notice"]
