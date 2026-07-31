"""Filtros de la API: traducen parámetros de consulta en filtros del ORM."""

from django_filters import rest_framework as filters

from farms.models import Animal, DailyYield, Farm, MilkRecord


class AnimalFilter(filters.FilterSet):
    """Filtros del listado de animales."""

    # "culled_date" representa la baja del animal
    active = filters.BooleanFilter(
        field_name="culled_date",
        lookup_expr="isnull",
        label="solo animales en la explotación",
    )

    class Meta:
        model = Animal
        fields = ["farm", "breed"]


class AnimalRecordFilter(filters.FilterSet):
    """Filtros comunes a los registros fechados que cuelgan de un animal.

    La producción diaria y los controles lecheros comparten la misma forma
    —pertenecen a un animal y llevan fecha—, así que comparten también su juego
    de filtros.
    """

    farm = filters.ModelChoiceFilter(
        field_name="animal__farm",
        queryset=Farm.objects.all(),
        label="granja",
    )
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte", label="desde")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte", label="hasta")


class DailyYieldFilter(AnimalRecordFilter):
    """Filtros de la producción diaria."""

    class Meta:
        model = DailyYield
        fields = ["animal"]


class MilkRecordFilter(AnimalRecordFilter):
    """Filtros de los controles lecheros."""

    class Meta:
        model = MilkRecord
        fields = ["animal"]
