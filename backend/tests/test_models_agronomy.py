"""Tests de la cadena agrícola: representación, restricciones y borrado en cascada."""

import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError

from farms.models import Crop, Farm, NIRAnalysis, Plot, RawMaterial, Silage


@pytest.mark.django_db
def test_plot_str_incluye_nombre_y_superficie(plot):
    """La etiqueta del admin distingue parcelas que comparten nombre de casa."""
    assert str(plot) == "Leira do Souto (2.5000 ha)"


@pytest.mark.django_db
def test_plot_code_unico_dentro_de_la_granja(farm, plot):
    """Dos parcelas de la misma explotación no pueden compartir código."""
    with pytest.raises(IntegrityError):
        Plot.objects.create(
            farm=farm,
            name="Otra leira",
            code="P-001",
            area_ha=Decimal("1.0000"),
        )


@pytest.mark.django_db
def test_plot_code_se_puede_repetir_entre_granjas(plot):
    """El código es único *por granja*: cada fuente numera sus parcelas sin coordinarse."""
    otra_granja = Farm.objects.create(
        name="A Ponte", code="a-ponte", municipality="Chantada", province="Lugo"
    )

    Plot.objects.create(
        farm=otra_granja,
        name="Leira da Ponte",
        code="P-001",
        area_ha=Decimal("3.0000"),
    )

    assert Plot.objects.filter(code="P-001").count() == 2


@pytest.mark.django_db
def test_plot_rechaza_superficie_nula_o_negativa(farm):
    """Una superficie de cero o negativa es imposible, no improbable: la prohíbe la BD."""
    with pytest.raises(IntegrityError):
        Plot.objects.create(
            farm=farm,
            name="Parcela fantasma",
            code="P-999",
            area_ha=Decimal("0"),
        )


@pytest.mark.django_db
def test_plot_borrado_en_cascada_al_borrar_la_granja(farm, plot):
    """La granja es la frontera de tenencia: borrarla limpia también su rama agrícola."""
    farm.delete()

    assert Plot.objects.count() == 0


@pytest.mark.django_db
def test_crop_str_muestra_especie_legible_parcela_y_campana(crop):
    """get_species_display() traduce el valor almacenado a su etiqueta en castellano."""
    assert str(crop) == "Maíz forrajero · Leira do Souto · 2025"


@pytest.mark.django_db
def test_crop_admite_dos_especies_en_la_misma_parcela_y_campana(plot, crop):
    """La rotación es el caso normal, y es la razón de que el unique incluya la especie."""
    Crop.objects.create(
        plot=plot,
        species=Crop.Species.ITALIAN_RYEGRASS,
        season=2025,
        sowing_date=datetime.date(2025, 10, 1),
    )

    assert Crop.objects.filter(plot=plot, season=2025).count() == 2


@pytest.mark.django_db
def test_crop_no_repite_especie_en_la_misma_parcela_y_campana(plot, crop):
    """Un mismo cultivo dos veces en una campaña sería un duplicado de carga."""
    with pytest.raises(IntegrityError):
        Crop.objects.create(plot=plot, species=Crop.Species.MAIZE, season=2025)


@pytest.mark.django_db
def test_crop_rechaza_cosecha_anterior_a_la_siembra(plot):
    """Restricción aritmética: se prohíbe lo imposible, no lo improbable."""
    with pytest.raises(IntegrityError):
        Crop.objects.create(
            plot=plot,
            species=Crop.Species.GRASS_MIX,
            season=2025,
            sowing_date=datetime.date(2025, 5, 1),
            harvest_date=datetime.date(2025, 4, 1),
        )


@pytest.mark.django_db
def test_crop_admite_fechas_ausentes(plot):
    """NULL significa "no registrado" y debe sobrevivir a la validación del admin.

    Es lo que protegen las ramas `isnull=True` del CheckConstraint: `full_clean()`
    evalúa la condición como booleano de Python, donde un NULL es *falsy* y
    rechazaría filas perfectamente válidas.
    """
    cultivo = Crop.objects.create(plot=plot, species=Crop.Species.MAIZE, season=2024)

    cultivo.full_clean()

    assert cultivo.sowing_date is None
    assert cultivo.harvest_date is None


@pytest.mark.django_db
def test_silage_str_identifica_silo_y_procedencia(silage):
    """El silo se lee junto a lo que contiene, que es lo que importa al ganadero."""
    assert str(silage) == "S-2025-01 · Maíz forrajero 2025"


@pytest.mark.django_db
def test_silage_code_unico_dentro_del_cultivo(crop, silage):
    """Dos silos de la misma campaña no pueden compartir código."""
    with pytest.raises(IntegrityError):
        Silage.objects.create(crop=crop, code="S-2025-01")


@pytest.mark.django_db
def test_silage_rechaza_apertura_anterior_al_cierre(crop):
    """No se puede abrir un silo antes de haberlo cerrado."""
    with pytest.raises(IntegrityError):
        Silage.objects.create(
            crop=crop,
            code="S-2025-02",
            sealed_date=datetime.date(2025, 9, 22),
            opened_date=datetime.date(2025, 9, 1),
        )


@pytest.mark.django_db
def test_silage_admite_fechas_ausentes(crop):
    """Un silo cargado desde una fuente sin fechas sigue pasando `full_clean()`."""
    silo = Silage.objects.create(crop=crop, code="S-2025-03")

    silo.full_clean()

    assert silo.sealed_date is None


@pytest.mark.django_db
def test_nir_un_analisis_por_ensilado_y_fecha(silage):
    """El unique da idempotencia a la ingesta: recargar el mismo día no duplica."""
    NIRAnalysis.objects.create(silage=silage, date=datetime.date(2025, 10, 5))

    with pytest.raises(IntegrityError):
        NIRAnalysis.objects.create(silage=silage, date=datetime.date(2025, 10, 5))


@pytest.mark.django_db
def test_nir_no_almacena_los_valores_como_columnas(silage):
    """Los parámetros del NIR cuelgan como resultados por analito, no como campos.

    Fija la decisión de diseño: el mismo par muestra/resultado sirve para el
    forraje y para la leche, y el esquema no cambia al añadir un parámetro nuevo.
    """
    campos = {field.name for field in NIRAnalysis._meta.fields}

    assert campos == {"id", "silage", "date", "laboratory"}


@pytest.mark.django_db
def test_la_cadena_agricola_se_borra_entera_desde_la_granja(farm, silage):
    """Cuatro niveles de CASCADE: granja → parcela → cultivo → silo → análisis."""
    NIRAnalysis.objects.create(silage=silage, date=datetime.date(2025, 10, 5))

    farm.delete()

    assert Plot.objects.count() == 0
    assert Crop.objects.count() == 0
    assert Silage.objects.count() == 0
    assert NIRAnalysis.objects.count() == 0


@pytest.mark.django_db
def test_raw_material_es_catalogo_global_con_nombre_unico():
    """Una materia prima es el mismo producto comercial en todas las explotaciones."""
    RawMaterial.objects.create(name="Harina de soja 44", category=RawMaterial.Category.CONCENTRATE)

    with pytest.raises(IntegrityError):
        RawMaterial.objects.create(
            name="Harina de soja 44", category=RawMaterial.Category.BYPRODUCT
        )
