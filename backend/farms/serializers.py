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
