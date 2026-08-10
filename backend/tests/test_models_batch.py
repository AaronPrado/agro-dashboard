"""Tests del lote y su alimentación, con foco en la vigencia temporal.

El no-solape de periodos es la decisión de diseño más delicada del modelo: se
comprueba en `clean()` y no en la base de datos, salvo la parte que sí cabe en un
índice único parcial. Estos tests fijan las dos mitades —lo que protege y lo que
no— para que el límite quede documentado y no se descubra por sorpresa.
"""

import datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError

from farms.models import (
    Animal,
    AnimalBatch,
    AnimalBatchMembership,
    BatchRation,
    Crop,
    Farm,
    Plot,
    Ration,
    RationIngredient,
    RawMaterial,
    Silage,
)

ENERO = datetime.date(2026, 1, 1)
FIN_ENERO = datetime.date(2026, 1, 31)
FEBRERO = datetime.date(2026, 2, 1)
FIN_FEBRERO = datetime.date(2026, 2, 28)
MARZO = datetime.date(2026, 3, 1)


def pertenencia(animal, batch, desde, hasta=None):
    """Construye una pertenencia sin guardarla, para poder validarla aparte."""
    return AnimalBatchMembership(animal=animal, batch=batch, date_from=desde, date_to=hasta)


@pytest.mark.django_db
def test_batch_str_es_el_nombre(batch):
    """El lote se identifica por su nombre dentro de la explotación."""
    assert str(batch) == "Alta producción"


@pytest.mark.django_db
def test_batch_name_unico_por_granja(farm, batch):
    """Dos lotes de la misma explotación no pueden llamarse igual."""
    with pytest.raises(IntegrityError):
        AnimalBatch.objects.create(farm=farm, name="Alta producción")


@pytest.mark.django_db
def test_pertenencias_consecutivas_son_validas(animal, batch):
    """Cerrar un periodo y abrir el siguiente al día siguiente es el caso normal."""
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )

    siguiente = pertenencia(animal, batch, FEBRERO, FIN_FEBRERO)

    siguiente.full_clean()


@pytest.mark.django_db
def test_pertenencia_solapada_se_rechaza(animal, batch):
    """Un animal no puede estar en dos sitios a la vez: `clean()` lo impide."""
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )

    solapada = pertenencia(animal, batch, datetime.date(2026, 1, 15), FIN_FEBRERO)

    with pytest.raises(ValidationError):
        solapada.full_clean()


@pytest.mark.django_db
def test_compartir_un_solo_dia_ya_es_solape(animal, batch):
    """El intervalo es cerrado por ambos extremos: el día 31 pertenece al periodo.

    Fija la decisión de que "del 1 al 31" incluye el 31. Si los intervalos fuesen
    semiabiertos, este caso sería válido y el modelo diría otra cosa.
    """
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )

    pegada = pertenencia(animal, batch, FIN_ENERO, FIN_FEBRERO)

    with pytest.raises(ValidationError):
        pegada.full_clean()


@pytest.mark.django_db
def test_un_periodo_abierto_bloquea_cualquier_periodo_posterior(animal, batch):
    """`date_to` nulo significa "vigente", y se comporta como fecha infinita."""
    AnimalBatchMembership.objects.create(animal=animal, batch=batch, date_from=ENERO)

    posterior = pertenencia(animal, batch, MARZO, datetime.date(2026, 4, 1))

    with pytest.raises(ValidationError):
        posterior.full_clean()


@pytest.mark.django_db
def test_el_solape_solo_mira_al_mismo_animal(farm, animal, batch):
    """El ámbito del no-solape es el animal: otro puede tener las mismas fechas."""
    otro = Animal.objects.create(farm=farm, ear_tag="ES0002", birth_date=datetime.date(2021, 3, 1))
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )

    misma_ventana = pertenencia(otro, batch, ENERO, FIN_ENERO)

    misma_ventana.full_clean()


@pytest.mark.django_db
def test_editar_una_pertenencia_no_la_solapa_consigo_misma(animal, batch):
    """Al validar una fila ya guardada hay que excluirla de la comparación."""
    guardada = AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )

    guardada.date_to = FIN_FEBRERO

    guardada.full_clean()


@pytest.mark.django_db
def test_dos_periodos_abiertos_los_rechaza_la_base(animal, batch):
    """El índice único parcial no depende de `full_clean()`: nadie lo esquiva.

    Es la mitad del no-solape que sí se delega en PostgreSQL, y cubre el error
    más frecuente: dejar abierta la pertenencia vieja al abrir la nueva.
    """
    AnimalBatchMembership.objects.create(animal=animal, batch=batch, date_from=ENERO)

    with pytest.raises(IntegrityError):
        AnimalBatchMembership.objects.create(animal=animal, batch=batch, date_from=MARZO)


@pytest.mark.django_db
def test_el_no_solape_no_protege_a_objects_create(animal, batch):
    """Documenta el límite conocido de la decisión de diseño, no un descuido.

    `objects.create()` y `bulk_create()` no llaman a `full_clean()`, así que el
    no-solape de periodos cerrados solo alcanza al admin y a los formularios. Una
    restricción de exclusión en la base sería la respuesta completa; quien cargue
    datos en masa es responsable de no generar solapes.
    """
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_ENERO
    )
    AnimalBatchMembership.objects.create(
        animal=animal, batch=batch, date_from=ENERO, date_to=FIN_FEBRERO
    )

    assert AnimalBatchMembership.objects.filter(animal=animal).count() == 2


@pytest.mark.django_db
def test_pertenencia_rechaza_fin_anterior_al_inicio(animal, batch):
    """Restricción aritmética, esta sí en la base: un periodo no puede ir hacia atrás."""
    with pytest.raises(IntegrityError):
        AnimalBatchMembership.objects.create(
            animal=animal, batch=batch, date_from=FIN_ENERO, date_to=ENERO
        )


@pytest.mark.django_db
def test_str_de_pertenencia_marca_la_vigente(animal, batch):
    """La etiqueta del admin distingue de un vistazo la pertenencia en curso."""
    abierta = AnimalBatchMembership.objects.create(animal=animal, batch=batch, date_from=ENERO)

    assert str(abierta) == "ES221100010001 · Alta producción · 2026-01-01 → vigente"


@pytest.mark.django_db
def test_ration_str_incluye_la_fecha_de_formulacion(ration):
    """Una ración es una formulación fechada, y su etiqueta lo refleja."""
    assert str(ration) == "Lactación alta (2026-01-15)"


@pytest.mark.django_db
def test_reformular_una_racion_crea_otra_fila(farm, ration):
    """Las raciones son inmutables: reformular es crear, no editar.

    Por eso el unique incluye la fecha de formulación. Así el periodo de
    `BatchRation` basta para saber qué comió un lote sin historificar la receta.
    """
    Ration.objects.create(farm=farm, name="Lactación alta", formulated_on=datetime.date(2026, 6, 1))

    assert Ration.objects.filter(farm=farm, name="Lactación alta").count() == 2


@pytest.mark.django_db
def test_ingrediente_admite_un_ensilado_propio(ration, silage):
    """La mitad propia de la ración apunta al silo de la explotación."""
    ingrediente = RationIngredient.objects.create(
        ration=ration, silage=silage, dry_matter_kg=Decimal("8.50")
    )

    assert str(ingrediente).endswith("8.50 kg MS")


@pytest.mark.django_db
def test_ingrediente_admite_una_materia_prima(ration):
    """La mitad comprada apunta al catálogo global de materias primas."""
    materia = RawMaterial.objects.create(
        name="Harina de soja 44", category=RawMaterial.Category.CONCENTRATE
    )

    ingrediente = RationIngredient.objects.create(
        ration=ration, raw_material=materia, dry_matter_kg=Decimal("2.00")
    )

    assert ingrediente.silage is None


@pytest.mark.django_db
def test_ingrediente_rechaza_las_dos_fuentes_a_la_vez(ration, silage):
    """El CheckConstraint es un XOR: exactamente una fuente, no dos."""
    materia = RawMaterial.objects.create(
        name="Harina de soja 44", category=RawMaterial.Category.CONCENTRATE
    )

    with pytest.raises(IntegrityError):
        RationIngredient.objects.create(
            ration=ration, silage=silage, raw_material=materia, dry_matter_kg=Decimal("1.00")
        )


@pytest.mark.django_db
def test_ingrediente_rechaza_quedarse_sin_fuente(ration):
    """Un ingrediente sin origen no es trazable, que es justo lo que se vende."""
    with pytest.raises(IntegrityError):
        RationIngredient.objects.create(ration=ration, dry_matter_kg=Decimal("1.00"))


@pytest.mark.django_db
def test_ingrediente_rechaza_materia_seca_no_positiva(ration, silage):
    """Aportar cero kilos no es un ingrediente: es no estar en la ración."""
    with pytest.raises(IntegrityError):
        RationIngredient.objects.create(ration=ration, silage=silage, dry_matter_kg=Decimal("0"))


@pytest.mark.django_db
def test_un_ensilado_no_se_repite_en_la_misma_racion(ration, silage):
    """Dos líneas del mismo silo serían una carga duplicada, no una receta."""
    RationIngredient.objects.create(ration=ration, silage=silage, dry_matter_kg=Decimal("8.50"))

    with pytest.raises(IntegrityError):
        RationIngredient.objects.create(ration=ration, silage=silage, dry_matter_kg=Decimal("2.00"))


@pytest.mark.django_db
def test_full_clean_rechaza_un_ensilado_de_otra_explotacion(ration):
    """Coherencia que cruza cuatro tablas y que ningún CheckConstraint alcanza.

    `silage → crop → plot → farm` tiene que desembocar en la misma granja que la
    ración. Como la comprobación vive en `clean()`, comparte el límite del
    no-solape: protege al admin, no a una carga masiva.
    """
    otra_granja = Farm.objects.create(
        name="A Ponte", code="a-ponte", municipality="Chantada", province="Lugo"
    )
    otra_parcela = Plot.objects.create(
        farm=otra_granja, name="Leira allea", code="P-001", area_ha=Decimal("1.0000")
    )
    otro_cultivo = Crop.objects.create(plot=otra_parcela, species=Crop.Species.MAIZE, season=2025)
    silo_ajeno = Silage.objects.create(crop=otro_cultivo, code="S-AJENO")

    ingrediente = RationIngredient(ration=ration, silage=silo_ajeno, dry_matter_kg=Decimal("5.00"))

    with pytest.raises(ValidationError):
        ingrediente.full_clean()


@pytest.mark.django_db
def test_no_se_puede_borrar_un_ensilado_ya_usado_en_una_racion(ration, silage):
    """PROTECT, no CASCADE: borrar el silo destruiría el historial de alimentación.

    Es el primer punto del modelo donde el borrado deja de ser regenerable, y por
    eso el criterio cambia respecto a las ramas derivadas del dominio lechero.
    """
    RationIngredient.objects.create(ration=ration, silage=silage, dry_matter_kg=Decimal("8.50"))

    with pytest.raises(ProtectedError):
        silage.delete()


@pytest.mark.django_db
def test_la_base_abstracta_valida_tambien_el_solape_de_raciones(batch, ration):
    """`BatchRation` hereda el no-solape sin una línea propia de comparación.

    Es lo que justifica `DatedPeriod`: la lógica de intervalos se escribe una vez
    y el ámbito lo aporta cada modelo con `overlap_scope()`.
    """
    BatchRation.objects.create(batch=batch, ration=ration, date_from=ENERO, date_to=FIN_ENERO)

    solapada = BatchRation(
        batch=batch, ration=ration, date_from=datetime.date(2026, 1, 20), date_to=FIN_FEBRERO
    )

    with pytest.raises(ValidationError):
        solapada.full_clean()


@pytest.mark.django_db
def test_dos_raciones_abiertas_para_un_lote_las_rechaza_la_base(batch, ration):
    """Mismo índice único parcial que en la pertenencia, mismo ámbito: el lote."""
    BatchRation.objects.create(batch=batch, ration=ration, date_from=ENERO)

    with pytest.raises(IntegrityError):
        BatchRation.objects.create(batch=batch, ration=ration, date_from=MARZO)
