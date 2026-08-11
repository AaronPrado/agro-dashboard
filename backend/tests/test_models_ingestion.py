"""Tests del registro de cargas y de la traza de procedencia."""

import datetime
from decimal import Decimal

import pytest
from django.db.models import ProtectedError

from farms.models import (
    Animal,
    DailyYield,
    Farm,
    IngestionReject,
    IngestionRun,
    SourceSystem,
)


@pytest.mark.django_db
def test_una_carga_registra_fuente_y_momento(ingestion_run):
    """La fecha de ingesta la pone la base, no quien carga."""
    assert ingestion_run.ingested_at is not None
    assert ingestion_run.get_source_display() == "Robot o sala de ordeño"
    assert ingestion_run.records_loaded == 0
    assert ingestion_run.records_rejected == 0


@pytest.mark.django_db
def test_las_fuentes_son_las_que_esperan_los_adaptadores():
    """Fija el catálogo: añadir una fuente es una decisión, no un descuido.

    Los adaptadores declaran su origen con estos valores, y el mismo literal
    viaja a la columna `source`; si alguno cambia, la carga deja de casar con
    su adaptador.
    """
    assert set(SourceSystem.values) == {
        "milking_robot",
        "milk_recording",
        "nir_lab",
        "milk_lab",
        "field_notebook",
    }


@pytest.mark.django_db
def test_la_fila_cargada_apunta_a_su_carga(ingestion_run):
    """El acceso inverso lo genera `%(class)ss` del modelo abstracto.

    Quince modelos heredan la misma clave ajena, así que el `related_name` no
    puede ser una cadena fija: Django sustituye el marcador por el nombre de
    cada clase hija y evita la colisión.
    """
    farm = Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
        ingestion_run=ingestion_run,
    )
    animal = Animal.objects.create(
        farm=farm,
        ear_tag="ES221100010001",
        birth_date=datetime.date(2021, 3, 1),
        ingestion_run=ingestion_run,
    )
    DailyYield.objects.create(
        animal=animal,
        date=datetime.date(2026, 2, 10),
        liters=Decimal("28.40"),
        ingestion_run=ingestion_run,
    )

    assert list(ingestion_run.farms.all()) == [farm]
    assert list(ingestion_run.animals.all()) == [animal]
    assert ingestion_run.dailyyields.count() == 1


@pytest.mark.django_db
def test_una_fila_puede_no_tener_carga(farm):
    """La procedencia es nula en lo cargado antes de que existiera el registro."""
    assert farm.ingestion_run is None


@pytest.mark.django_db
def test_borrar_una_carga_con_filas_esta_protegido(ingestion_run):
    """`PROTECT`: perder la carga sería perder de dónde vino cada fila."""
    Farm.objects.create(
        name="A Ponte",
        code="a-ponte",
        municipality="Chantada",
        province="Lugo",
        ingestion_run=ingestion_run,
    )

    with pytest.raises(ProtectedError):
        ingestion_run.delete()


@pytest.mark.django_db
def test_los_rechazos_conservan_la_linea_y_su_motivo(ingestion_run):
    """Un contador de errores sin la fila original no sirve para corregir nada."""
    IngestionReject.objects.create(
        run=ingestion_run,
        line_number=42,
        raw="ES221100010001;;2026-02-31;28,4",
        reason="fecha inexistente",
    )

    reject = ingestion_run.rejects.get()
    assert reject.line_number == 42
    assert "2026-02-31" in reject.raw
    assert str(reject) == "línea 42: fecha inexistente"


@pytest.mark.django_db
def test_borrar_la_carga_arrastra_sus_rechazos(ingestion_run):
    """Los rechazos son `CASCADE`: sin su carga no significan nada."""
    IngestionReject.objects.create(
        run=ingestion_run,
        line_number=7,
        raw="basura",
        reason="columnas insuficientes",
    )

    ingestion_run.delete()

    assert IngestionRun.objects.count() == 0
    assert IngestionReject.objects.count() == 0
