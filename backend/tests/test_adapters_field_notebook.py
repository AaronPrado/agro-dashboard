"""Tests del adaptador del cuaderno de campo.

Cuarta forma de entrada y la más desordenada: secciones, tabuladores, coma
decimal y el año en dos cifras. Las entregas se escriben a mano para que se vea
qué separa lo que teclea el ganadero de lo que guarda el modelo.
"""

import datetime
from decimal import Decimal

import pytest

from farms.models import Crop, RawMaterial, SourceSystem
from farms.services.adapters.base import AdapterError
from farms.services.adapters.field_notebook import FieldNotebookAdapter

HEADER = ["CUADERNO DE CAMPO", "EXPLOTACION\tcasa-grande", "--"]
PARCELAS = ["[PARCELAS]", "codigo\tnombre\tsuperficie_ha"]
CULTIVOS = ["[CULTIVOS]", "parcela\tespecie\tcampaña\tsiembra\tcosecha"]
SILOS = ["[SILOS]", "parcela\tcampaña\tespecie\tcodigo\tcierre\tapertura"]
MATERIAS = ["[MATERIAS_PRIMAS]", "nombre\tcategoria"]
RACIONES = ["[RACIONES]", "nombre\tformulacion"]
INGREDIENTES = ["[INGREDIENTES]", "racion\tformulacion\ttipo\treferencia\tkg_ms"]


def _feed(*blocks: list[str]) -> str:
    lines = list(HEADER)
    for block in blocks:
        lines.extend(block)
    return "\n".join(lines)


@pytest.fixture
def adapter():
    return FieldNotebookAdapter()


def test_la_parcela_llega_con_su_superficie_en_coma_decimal(adapter):
    """La hoja de cálculo escribe con coma; el modelo guarda un Decimal."""
    batch = adapter.parse(_feed([*PARCELAS, "P-01\tLeira do Souto\t2,35"]))

    plot = batch.plots[0]
    assert plot.farm_code == "casa-grande"
    assert plot.code == "P-01"
    assert plot.name == "Leira do Souto"
    assert plot.area_ha == Decimal("2.35")


def test_el_ano_en_dos_cifras_se_resuelve_al_siglo_actual(adapter):
    """`28-04-25` es 2025: la convención POSIX de `%y`, documentada y aceptada."""
    batch = adapter.parse(_feed([*CULTIVOS, "P-01\tMAIZ\t2025\t28-04-25\t22-09-25"]))

    crop = batch.crops[0]
    assert crop.sowing_date == datetime.date(2025, 4, 28)
    assert crop.harvest_date == datetime.date(2025, 9, 22)


def test_la_especie_se_traduce_al_vocabulario_del_modelo(adapter):
    """El cuaderno dice RAIGRAS; el modelo, `italian_ryegrass`."""
    batch = adapter.parse(_feed([*CULTIVOS, "P-02\tRAIGRAS\t2026\t12-10-25\t05-04-26"]))

    assert batch.crops[0].species == Crop.Species.ITALIAN_RYEGRASS


def test_una_pradera_no_tiene_siembra_y_lo_dice(adapter):
    """El guion es la marca de «no aplica», y no es lo mismo que no saberlo."""
    batch = adapter.parse(_feed([*CULTIVOS, "P-03\tPRADERA\t2026\t-\t20-05-26"]))

    crop = batch.crops[0]
    assert crop.sowing_date is None
    assert crop.harvest_date == datetime.date(2026, 5, 20)


def test_el_silo_arrastra_las_cuatro_senas_de_su_campana(adapter):
    """Una parcela lleva dos especies el mismo año: la rotación de verano e invierno."""
    batch = adapter.parse(_feed([*SILOS, "P-01\t2025\tMAIZ\tS-2025-P01-M\t23-09-25\t28-10-25"]))

    silage = batch.silages[0]
    assert (silage.plot_code, silage.season, silage.species) == (
        "P-01",
        2025,
        Crop.Species.MAIZE,
    )
    assert silage.code == "S-2025-P01-M"
    assert silage.sealed_date == datetime.date(2025, 9, 23)
    assert silage.opened_date == datetime.date(2025, 10, 28)


def test_las_tres_secciones_conviven_en_una_entrega(adapter):
    """El cuaderno se exporta entero, no una hoja por fichero."""
    batch = adapter.parse(
        _feed(
            [*PARCELAS, "P-01\tLeira do Souto\t2,35"],
            [*CULTIVOS, "P-01\tMAIZ\t2025\t28-04-25\t22-09-25"],
            [*SILOS, "P-01\t2025\tMAIZ\tS-2025-P01-M\t23-09-25\t28-10-25"],
        )
    )

    assert (len(batch.plots), len(batch.crops), len(batch.silages)) == (1, 1, 1)
    assert not batch.rejects


def test_una_fila_con_columnas_de_menos_se_rechaza_y_el_resto_entra(adapter):
    """Una fila rota no invalida el cuaderno entero."""
    batch = adapter.parse(
        _feed([*PARCELAS, "P-01\tLeira do Souto\t2,35", "P-02\tA Veiga", "P-03\tAgro Novo\t1,10"])
    )

    assert len(batch.plots) == 2
    assert len(batch.rejects) == 1
    assert batch.rejects[0].line_number == 7
    assert "columnas" in batch.rejects[0].reason


def test_una_especie_desconocida_se_rechaza(adapter):
    """El cuaderno puede traer un cultivo que el modelo no contempla."""
    batch = adapter.parse(_feed([*CULTIVOS, "P-01\tTRIGO\t2025\t28-04-25\t22-09-25"]))

    assert not batch.crops
    assert "especie" in batch.rejects[0].reason


def test_una_seccion_desconocida_aborta_la_entrega(adapter):
    """Si el cuaderno cambia de forma, ninguna fila es de fiar."""
    with pytest.raises(AdapterError):
        adapter.parse(_feed(["[ABONADOS]", "parcela\tproducto\tdosis"]))


def test_unos_encabezados_distintos_abortan_la_entrega(adapter):
    """En una exportación por columnas, el orden es el contrato."""
    with pytest.raises(AdapterError):
        adapter.parse(_feed(["[PARCELAS]", "codigo\tsuperficie_ha\tnombre"]))


def test_una_cabecera_sin_explotacion_aborta_la_entrega(adapter):
    """Sin explotación no se sabe de quién es la parcela."""
    with pytest.raises(AdapterError):
        adapter.parse("CUADERNO DE CAMPO\nEXPLOTACION\t\n--\n")


def test_el_lote_declara_de_que_fuente_viene(adapter):
    """La procedencia viaja con el dato desde el primer momento."""
    batch = adapter.parse(_feed([*PARCELAS, "P-01\tLeira do Souto\t2,35"]))

    assert batch.source == SourceSystem.FIELD_NOTEBOOK


def test_la_materia_prima_es_catalogo_y_no_lleva_explotacion(adapter):
    """Lo que compra un ganadero lo compran todos: el catálogo es común."""
    batch = adapter.parse(_feed([*MATERIAS, "Harina de soja 44\tCONCENTRADO"]))

    material = batch.raw_materials[0]
    assert material.name == "Harina de soja 44"
    assert material.category == RawMaterial.Category.CONCENTRATE
    assert not hasattr(material, "farm_code")


def test_una_categoria_desconocida_se_rechaza(adapter):
    """Mismo criterio que con las razas y las especies: no se absorbe en «otra»."""
    batch = adapter.parse(_feed([*MATERIAS, "Bagazo de cerveza\tHUMEDO"]))

    assert not batch.raw_materials
    assert "categoría" in batch.rejects[0].reason


def test_la_racion_se_identifica_por_nombre_y_fecha_de_formulacion(adapter):
    """Reformular es crear otra ración, no editar esta: la fecha va en la clave."""
    batch = adapter.parse(_feed([*RACIONES, "Lactación alta\t01-02-26"]))

    ration = batch.rations[0]
    assert ration.farm_code == "casa-grande"
    assert ration.name == "Lactación alta"
    assert ration.formulated_on == datetime.date(2026, 2, 1)


def test_un_ingrediente_de_silo_no_lleva_materia_prima(adapter):
    """El fichero trae tipo y referencia; el canónico, dos campos excluyentes."""
    batch = adapter.parse(
        _feed([*INGREDIENTES, "Lactación alta\t01-02-26\tSILO\tS-2025-P01-M\t6,67"])
    )

    ingredient = batch.ration_ingredients[0]
    assert ingredient.silage_code == "S-2025-P01-M"
    assert ingredient.raw_material_name is None
    assert ingredient.dry_matter_kg == Decimal("6.67")


def test_un_ingrediente_comprado_no_lleva_silo(adapter):
    """La otra mitad del excluyente, y la que sostiene el CheckConstraint del modelo."""
    batch = adapter.parse(
        _feed([*INGREDIENTES, "Lactación alta\t01-02-26\tMATERIA_PRIMA\tMaíz grano\t4,35"])
    )

    ingredient = batch.ration_ingredients[0]
    assert ingredient.silage_code is None
    assert ingredient.raw_material_name == "Maíz grano"


def test_un_tipo_de_ingrediente_desconocido_se_rechaza(adapter):
    """Sin saber si la referencia es un silo o un saco, la fila no se puede anclar."""
    batch = adapter.parse(
        _feed([*INGREDIENTES, "Lactación alta\t01-02-26\tPASTO\tPradera de arriba\t5,00"])
    )

    assert not batch.ration_ingredients
    assert "tipo de ingrediente" in batch.rejects[0].reason
