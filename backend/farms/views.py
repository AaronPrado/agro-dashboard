"""Vistas de la app farms."""

from django.db import connection
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse
from rest_framework import viewsets

from farms.models import Animal, Farm, Milking, MilkRecord
from farms.serializers import (
    AnimalSerializer,
    FarmSerializer,
    MilkingSerializer,
    MilkRecordSerializer,
)


def health(request: HttpRequest) -> JsonResponse:
    """Comprueba que la API responde y que PostgreSQL es accesible.

    Devuelve 200 con estado "ok" si la conexión a la base de datos funciona,
    o 503 si la base de datos no está disponible.
    """
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse(
            {"status": "error", "database": "unavailable"},
            status=503,
        )
    return JsonResponse({"status": "ok", "database": "ok"})


class FarmViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de explotaciones ganaderas."""

    queryset = Farm.objects.order_by("name", "pk")
    serializer_class = FarmSerializer
    ordering_fields = ["name", "code", "created_at"]


class AnimalViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de animales."""

    queryset = Animal.objects.select_related("farm")
    serializer_class = AnimalSerializer
    ordering_fields = ["ear_tag", "birth_date", "lactation_number"]


class MilkingViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de la producción diaria."""

    queryset = Milking.objects.select_related("animal")
    serializer_class = MilkingSerializer
    ordering_fields = ["date", "liters"]


class MilkRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de los controles lecheros mensuales."""

    queryset = MilkRecord.objects.select_related("animal")
    serializer_class = MilkRecordSerializer
    ordering_fields = ["date", "somatic_cell_count", "fat_pct", "protein_pct"]
