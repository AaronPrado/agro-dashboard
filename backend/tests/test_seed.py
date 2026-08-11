"""Tests del comando de siembra: el recorrido completo, de extremo a extremo.

Es el criterio de hecho de la sesión puesto en un test: el comando genera, emite
el crudo de cada fuente, lo adapta, lo carga, y con la misma semilla produce
exactamente los mismos datos.
"""

import datetime
import itertools
from collections import defaultdict

import pytest
from django.core.management import call_command
from django.db.utils import IntegrityError

from farms.models import (
    AnalysisResult,
    Analyte,
    Animal,
    AnimalBatchMembership,
    BatchRation,
    Crop,
    DailyYield,
    Farm,
    IngestionRun,
    MilkRecord,
    Plot,
    Ration,
    RationIngredient,
    Silage,
    SourceSystem,
)
from farms.services.agronomy import FEEDING_GROUPS, FORAGE_RANGES

START = datetime.date(2026, 1, 1)
END = datetime.date(2026, 3, 31)


def _seed(seed=42, clear=True):
    """Siembra una explotación pequeña en una ventana fija y reproducible."""
    call_command(
        "seed",
        seed=seed,
        farms=1,
        animals_per_farm=4,
        start=START,
        end=END,
        clear=clear,
    )


def _produccion():
    return list(
        DailyYield.objects.order_by("animal__ear_tag", "date").values_list("liters", flat=True)
    )


def _inventario():
    """Cuántas filas hay de cada modelo que escribe la siembra.

    `IngestionRun` queda fuera a propósito: cada ejecución registra sus cargas,
    así que crece aunque no entre ni un dato nuevo.
    """
    modelos = (
        Farm,
        Animal,
        DailyYield,
        MilkRecord,
        Plot,
        Crop,
        Silage,
        Ration,
        RationIngredient,
        AnimalBatchMembership,
        BatchRation,
        Analyte,
        AnalysisResult,
    )
    return {modelo.__name__: modelo.objects.count() for modelo in modelos}


def _pertenencias():
    """Las pertenencias por clave natural, con el extremo abierto normalizado."""
    return sorted(
        (ear_tag, lote, desde, hasta or datetime.date.max)
        for ear_tag, lote, desde, hasta in AnimalBatchMembership.objects.values_list(
            "animal__ear_tag", "batch__name", "date_from", "date_to"
        )
    )


@pytest.mark.django_db
def test_la_siembra_puebla_de_extremo_a_extremo():
    """De la generación a la base pasando por el crudo y los adaptadores."""
    _seed()

    assert Farm.objects.count() == 1
    assert Animal.objects.count() == 4
    assert DailyYield.objects.exists()
    assert MilkRecord.objects.exists()


@pytest.mark.xfail(
    strict=True,
    reason="el laboratorio de leche ya está declarado como fuente pero el comando "
    "todavía no lo ingiere; la marca cae cuando `seed` lo cablee",
)
@pytest.mark.django_db
def test_el_dato_entra_por_mas_de_una_fuente():
    """La tesis en un assert: dos sistemas distintos, un solo modelo."""
    _seed()

    fuentes = set(IngestionRun.objects.values_list("source", flat=True))
    assert fuentes == set(SourceSystem.values)


@pytest.mark.django_db
def test_la_cadena_agricola_queda_sembrada_y_encadenada():
    """Parcela → campaña → silo, cada eslabón colgando del anterior."""
    _seed()

    assert Plot.objects.exists()
    assert Crop.objects.exists()
    assert Silage.objects.exists()
    for silage in Silage.objects.select_related("crop__plot__farm"):
        assert silage.crop.plot.farm.code is not None
        assert silage.sealed_date >= silage.crop.harvest_date
        assert silage.opened_date > silage.sealed_date


@pytest.mark.django_db
def test_hay_silo_disponible_antes_de_que_empiece_la_ventana():
    """El silo que se come en enero se cosechó el otoño anterior.

    Sin campañas del año previo, la cadena empezaría vacía justo en el tramo que
    la pantalla del hilo tiene que enseñar.
    """
    _seed()

    assert Silage.objects.filter(opened_date__lt=START).exists()


@pytest.mark.django_db
def test_las_raciones_se_formulan_con_silos_de_la_propia_explotacion():
    """El hilo se cierra: lo cosechado en la parcela acaba en el pesebre."""
    _seed()

    assert Ration.objects.exists()
    for ingredient in RationIngredient.objects.select_related(
        "ration__farm", "silage__crop__plot__farm"
    ):
        if ingredient.silage_id is not None:
            assert ingredient.silage.crop.plot.farm_id == ingredient.ration.farm_id


@pytest.mark.django_db
def test_cada_ingrediente_tiene_un_origen_y_solo_uno():
    """La restricción XOR del modelo, comprobada sobre el dato realmente sembrado."""
    _seed()

    for ingredient in RationIngredient.objects.all():
        assert (ingredient.silage_id is None) != (ingredient.raw_material_id is None)
        assert ingredient.dry_matter_kg > 0


@pytest.mark.django_db
def test_la_racion_suma_la_ingesta_declarada_del_grupo():
    """Los kg de materia seca de una ración cuadran con el grupo de manejo.

    Si el reparto entre silos y concentrado perdiera un céntimo por redondeo, la
    ración diría alimentar menos de lo que declara su grupo.
    """
    _seed()

    ingestas = {group.ration_name: group.dry_matter_kg for group in FEEDING_GROUPS}
    for ration in Ration.objects.prefetch_related("ingredients"):
        total = sum(ingredient.dry_matter_kg for ingredient in ration.ingredients.all())
        assert total == ingestas[ration.name]


@pytest.mark.django_db
def test_cada_silo_llega_con_su_analitica():
    """El último eslabón: del silo cuelga qué se midió en él."""
    _seed()

    assert Analyte.objects.exists()
    for silage in Silage.objects.prefetch_related("nir_analyses__results"):
        analisis = list(silage.nir_analyses.all())
        assert len(analisis) == 1
        assert analisis[0].date == silage.opened_date
        assert analisis[0].results.exists()


@pytest.mark.django_db
def test_los_valores_del_nir_caen_dentro_del_rango_publicado():
    """Ningún valor del generador se sale del rango de FEDNA para ese forraje.

    Es la afirmación que sostiene el apartado del documento sobre qué es
    sintético: los números están sorteados, pero no inventados.
    """
    _seed()

    resultados = AnalysisResult.objects.select_related("analyte", "nir_analysis__silage__crop")
    assert resultados.exists()
    for resultado in resultados:
        especie = resultado.nir_analysis.silage.crop.species
        rango = FORAGE_RANGES[especie][resultado.analyte.code]
        assert rango is not None, (especie, resultado.analyte.code)
        assert rango[0] <= resultado.value <= rango[1]


@pytest.mark.django_db
def test_el_almidon_solo_se_mide_en_el_maiz():
    """Un parámetro no determinado no deja fila, y el esquema lo impone."""
    _seed()

    especies = {
        resultado.nir_analysis.silage.crop.species
        for resultado in AnalysisResult.objects.filter(analyte__code="almidon").select_related(
            "nir_analysis__silage__crop"
        )
    }

    assert especies == {Crop.Species.MAIZE}


@pytest.mark.django_db
def test_ninguna_pertenencia_se_solapa_con_otra_del_mismo_animal():
    """El invariante que la base NO comprueba, verificado sobre lo sembrado.

    `update_or_create` no llama a `full_clean()`, así que el no-solape de
    `DatedPeriod` no protege a la siembra: lo garantiza el generador por
    construcción. Este test es la comprobación de que esa garantía se cumple, y
    la evidencia de que el hueco está identificado y no ignorado.
    """
    _seed()

    por_animal: dict[int, list[tuple[datetime.date, datetime.date]]] = defaultdict(list)
    for membership in AnimalBatchMembership.objects.all():
        hasta = membership.date_to or datetime.date.max
        por_animal[membership.animal_id].append((membership.date_from, hasta))

    assert por_animal
    for periodos in por_animal.values():
        periodos.sort()
        for anterior, siguiente in itertools.pairwise(periodos):
            assert anterior[1] < siguiente[0], (anterior, siguiente)


@pytest.mark.django_db
def test_cada_animal_tiene_como_mucho_un_periodo_abierto():
    """Esta mitad sí la impone la base: es un índice único parcial de PostgreSQL."""
    _seed()

    abiertos = AnimalBatchMembership.objects.filter(date_to__isnull=True)
    animales = list(abiertos.values_list("animal_id", flat=True))
    assert len(animales) == len(set(animales))


@pytest.mark.django_db
def test_la_base_rechaza_un_segundo_periodo_abierto():
    """El índice único parcial actúa aunque nadie llame a `full_clean()`.

    Es la única mitad del no-solape que sobrevive a una escritura masiva, y por
    eso conviene tener escrito que funciona.
    """
    _seed()
    abierta = AnimalBatchMembership.objects.filter(date_to__isnull=True).first()
    assert abierta is not None

    with pytest.raises(IntegrityError):
        AnimalBatchMembership.objects.create(
            animal_id=abierta.animal_id,
            batch_id=abierta.batch_id,
            date_from=abierta.date_from + datetime.timedelta(days=1),
        )


@pytest.mark.django_db
def test_cada_lote_come_una_racion_detras_de_otra_sin_solaparse():
    """Los periodos de ración también son partición: cortes en las formulaciones."""
    _seed()

    por_lote: dict[int, list[tuple[datetime.date, datetime.date]]] = defaultdict(list)
    for period in BatchRation.objects.all():
        hasta = period.date_to or datetime.date.max
        por_lote[period.batch_id].append((period.date_from, hasta))

    assert por_lote
    for periodos in por_lote.values():
        periodos.sort()
        for anterior, siguiente in itertools.pairwise(periodos):
            assert anterior[1] < siguiente[0], (anterior, siguiente)


@pytest.mark.django_db
def test_toda_fila_cargada_sabe_de_donde_viene():
    """Nada entra sin procedencia: es lo que sostiene el registro de cargas."""
    _seed()

    assert not Farm.objects.filter(ingestion_run__isnull=True).exists()
    assert not Animal.objects.filter(ingestion_run__isnull=True).exists()
    assert not DailyYield.objects.filter(ingestion_run__isnull=True).exists()
    assert not MilkRecord.objects.filter(ingestion_run__isnull=True).exists()


@pytest.mark.django_db
def test_la_produccion_llega_al_animal_que_el_censo_declaro():
    """El robot escribe el crotal a su manera y aun así casa con el del censo.

    Es la reconciliación entera: dos ficheros sin nada en común salvo un
    identificador que ninguno de los dos escribe igual.
    """
    _seed()

    for daily_yield in DailyYield.objects.select_related("animal")[:20]:
        animal = daily_yield.animal
        assert len(animal.ear_tag) == 14  # ES + 12 dígitos, la forma canónica
        # La raza y el nacimiento solo los sabe el censo: si la producción cuelga
        # de un animal con esos datos, las dos fuentes se han encontrado.
        assert animal.birth_date is not None
        assert animal.breed in Animal.Breed.values


@pytest.mark.django_db
def test_relanzar_con_la_misma_semilla_da_los_mismos_datos():
    """Misma semilla ⇒ mismos datos en todo el recorrido, no solo al generar."""
    _seed(seed=5)
    primera = _produccion()

    _seed(seed=5)
    segunda = _produccion()

    assert primera == segunda
    assert Animal.objects.count() == 4


@pytest.mark.django_db
def test_semillas_distintas_producen_datos_distintos():
    """Si no divergen, la semilla no está teniendo efecto en el recorrido."""
    _seed(seed=1)
    primera = _produccion()

    _seed(seed=2)
    segunda = _produccion()

    assert primera != segunda


@pytest.mark.django_db
def test_resembrar_la_misma_ventana_sin_borrar_actualiza_en_vez_de_duplicar():
    """El camino de una entrega corregida que se vuelve a ingerir.

    Es el único test que ejercita los cargadores sobre filas que ya existen: el
    resto de la batería siembra siempre con `--clear`, es decir, sobre una base
    vacía, y por eso no ve lo que hace el upsert cuando encuentra algo.
    """
    _seed()
    inventario = _inventario()
    pertenencias = _pertenencias()
    produccion = _produccion()

    _seed(clear=False)

    assert _inventario() == inventario
    assert _pertenencias() == pertenencias
    assert _produccion() == produccion


@pytest.mark.django_db
def test_resembrar_otra_ventana_sin_borrar_choca_con_el_periodo_abierto():
    """La idempotencia del upsert alcanza a la misma ventana, no a otra.

    La clave natural de una pertenencia incluye su fecha de inicio, así que mover
    la ventana recalcula la partición y las filas nuevas no reconocen a las
    viejas: intentan insertarse y el índice único parcial de "un solo periodo
    abierto por animal" las rechaza. Resembrar otra ventana exige `--clear`, y
    este test lo deja escrito en lugar de dejarlo como sorpresa.
    """
    _seed()
    desplazamiento = datetime.timedelta(days=30)

    with pytest.raises(IntegrityError, match="one_open_per_animal"):
        call_command(
            "seed",
            seed=42,
            farms=1,
            animals_per_farm=4,
            start=START + desplazamiento,
            end=END + desplazamiento,
            clear=False,
        )
