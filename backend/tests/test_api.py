"""Tests de los endpoints de lectura de la API.

Aquí se ejercita la API de extremo a extremo (enrutado, paginación, orden y
serialización), a diferencia de `test_serializers.py`, que prueba la
representación de cada modelo en aislamiento.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from farms.models import Animal, Milking


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
    assert set(response.json()) == {"farms", "animals", "milkings", "milk-records"}


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
def test_una_pagina_de_ordenos_no_dispara_consultas_por_fila(
    api_client, animals, django_assert_num_queries
):
    """El `select_related` de la vista evita el problema N+1.

    Sin él, cada ordeño de la página consultaría su animal por separado y el
    número de consultas crecería con el tamaño de página.
    """
    for index, animal in enumerate(animals):
        Milking.objects.create(
            animal=animal,
            date=datetime.date(2026, 5, 10 + index),
            liters=Decimal("28.40"),
        )

    # Dos consultas fijas: el recuento de la paginación y la página en sí.
    with django_assert_num_queries(2):
        response = api_client.get(reverse("farms:milking-list"))
        assert len(response.json()["results"]) == len(animals)


@pytest.mark.django_db
def test_el_health_check_sigue_respondiendo_fuera_del_router(api_client):
    """La sonda de infraestructura convive con las rutas generadas por DRF."""
    response = api_client.get(reverse("farms:health"))

    assert response.status_code == 200
