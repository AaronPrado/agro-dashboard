"""Servicios de agregación de la API.

Totales, medias y conteos se resuelven aquí con el ORM y viajan ya calculados:
el cliente pinta, no cruza series. Cada función devuelve un QuerySet sin
evaluar, para que la vista pueda seguir filtrando, ordenando y paginando encima.
"""

from datetime import date

from django.db.models import Aggregate, Avg, Count, OuterRef, Q, QuerySet, Subquery, Sum

from farms.models import DailyYield, Farm, MilkRecord


def date_window(date_from: date | None, date_to: date | None) -> Q:
    """Condición sobre el campo `date` que acota una serie fechada.

    Los dos extremos son opcionales e independientes: sin ninguno la condición
    queda vacía y no filtra nada.
    """
    window = Q()
    if date_from is not None:
        window &= Q(date__gte=date_from)
    if date_to is not None:
        window &= Q(date__lte=date_to)
    return window


def _per_farm(records: QuerySet, aggregate: Aggregate) -> Subquery:
    """Agrega una serie de animal por la explotación de la fila externa.

    Cada métrica viaja en su propia subconsulta correlacionada. Anotar dos
    relaciones multivaluadas sobre el mismo queryset las uniría por JOIN, y el
    producto cartesiano resultante multiplicaría los totales.
    """
    return Subquery(
        records.filter(animal__farm=OuterRef("pk"))
        .values("animal__farm")
        .annotate(value=aggregate)
        .values("value")
        .order_by()
    )


def farm_summaries(
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[Farm]:
    """Una fila por explotación con su producción y su calidad agregadas.

    El rango de fechas acota las series fechadas, no el censo: la pregunta
    "cuántas vacas hay" no tiene fecha. Una métrica sin dato en la ventana sale
    a `None` y no a cero, la misma distinción entre hueco y lectura ausente que
    sostiene el resto del proyecto.
    """
    window = date_window(date_from, date_to)
    yields = DailyYield.objects.filter(window)
    records = MilkRecord.objects.filter(window)

    return Farm.objects.annotate(
        active_animals=Count("animals", filter=Q(animals__culled_date__isnull=True)),
        total_liters=_per_farm(yields, Sum("liters")),
        avg_daily_liters=_per_farm(yields, Avg("liters")),
        avg_fat_pct=_per_farm(records, Avg("fat_pct")),
        avg_protein_pct=_per_farm(records, Avg("protein_pct")),
        scc_over_limit=_per_farm(
            records,
            Count("pk", filter=Q(somatic_cell_count__gt=MilkRecord.LEGAL_SCC_LIMIT)),
        ),
    ).order_by("name", "pk")
