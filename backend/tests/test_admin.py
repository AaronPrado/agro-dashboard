"""Tests del registro de los modelos en el admin de Django."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from farms.models import Animal

LISTADOS = [
    "admin:farms_farm_changelist",
    "admin:farms_animal_changelist",
    "admin:farms_dailyyield_changelist",
    "admin:farms_milkrecord_changelist",
    "admin:farms_plot_changelist",
    "admin:farms_crop_changelist",
    "admin:farms_silage_changelist",
    "admin:farms_niranalysis_changelist",
    "admin:farms_rawmaterial_changelist",
]


def crear_animales(farm, cantidad, desde=0):
    """Crea `cantidad` animales con crotales correlativos."""
    return Animal.objects.bulk_create(
        Animal(
            farm=farm,
            ear_tag=f"ES{desde + i:06d}",
            birth_date=datetime.date(2021, 3, 1),
        )
        for i in range(cantidad)
    )


@pytest.mark.parametrize("nombre_url", LISTADOS)
@pytest.mark.django_db
def test_listados_del_admin_responden(admin_client, nombre_url):
    """Todos los modelos están registrados y su listado se renderiza."""
    response = admin_client.get(reverse(nombre_url))

    assert response.status_code == 200


@pytest.mark.django_db
def test_formulario_de_alta_de_animal_responde(admin_client, farm):
    """El alta usa autocomplete_fields, que exige search_fields en FarmAdmin."""
    response = admin_client.get(reverse("admin:farms_animal_add"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_formulario_de_alta_de_analisis_nir_responde(admin_client, silage):
    """Valida la cadena de autocompletado más profunda del admin.

    `NIRAnalysis` autocompleta `Silage`, que autocompleta `Crop`, que autocompleta
    `Plot`, que autocompleta `Farm`. Como `autocomplete_fields` exige
    `search_fields` en el ModelAdmin apuntado, quitarlos de cualquier eslabón
    intermedio rompe la comprobación de sistema y tumba el admin entero, no solo
    este formulario.
    """
    response = admin_client.get(reverse("admin:farms_niranalysis_add"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_listado_de_animales_no_incurre_en_n_mas_uno(admin_client, farm):
    """list_select_related evita una consulta por fila para pintar la granja.

    No se fija un número concreto de consultas (el admin hace varias por
    sesión y permisos), sino que ese número no crezca con las filas: eso es
    exactamente lo que distingue una consulta con JOIN de un N+1.
    """
    url = reverse("admin:farms_animal_changelist")
    crear_animales(farm, cantidad=1)

    with CaptureQueriesContext(connection) as con_una_fila:
        admin_client.get(url)

    crear_animales(farm, cantidad=20, desde=100)

    with CaptureQueriesContext(connection) as con_muchas_filas:
        admin_client.get(url)

    assert len(con_muchas_filas) == len(con_una_fila)
