"""Tests del cargador: claves naturales, procedencia, idempotencia y rechazos.

Los lotes se construyen a mano en vez de pasar por un adaptador: así el cargador
queda probado aislado de cualquier formato de origen, que es justo la separación
que el diseño defiende.
"""

import datetime
from dataclasses import replace
from decimal import Decimal

import pytest

from farms.models import (
    AnalysisResult,
    Analyte,
    Animal,
    BatchMilkSample,
    DailyYield,
    Farm,
    IngestionReject,
    IngestionRun,
    SourceSystem,
    TargetProfile,
    TargetRange,
)
from farms.services.canonical import (
    AnalyteRecord,
    AnimalBatchRecord,
    AnimalRegistration,
    CanonicalBatch,
    FarmRegistration,
    MilkQualityRecord,
    MilkResultRecord,
    MilkSampleRecord,
    ProductionReading,
    Reject,
)
from farms.services.ingest import IngestionError, clear, load, load_target_profiles
from farms.services.milk_quality import MILK_ANALYTES
from farms.services.target_profiles import (
    TARGET_PROFILES,
    TargetProfileSpec,
    minimum_values,
)

FARM_CODE = "casa-grande"
EAR_TAG = "ES221100010001"
DAY = datetime.date(2026, 2, 10)
BATCH_NAME = "Alta producción"


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
    load(_milk_lab())

    clear()

    assert Farm.objects.count() == 0
    assert Animal.objects.count() == 0
    assert BatchMilkSample.objects.count() == 0
    assert AnalysisResult.objects.count() == 0
    assert IngestionRun.objects.count() == 0


# --- La analítica de leche del lote ---


def _milk_lab(value=Decimal("1.2300"), source=SourceSystem.MILK_LAB) -> CanonicalBatch:
    """Entrega del laboratorio de leche: el lote, el analito y una muestra.

    Trae también la explotación y el lote porque el cargador resuelve por clave
    natural: sin ellos no habría a qué anclar la muestra.
    """
    return CanonicalBatch(
        source=source,
        farms=[_farm()],
        batches=[AnimalBatchRecord(farm_code=FARM_CODE, name=BATCH_NAME)],
        analytes=[AnalyteRecord(code="cla", name="Ácido linoleico conjugado", unit="% de AG")],
        milk_samples=[
            MilkSampleRecord(
                farm_code=FARM_CODE,
                batch_name=BATCH_NAME,
                date=DAY,
                laboratory="Laboratorio de análisis de leche",
            )
        ],
        milk_results=[
            MilkResultRecord(
                farm_code=FARM_CODE,
                batch_name=BATCH_NAME,
                date=DAY,
                analyte_code="cla",
                value=value,
            )
        ],
    )


@pytest.mark.django_db
def test_la_muestra_de_leche_cuelga_de_su_lote():
    """El laboratorio nombra el lote; resolverlo a clave primaria es de aquí."""
    run, _ = load(_milk_lab())

    sample = BatchMilkSample.objects.get()
    assert sample.batch.name == BATCH_NAME
    assert sample.batch.farm.code == FARM_CODE
    assert sample.date == DAY
    assert sample.ingestion_run == run


@pytest.mark.django_db
def test_el_resultado_de_leche_deja_vacia_la_rama_del_analisis_nir():
    """El XOR del modelo: un resultado es de forraje o de leche, nunca de ambos."""
    load(_milk_lab())

    result = AnalysisResult.objects.get()
    assert result.nir_analysis is None
    assert result.milk_sample == BatchMilkSample.objects.get()
    assert result.analyte.code == "cla"
    assert result.value == Decimal("1.2300")


@pytest.mark.django_db
def test_los_contadores_distinguen_muestras_de_resultados():
    """Una muestra con cuatro analitos son cinco filas, no una."""
    _, summary = load(_milk_lab())

    assert summary.milk_samples == 1
    assert summary.milk_results == 1


@pytest.mark.django_db
def test_reingerir_una_muestra_corregida_actualiza_en_vez_de_duplicar():
    """El laboratorio rectifica un valor y reenvía el informe entero."""
    load(_milk_lab())

    load(_milk_lab(value=Decimal("1.8800")))

    assert BatchMilkSample.objects.count() == 1
    assert AnalysisResult.objects.count() == 1
    assert AnalysisResult.objects.get().value == Decimal("1.8800")


@pytest.mark.django_db
def test_una_muestra_de_un_lote_desconocido_aborta_la_entrega():
    """Clave natural que no casa: se para, no se carga a medias."""
    batch = _milk_lab()
    batch.batches = []

    with pytest.raises(IngestionError, match="lotes no registrados"):
        load(batch)

    assert BatchMilkSample.objects.count() == 0


@pytest.mark.django_db
def test_un_resultado_sin_su_muestra_aborta_la_entrega():
    """Un valor suelto no se puede anclar, y colgarlo de otra muestra sería peor."""
    batch = _milk_lab()
    batch.milk_samples = []

    with pytest.raises(IngestionError, match="muestras de leche no registradas"):
        load(batch)

    assert AnalysisResult.objects.count() == 0


# --- El catálogo de perfiles de destino ---

TOTAL_RANGES = sum(len(spec.demands) for spec in TARGET_PROFILES)


def _milk_analytes() -> None:
    """Siembra el catálogo de analitos de leche, que es quien define los códigos.

    Se crean directamente y no por una entrega: lo que se prueba aquí es el
    cargador del catálogo comercial, no cómo llegan los analitos.
    """
    for code, name, unit in MILK_ANALYTES:
        Analyte.objects.create(code=code, name=name, unit=unit)


def _spec(code: str) -> TargetProfileSpec:
    return next(spec for spec in TARGET_PROFILES if spec.code == code)


@pytest.mark.django_db
def test_los_perfiles_de_destino_se_cargan_con_sus_rangos():
    _milk_analytes()

    summary = load_target_profiles()

    assert summary.target_profiles == len(TARGET_PROFILES)
    assert summary.target_ranges == TOTAL_RANGES
    assert TargetProfile.objects.count() == len(TARGET_PROFILES)
    assert TargetRange.objects.count() == TOTAL_RANGES


@pytest.mark.django_db
def test_el_catalogo_de_perfiles_no_abre_una_carga():
    """Nadie lo entrega, así que no hay procedencia que registrar."""
    _milk_analytes()

    load_target_profiles()

    assert IngestionRun.objects.count() == 0


@pytest.mark.django_db
def test_los_umbrales_llegan_a_la_base_como_minimos_sin_techo():
    """El catálogo solo pone suelos: un techo sería una exigencia inventada."""
    _milk_analytes()

    load_target_profiles()

    rango = TargetRange.objects.get(profile__code="queso-azul-artesano", analyte__code="cla")
    assert rango.min_value == minimum_values(_spec("queso-azul-artesano"))["cla"]
    assert rango.max_value is None
    assert not TargetRange.objects.filter(max_value__isnull=False).exists()


@pytest.mark.django_db
def test_resembrar_el_catalogo_actualiza_en_vez_de_duplicar():
    _milk_analytes()
    load_target_profiles()

    load_target_profiles()

    assert TargetProfile.objects.count() == len(TARGET_PROFILES)
    assert TargetRange.objects.count() == TOTAL_RANGES


@pytest.mark.django_db
def test_un_perfil_que_deja_de_exigir_un_analito_pierde_su_rango():
    """El upsert actualiza lo que sigue estando; retirar lo que sobra es aparte."""
    _milk_analytes()
    completo = TargetProfileSpec(
        code="ejemplo",
        name="Perfil de ejemplo",
        description="Solo para el test.",
        demands={"cla": Decimal("0.50"), "omega3": Decimal("0.50")},
    )
    load_target_profiles([completo])

    load_target_profiles([replace(completo, demands={"cla": Decimal("0.50")})])

    rangos = TargetRange.objects.filter(profile__code="ejemplo")
    assert [rango.analyte.code for rango in rangos] == ["cla"]


@pytest.mark.django_db
def test_un_perfil_sobre_un_analito_desconocido_aborta_el_catalogo():
    """Mismo criterio que el resto del cargador: clave que no casa, no se carga a medias."""
    with pytest.raises(IngestionError, match="analitos no registrados"):
        load_target_profiles()

    assert TargetProfile.objects.count() == 0
    assert TargetRange.objects.count() == 0


@pytest.mark.django_db
def test_clear_se_lleva_los_perfiles_y_libera_el_catalogo_de_analitos():
    """`TargetRange.analyte` es PROTECT: sin quitar antes los perfiles, `Analyte` no cae."""
    _milk_analytes()
    load_target_profiles()

    clear()

    assert TargetProfile.objects.count() == 0
    assert TargetRange.objects.count() == 0
    assert Analyte.objects.count() == 0
