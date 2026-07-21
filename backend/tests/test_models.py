"""Tests de los modelos del dominio: representación, restricciones y relaciones."""

import datetime
from decimal import Decimal

import pytest
from django.db import DataError, IntegrityError

from farms.models import Animal, Farm, Milking, MilkRecord


@pytest.fixture
def farm(db):
    """Granja base sobre la que colgar animales en los tests."""
    return Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )


@pytest.fixture
def animal(farm):
    """Animal base sobre el que colgar registros de producción."""
    return Animal.objects.create(
        farm=farm,
        ear_tag="ES0001",
        birth_date=datetime.date(2021, 3, 1),
    )


@pytest.mark.django_db
def test_farm_str_incluye_nombre_y_codigo():
    """La etiqueta del admin identifica la granja sin ambigüedad."""
    farm = Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )

    assert str(farm) == "Casa Grande (casa-grande)"


@pytest.mark.django_db
def test_farm_code_es_unico():
    """El código identifica la granja en la API, así que no puede repetirse."""
    Farm.objects.create(
        name="Casa Grande",
        code="casa-grande",
        municipality="Sarria",
        province="Lugo",
    )

    with pytest.raises(IntegrityError):
        Farm.objects.create(
            name="Otra granja",
            code="casa-grande",
            municipality="Chantada",
            province="Lugo",
        )


@pytest.mark.django_db
def test_farm_ordenacion_por_defecto_alfabetica():
    """Meta.ordering garantiza un orden estable, requisito de la paginación."""
    Farm.objects.create(name="Zaragoza", code="z", municipality="A", province="Lugo")
    Farm.objects.create(name="Abegondo", code="a", municipality="B", province="A Coruña")

    assert [farm.name for farm in Farm.objects.all()] == ["Abegondo", "Zaragoza"]


@pytest.mark.django_db
def test_farm_created_at_se_rellena_sola():
    """auto_now_add sella el alta sin que el generador de datos tenga que pasarla."""
    farm = Farm.objects.create(
        name="Casa Grande", code="cg", municipality="Sarria", province="Lugo"
    )

    assert farm.created_at is not None


@pytest.mark.django_db
def test_animal_str_muestra_crotal_y_raza_legible():
    """get_breed_display() traduce el valor de BD a la etiqueta en castellano."""
    farm = Farm.objects.create(name="A", code="a", municipality="Sarria", province="Lugo")
    animal = Animal.objects.create(
        farm=farm,
        ear_tag="ES1234567890",
        birth_date=datetime.date(2021, 3, 1),
        breed=Animal.Breed.BROWN_SWISS,
    )

    assert str(animal) == "ES1234567890 (Parda Alpina)"


@pytest.mark.django_db
def test_animal_crotal_unico_dentro_de_la_granja(farm):
    """El UniqueConstraint (farm, ear_tag) lo impone la base de datos."""
    Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))

    with pytest.raises(IntegrityError):
        Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2022, 5, 4))


@pytest.mark.django_db
def test_animal_mismo_crotal_permitido_en_granjas_distintas(farm):
    """La unicidad es por granja (decisión D2), no global."""
    otra = Farm.objects.create(
        name="Outeiro", code="outeiro", municipality="Lalín", province="Pontevedra"
    )
    Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))

    Animal.objects.create(farm=otra, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))

    assert Animal.objects.filter(ear_tag="ES0001").count() == 2


@pytest.mark.django_db
def test_animal_no_admite_baja_anterior_al_nacimiento(farm):
    """El CheckConstraint protege de fechas incoherentes aunque se inserte sin validar."""
    with pytest.raises(IntegrityError):
        Animal.objects.create(
            farm=farm,
            ear_tag="ES0002",
            birth_date=datetime.date(2022, 1, 1),
            culled_date=datetime.date(2021, 12, 31),
        )


@pytest.mark.django_db
def test_animal_en_activo_pasa_la_validacion_del_constraint(farm):
    """La rama `culled_date IS NULL` del CheckConstraint existe por esto.

    En SQL sobra: `NULL >= birth_date` evalúa a NULL y un CHECK solo falla si
    da FALSE. Pero full_clean() evalúa la condición como un booleano de Python,
    donde ese NULL es falsy: sin esa rama, todo animal sin fecha de baja sería
    rechazado por el admin y los formularios.
    """
    animal = Animal(farm=farm, ear_tag="ES0003", birth_date=datetime.date(2021, 3, 1))

    animal.full_clean()


@pytest.mark.django_db
def test_animal_accesible_desde_la_granja_por_related_name(farm):
    """related_name="animals" es el camino inverso que usarán los agregados."""
    Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))
    Animal.objects.create(farm=farm, ear_tag="ES0002", birth_date=datetime.date(2021, 4, 2))

    assert farm.animals.count() == 2


@pytest.mark.django_db
def test_animales_en_activo_son_los_que_no_tienen_fecha_de_baja(farm):
    """Sin campo `active`: el estado se deriva de culled_date."""
    Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))
    Animal.objects.create(
        farm=farm,
        ear_tag="ES0002",
        birth_date=datetime.date(2021, 4, 2),
        culled_date=datetime.date(2024, 6, 1),
    )

    assert farm.animals.filter(culled_date__isnull=True).count() == 1


@pytest.mark.django_db
def test_animal_borrado_en_cascada_al_borrar_la_granja(farm):
    """on_delete=CASCADE: un animal sin granja no significa nada."""
    Animal.objects.create(farm=farm, ear_tag="ES0001", birth_date=datetime.date(2021, 3, 1))

    farm.delete()

    assert Animal.objects.count() == 0


@pytest.mark.django_db
def test_milking_str_resume_animal_fecha_y_litros(animal):
    """Etiqueta legible para el admin, donde los ordeños se listan en masa."""
    milking = Milking.objects.create(
        animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("28.40")
    )

    assert str(milking) == "ES0001 · 2024-05-10 · 28.40 L"


@pytest.mark.django_db
def test_milking_un_registro_por_animal_y_dia(animal):
    """Decisión F1: la granularidad es diaria, y la BD la impone."""
    Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("28.40"))

    with pytest.raises(IntegrityError):
        Milking.objects.create(
            animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("12.00")
        )


@pytest.mark.django_db
def test_milking_rechaza_litros_negativos(animal):
    """Una producción negativa es corrupción, no un dato atípico."""
    with pytest.raises(IntegrityError):
        Milking.objects.create(
            animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("-1.00")
        )


@pytest.mark.django_db
def test_milking_admite_litros_nulos_para_medicion_fallida(animal):
    """NULL distingue "no se midió" de "produjo cero", que no es lo mismo."""
    milking = Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 10), liters=None)

    assert milking.liters is None


@pytest.mark.django_db
def test_milking_los_litros_llegan_como_decimal_exacto(animal):
    """DecimalField, no FloatField: la agregación posterior debe ser exacta."""
    Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("28.40"))

    assert Milking.objects.get().liters == Decimal("28.40")


@pytest.mark.django_db
def test_milking_ordenacion_por_defecto_mas_reciente_primero(animal):
    """El dashboard mira los últimos días; el desempate mantiene estable la paginación."""
    Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 9), liters=Decimal("20.00"))
    Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 11), liters=Decimal("22.00"))

    fechas = [milking.date for milking in Milking.objects.all()]

    assert fechas == [datetime.date(2024, 5, 11), datetime.date(2024, 5, 9)]


@pytest.mark.django_db
def test_milking_borrado_en_cascada_al_borrar_la_granja(farm, animal):
    """El borrado en cascada alcanza dos niveles: granja → animal → ordeños."""
    Milking.objects.create(animal=animal, date=datetime.date(2024, 5, 10), liters=Decimal("28.40"))

    farm.delete()

    assert Milking.objects.count() == 0


@pytest.mark.django_db
def test_milk_record_str_identifica_animal_y_fecha(animal):
    """El control se identifica por animal y fecha, que además son su clave única."""
    record = MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))

    assert str(record) == "ES0001 · control 2024-05-01"


@pytest.mark.django_db
def test_milk_record_un_control_por_animal_y_fecha(animal):
    """El control lechero es mensual: no hay dos analíticas del mismo día."""
    MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))

    with pytest.raises(IntegrityError):
        MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))


@pytest.mark.django_db
def test_milk_record_rechaza_porcentaje_negativo(animal):
    """Lo cubre el CheckConstraint: numeric acepta negativos, el dominio no."""
    with pytest.raises(IntegrityError):
        MilkRecord.objects.create(
            animal=animal, date=datetime.date(2024, 5, 1), fat_pct=Decimal("-1.00")
        )


@pytest.mark.django_db
def test_milk_record_rechaza_porcentaje_por_encima_de_cien(animal):
    """Lo cubre el propio tipo: numeric(4, 2) no representa valores >= 100.

    De ahí que el constraint solo vigile el límite inferior; el superior ya
    lo impone la columna, y el error que llega es DataError, no IntegrityError.
    """
    with pytest.raises(DataError):
        MilkRecord.objects.create(
            animal=animal, date=datetime.date(2024, 5, 1), fat_pct=Decimal("120.00")
        )


@pytest.mark.django_db
def test_milk_record_admite_valores_atipicos_dentro_del_rango(animal):
    """El generador crea outliers a propósito: la BD no debe estorbarlos."""
    record = MilkRecord.objects.create(
        animal=animal,
        date=datetime.date(2024, 5, 1),
        fat_pct=Decimal("6.80"),
        protein_pct=Decimal("2.10"),
        somatic_cell_count=1_500_000,
    )

    assert record.fat_pct == Decimal("6.80")
    assert record.somatic_cell_count == 1_500_000


@pytest.mark.django_db
def test_milk_record_admite_analitica_incompleta(animal):
    """Una analítica no disponible se representa con NULL, no con ceros."""
    record = MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))

    assert record.fat_pct is None
    assert record.protein_pct is None
    assert record.somatic_cell_count is None


def test_milk_record_limite_legal_de_celulas_somaticas():
    """El umbral del Reglamento (CE) 853/2004 vive en el modelo, no en las vistas."""
    assert MilkRecord.LEGAL_SCC_LIMIT == 400_000


@pytest.mark.django_db
def test_milk_records_accesibles_desde_el_animal(animal):
    """related_name="milk_records" separa los controles de los ordeños."""
    MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 4, 1))
    MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))

    assert animal.milk_records.count() == 2


@pytest.mark.django_db
def test_milk_record_borrado_en_cascada_al_borrar_el_animal(animal):
    """Una analítica sin animal al que atribuirla no significa nada."""
    MilkRecord.objects.create(animal=animal, date=datetime.date(2024, 5, 1))

    animal.delete()

    assert MilkRecord.objects.count() == 0
