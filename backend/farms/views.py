"""Vistas de la app farms."""

from django.db import connection
from django.db.utils import OperationalError
from django.http import HttpRequest, JsonResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from farms.filters import AnimalFilter, DailyYieldFilter, MilkRecordFilter
from farms.models import Animal, DailyYield, Farm, MilkRecord
from farms.serializers import (
    AnimalBatchSerializer,
    AnimalSerializer,
    BatchSummarySerializer,
    DailyYieldSerializer,
    DateWindowSerializer,
    FarmSerializer,
    FarmSummarySerializer,
    MilkRecordSerializer,
)
from farms.services.aggregation import batch_list, batch_summary, farm_summaries


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
    filterset_fields = ["province"]

    @action(detail=False)
    def summary(self, request: Request) -> Response:
        """Producción y calidad agregadas, una fila por explotación.

        Acepta `date_from` y `date_to` para acotar las series fechadas, y sigue
        respetando el filtro de provincia y la paginación del propio recurso.
        """
        window = DateWindowSerializer(data=request.query_params)
        window.is_valid(raise_exception=True)
        summaries = self.filter_queryset(farm_summaries(**window.validated_data))
        page = self.paginate_queryset(summaries)
        return self.get_paginated_response(FarmSummarySerializer(page, many=True).data)


class AnimalViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de animales."""

    queryset = Animal.objects.select_related("farm")
    serializer_class = AnimalSerializer
    ordering_fields = ["ear_tag", "birth_date", "lactation_number"]
    filterset_class = AnimalFilter


class DailyYieldViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de la producción diaria."""

    queryset = DailyYield.objects.select_related("animal")
    serializer_class = DailyYieldSerializer
    ordering_fields = ["date", "liters"]
    filterset_class = DailyYieldFilter


class MilkRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de los controles lecheros mensuales."""

    queryset = MilkRecord.objects.select_related("animal")
    serializer_class = MilkRecordSerializer
    ordering_fields = ["date", "somatic_cell_count", "fat_pct", "protein_pct"]
    filterset_class = MilkRecordFilter


class AnimalBatchViewSet(viewsets.ReadOnlyModelViewSet):
    """Consulta de los lotes de animales."""

    queryset = batch_list()
    serializer_class = AnimalBatchSerializer
    ordering_fields = ["name", "active_animals"]
    filterset_fields = ["farm"]

    @action(detail=True)
    def summary(self, request: Request, pk: str | None = None) -> Response:
        """Producción, calidad y perfil analítico del lote en un rango de fechas."""
        window = DateWindowSerializer(data=request.query_params)
        window.is_valid(raise_exception=True)
        summary = batch_summary(self.get_object(), **window.validated_data)
        return Response(BatchSummarySerializer(summary).data)
