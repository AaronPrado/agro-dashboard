"""Serializers de la API"""

from rest_framework import serializers

from farms.models import Animal, DailyYield, Farm, MilkRecord


class FarmSerializer(serializers.ModelSerializer):
    """Representación de una explotación ganadera."""

    class Meta:
        model = Farm
        fields = ["id", "name", "code", "municipality", "province", "created_at"]


class AnimalSerializer(serializers.ModelSerializer):
    """Representación de un animal, con los datos de su granja aplanados."""

    farm_name = serializers.CharField(source="farm.name", read_only=True)
    breed_display = serializers.CharField(source="get_breed_display", read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Animal
        fields = [
            "id",
            "farm",
            "farm_name",
            "ear_tag",
            "breed",
            "breed_display",
            "birth_date",
            "lactation_number",
            "last_calving_date",
            "culled_date",
            "is_active",
        ]


class DailyYieldSerializer(serializers.ModelSerializer):
    """Producción diaria de un animal.

    Expone `farm` como identificador para que el consumidor pueda agrupar por
    explotación sin una consulta extra; sale de `animal.farm_id`, que ya viaja
    en la propia fila del animal y no obliga a cargar la granja.
    """

    animal_ear_tag = serializers.CharField(source="animal.ear_tag", read_only=True)
    farm = serializers.IntegerField(source="animal.farm_id", read_only=True)

    class Meta:
        model = DailyYield
        fields = ["id", "animal", "animal_ear_tag", "farm", "date", "liters"]


class MilkRecordSerializer(serializers.ModelSerializer):
    """Control lechero mensual con la analítica de calidad de la leche."""

    animal_ear_tag = serializers.CharField(source="animal.ear_tag", read_only=True)
    farm = serializers.IntegerField(source="animal.farm_id", read_only=True)

    class Meta:
        model = MilkRecord
        fields = [
            "id",
            "animal",
            "animal_ear_tag",
            "farm",
            "date",
            "fat_pct",
            "protein_pct",
            "somatic_cell_count",
        ]


class DateWindowSerializer(serializers.Serializer):
    """Valida el rango de fechas que parametriza un agregado.

    No es un `FilterSet` a propósito: estas fechas no filtran la colección que
    se devuelve —hay las mismas explotaciones se pida el rango que se pida—,
    sino que son argumentos del cálculo. Y validarlas aquí hace que una fecha
    malformada dé 400 con su mensaje, en vez de ignorarse en silencio.
    """

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs: dict) -> dict:
        if (
            attrs.get("date_from")
            and attrs.get("date_to")
            and attrs["date_from"] > attrs["date_to"]
        ):
            raise serializers.ValidationError("`date_from` no puede ser posterior a `date_to`.")
        return attrs


class FarmSummarySerializer(serializers.Serializer):
    """Producción y calidad de una explotación, agregadas en un rango de fechas.

    No es un `ModelSerializer` porque lo que viaja no es la explotación: los
    campos agregados no existen en el modelo y salen nulos cuando el rango no
    contiene ninguna medida.
    """

    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    province = serializers.CharField(read_only=True)
    active_animals = serializers.IntegerField(read_only=True)
    total_liters = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    avg_daily_liters = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    avg_fat_pct = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    avg_protein_pct = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    scc_over_limit = serializers.IntegerField(read_only=True)
