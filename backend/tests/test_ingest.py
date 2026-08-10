"""Tests del cargador: claves naturales, procedencia, idempotencia y rechazos.

Los lotes se construyen a mano en vez de pasar por un adaptador: así el cargador
queda probado aislado de cualquier formato de origen, que es justo la separación
que el diseño defiende.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import Animal, DailyYield, Farm, IngestionReject, IngestionRun, SourceSystem
from farms.services.canonical import (
    AnimalRegistration,
    CanonicalBatch,
    FarmRegistration,
    MilkQualityRecord,
    ProductionReading,
    Reject,
)
from farms.services.ingest import IngestionError, clear, load

FARM_CODE = "casa-grande"
EAR_TAG = "ES221100010001"
DAY = datetime.date(2026, 2, 10)


def _farm() -> FarmRegistration:
    return FarmRegistration(
        code=FARM_CODE,
        name="Casa Grande",
        municipality="Sarria",
        province="Lugo",
    )


def _animal() -> AnimalRegistration:
    return AnimalRegistration(
        farm_code=FARM_CODE,
        ear_tag=EAR_TAG,
        birth_date=datetime.date(2021, 3, 1),
        breed="holstein",
        lactation_number=2,
        last_calving_date=datetime.date(2025, 11, 4),
        culled_date=None,
    )


def _census(source=SourceSystem.MILK_RECORDING) -> CanonicalBatch:
    """Lote maestro: la explotación y su animal, sin hechos medidos."""
    return CanonicalBatch(source=source, farms=[_farm()], animals=[_animal()])


@pytest.mark.django_db
def test_una_carga_queda_registrada_con_sus_contadores():
    """Toda escritura pasa por una carga, y la carga sabe cuánto entró."""
    run, summary = load(_census(), reference="censo-2026-02.csv")

    assert IngestionRun.objects.count() == 1
    assert run.source == SourceSystem.MILK_RECORDING
    assert run.reference == "censo-2026-02.csv"
    assert run.records_loaded == summary.loaded == 2
    assert run.records_rejected == 0


@pytest.mark.django_db
def test_cada_fila_apunta_a_la_carga_que_la_trajo():
    """La procedencia se escribe con el dato, no se deduce después."""
    run, _ = load(_census())

    assert Farm.objects.get().ingestion_run == run
    assert Animal.objects.get().ingestion_run == run


@pytest.mark.django_db
def test_la_produccion_se_ancla_por_clave_natural():
    """El lote habla de granja y crotal; el cargador resuelve la clave primaria."""
    load(_census())
    load(
        CanonicalBatch(
            source=SourceSystem.MILKING_ROBOT,
            production=[
                ProductionReading(
                    farm_code=FARM_CODE, ear_tag=EAR_TAG, date=DAY, liters=Decimal("27.57")
                )
            ],
        )
    )

    daily_yield = DailyYield.objects.get()
    assert daily_yield.animal.ear_tag == EAR_TAG
    assert daily_yield.liters == Decimal("27.57")


@pytest.mark.django_db
def test_dos_fuentes_distintas_cuelgan_del_mismo_animal():
    """Producción y calidad entran por caminos distintos y se juntan en la base.

    Es la integración en pequeño: dos entregas sin nada en común salvo el crotal
    terminan colgando de la misma vaca.
    """
    load(_census())
    load(
        CanonicalBatch(
            source=SourceSystem.MILKING_ROBOT,
            production=[
                ProductionReading(
                    farm_code=FARM_CODE, ear_tag=EAR_TAG, date=DAY, liters=Decimal("27.57")
                )
            ],
        )
    )
    load(
        CanonicalBatch(
            source=SourceSystem.MILK_RECORDING,
            quality=[
                MilkQualityRecord(
                    farm_code=FARM_CODE,
                    ear_tag=EAR_TAG,
                    date=DAY,
                    fat_pct=Decimal("3.70"),
                    protein_pct=Decimal("3.10"),
                    somatic_cell_count=68_000,
                )
            ],
        )
    )

    animal = Animal.objects.get()
    assert animal.daily_yields.count() == 1
    assert animal.milk_records.count() == 1
    assert IngestionRun.objects.count() == 3


@pytest.mark.django_db
def test_reingerir_una_entrega_corregida_actualiza_en_vez_de_duplicar():
    """Una fuente que rectifica no debería obligar a vaciar la base."""
    load(_census())
    entrega = CanonicalBatch(
        source=SourceSystem.MILKING_ROBOT,
        production=[
            ProductionReading(
                farm_code=FARM_CODE, ear_tag=EAR_TAG, date=DAY, liters=Decimal("27.57")
            )
        ],
    )
    load(entrega)

    corregida = CanonicalBatch(
        source=SourceSystem.MILKING_ROBOT,
        production=[
            ProductionReading(
                farm_code=FARM_CODE, ear_tag=EAR_TAG, date=DAY, liters=Decimal("31.20")
            )
        ],
    )
    segunda_carga, _ = load(corregida)

    daily_yield = DailyYield.objects.get()
    assert daily_yield.liters == Decimal("31.20")
    assert daily_yield.ingestion_run == segunda_carga


@pytest.mark.django_db
def test_un_animal_no_registrado_aborta_la_entrega_entera():
    """Cargar solo lo que casa dejaría una base incompleta con aspecto de sana."""
    load(_census())

    with pytest.raises(IngestionError):
        load(
            CanonicalBatch(
                source=SourceSystem.MILKING_ROBOT,
                production=[
                    ProductionReading(
                        farm_code=FARM_CODE,
                        ear_tag="ES221100019999",
                        date=DAY,
                        liters=Decimal("27.57"),
                    )
                ],
            )
        )

    assert DailyYield.objects.count() == 0
    # La carga abortada tampoco deja rastro: la transacción envuelve su creación.
    assert IngestionRun.objects.count() == 1


@pytest.mark.django_db
def test_lo_rechazado_por_el_adaptador_se_guarda_con_su_motivo():
    """Un rechazo sin registrar es un dato perdido en silencio."""
    run, summary = load(
        CanonicalBatch(
            source=SourceSystem.MILKING_ROBOT,
            rejects=[
                Reject(line_number=7, raw="221100010002;10/02/2026;12,30", reason="faltan campos")
            ],
        )
    )

    assert summary.rejected == run.records_rejected == 1
    reject = IngestionReject.objects.get()
    assert reject.run == run
    assert reject.line_number == 7
    assert reject.reason == "faltan campos"


@pytest.mark.django_db
def test_clear_vacia_hechos_y_cargas():
    """El orden importa: la procedencia es PROTECT y bloquea el borrado inverso."""
    load(_census())

    clear()

    assert Farm.objects.count() == 0
    assert Animal.objects.count() == 0
    assert IngestionRun.objects.count() == 0
