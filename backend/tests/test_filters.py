"""Tests de los filtros de la API.

Cubren las dos caras del contrato: que un filtro válido acote el conjunto
esperado, y que un parámetro inválido se rechace con 400 en vez de degradar
silenciosamente a "sin filtro" o a un listado vacío indistinguible.
"""

import datetime
from decimal import Decimal

import pytest
from django.urls import reverse

from farms.models import Animal, DailyYield, Farm


@pytest.fixture
def otra_granja(db):
    """Segunda explotación, para comprobar que el filtro por granja aísla."""
    return Farm.objects.create(
        name="Fonte Vella",
        code="fonte-vella",
        municipality="Chantada",
        province="Lugo",
    )


@pytest.fixture
def rebano(farm, otra_granja):
    """Un animal activo y uno de baja en una granja, y otro en la segunda."""
    activo = Animal.objects.create(
        farm=farm,
        ear_tag="ES0100",
        birth_date=datetime.date(2021, 1, 10),
        breed=Animal.Breed.HOLSTEIN,
    )
    de_baja = Animal.objects.create(
        farm=farm,
        ear_tag="ES0200",
        birth_date=datetime.date(2019, 6, 5),
        breed=Animal.Breed.JERSEY,
        culled_date=datetime.date(2026, 1, 31),
    )
    ajeno = Animal.objects.create(
        farm=otra_granja,
        ear_tag="ES0300",
        birth_date=datetime.date(2022, 4, 20),
    )
    return activo, de_baja, ajeno


@pytest.mark.django_db
def test_los_animales_se_filtran_por_granja(api_client, rebano, farm):
    """El filtro por granja excluye los animales de las demás."""
    activo, de_baja, _ajeno = rebano

    response = api_client.get(reverse("farms:animal-list"), {"farm": farm.pk})

    assert response.status_code == 200
    crotales = {row["ear_tag"] for row in response.json()["results"]}
    assert crotales == {activo.ear_tag, de_baja.ear_tag}


@pytest.mark.django_db
def test_los_animales_se_filtran_por_estado(api_client, rebano):
    """`active` se deriva de la fecha de baja, no de un campo propio."""
    activo, de_baja, ajeno = rebano

    activos = api_client.get(reverse("farms:animal-list"), {"active": "true"}).json()
    bajas = api_client.get(reverse("farms:animal-list"), {"active": "false"}).json()

    assert {row["ear_tag"] for row in activos["results"]} == {
        activo.ear_tag,
        ajeno.ear_tag,
    }
    assert [row["ear_tag"] for row in bajas["results"]] == [de_baja.ear_tag]


@pytest.mark.django_db
def test_los_animales_se_filtran_por_raza(api_client, rebano):
    """La raza se valida contra las opciones declaradas en el modelo."""
    _activo, de_baja, _ajeno = rebano

    response = api_client.get(reverse("farms:animal-list"), {"breed": "jersey"})

    assert [row["ear_tag"] for row in response.json()["results"]] == [de_baja.ear_tag]


@pytest.mark.django_db
def test_una_raza_inexistente_se_rechaza(api_client, rebano):
    """Un valor fuera de las opciones no puede pasar como filtro válido."""
    response = api_client.get(reverse("farms:animal-list"), {"breed": "pastueña"})

    assert response.status_code == 400


@pytest.fixture
def produccion(rebano):
    """Serie de producción diaria repartida entre dos granjas y tres fechas."""
    activo, _de_baja, ajeno = rebano
    for dia, animal in ((1, activo), (15, activo), (28, ajeno)):
        DailyYield.objects.create(
            animal=animal,
            date=datetime.date(2026, 4, dia),
            liters=Decimal("27.50"),
        )


@pytest.mark.django_db
def test_la_produccion_se_filtra_por_granja_del_animal(api_client, produccion, farm):
    """La producción diaria no tiene granja propia: se filtra cruzando la relación."""
    response = api_client.get(reverse("farms:daily-yield-list"), {"farm": farm.pk})

    assert response.status_code == 200
    fechas = {row["date"] for row in response.json()["results"]}
    assert fechas == {"2026-04-01", "2026-04-15"}


@pytest.mark.django_db
def test_la_produccion_se_filtra_por_rango_de_fechas(api_client, produccion):
    """El rango es cerrado por ambos extremos."""
    response = api_client.get(
        reverse("farms:daily-yield-list"),
        {"date_from": "2026-04-15", "date_to": "2026-04-28"},
    )

    fechas = {row["date"] for row in response.json()["results"]}
    assert fechas == {"2026-04-15", "2026-04-28"}


@pytest.mark.django_db
def test_el_rango_admite_un_solo_extremo(api_client, produccion):
    """`date_from` sin `date_to` deja la ventana abierta por la derecha."""
    response = api_client.get(reverse("farms:daily-yield-list"), {"date_from": "2026-04-15"})

    fechas = {row["date"] for row in response.json()["results"]}
    assert fechas == {"2026-04-15", "2026-04-28"}


@pytest.mark.django_db
def test_los_filtros_se_combinan(api_client, produccion, farm):
    """Granja y fecha acotan a la vez, no se pisan."""
    response = api_client.get(
        reverse("farms:daily-yield-list"),
        {"farm": farm.pk, "date_from": "2026-04-10"},
    )

    fechas = [row["date"] for row in response.json()["results"]]
    assert fechas == ["2026-04-15"]


@pytest.mark.django_db
def test_una_fecha_mal_formada_se_rechaza(api_client, produccion):
    """Un parámetro inválido devuelve 400, no un listado sin filtrar."""
    response = api_client.get(reverse("farms:daily-yield-list"), {"date_from": "ayer"})

    assert response.status_code == 400


@pytest.mark.django_db
def test_una_granja_inexistente_se_rechaza(api_client, produccion):
    """Filtrar por una granja que no existe es un error del cliente."""
    response = api_client.get(reverse("farms:daily-yield-list"), {"farm": 999_999})

    assert response.status_code == 400


@pytest.mark.django_db
def test_las_granjas_se_filtran_por_provincia(api_client, farm, otra_granja):
    """`filterset_fields` basta cuando el filtro es por igualdad simple."""
    response = api_client.get(reverse("farms:farm-list"), {"province": "Lugo"})

    assert response.status_code == 200
    assert response.json()["count"] == 2
