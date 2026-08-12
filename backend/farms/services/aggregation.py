"""Servicios de agregación de la API.

Totales, medias y conteos se resuelven aquí con el ORM y viajan ya calculados:
el cliente pinta, no cruza series. Cada función devuelve un QuerySet sin
evaluar, para que la vista pueda seguir filtrando, ordenando y paginando encima.
"""

from datetime import date

from django.db.models import Aggregate, Avg, Count, F, OuterRef, Q, QuerySet, Subquery, Sum

from farms.models import (
    AnalysisResult,
    AnimalBatch,
    BatchRation,
    DailyYield,
    Farm,
    MilkRecord,
)

# La relación entre la composición de la ración y estos analitos está plantada a
# propósito por el generador (`services/milk_quality.py`). Viaja con la respuesta
# para que ningún consumidor pueda leerla como un hallazgo.
SYNTHETIC_MILK_NOTICE = (
    "Los analitos de leche proceden de datos sintéticos: el generador planta a "
    "propósito la relación entre la composición de la ración y su valor. Es una "
    "construcción para poder recorrer la cadena completa, no un hallazgo."
)


def date_window(date_from: date | None, date_to: date | None, field: str = "date") -> Q:
    """Condición sobre un campo de fecha que acota una serie fechada.

    Los dos extremos son opcionales e independientes: sin ninguno la condición
    queda vacía y no filtra nada. `field` permite acotar por la fecha de un
    modelo relacionado sin duplicar la lógica del rango.
    """
    window = Q()
    if date_from is not None:
        window &= Q(**{f"{field}__gte": date_from})
    if date_to is not None:
        window &= Q(**{f"{field}__lte": date_to})
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


def batch_list() -> QuerySet[AnimalBatch]:
    """Lotes con su censo vigente y la ración que comen ahora mismo.

    "Vigente" es el periodo sin fecha de fin, no el que incluye la fecha de hoy:
    el modelo representa así lo que sigue abierto, y hay un índice único parcial
    que garantiza que no haya dos por lote.
    """
    open_ration = BatchRation.objects.filter(
        batch=OuterRef("pk"),
        date_to__isnull=True,
    ).values("ration__name")[:1]

    return (
        AnimalBatch.objects.select_related("farm")
        .annotate(
            active_animals=Count("memberships", filter=Q(memberships__date_to__isnull=True)),
            current_ration=Subquery(open_ration),
        )
        .order_by("farm__name", "name", "pk")
    )


def _batch_records(records: QuerySet, batch: AnimalBatch, window: Q) -> QuerySet:
    """Restringe una serie fechada de animal a su pertenencia al lote.

    Todas las condiciones sobre la pertenencia viajan en una única llamada a
    `filter()`. En una relación multivaluada, dos `filter()` encadenados abren
    JOIN distintos y cada condición podría satisfacerla una pertenencia
    diferente: el animal contaría por haber estado en el lote alguna vez, no por
    haberlo estado el día de la medida.

    Que un registro no case con dos pertenencias a la vez lo garantiza el
    no-solape de los periodos, no esta consulta.
    """
    return records.filter(
        window,
        Q(animal__batch_memberships__date_to__isnull=True)
        | Q(date__lte=F("animal__batch_memberships__date_to")),
        animal__batch_memberships__batch=batch,
        date__gte=F("animal__batch_memberships__date_from"),
    )


def batch_milk_analytes(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet:
    """Media de cada analito medido en las muestras de leche del lote.

    Recorrer `milk_sample__batch` deja fuera por construcción los resultados de
    forraje: `AnalysisResult` guarda las dos matrices en la misma tabla, con las
    dos claves ajenas excluyentes, y este JOIN solo alcanza a la de leche.
    """
    return (
        AnalysisResult.objects.filter(
            date_window(date_from, date_to, field="milk_sample__date"),
            milk_sample__batch=batch,
        )
        .values("analyte__code", "analyte__name", "analyte__unit")
        .annotate(avg_value=Avg("value"), samples=Count("pk"))
        .order_by("analyte__name")
    )


def batch_summary(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Resumen de un lote: qué produce, qué calidad da y con qué perfil analítico.

    La producción y los controles se restringen a los días en que cada animal
    pertenecía al lote, no a quienes están hoy en él: preguntarle a un lote qué
    produjo en marzo es preguntar por quienes lo formaban en marzo.

    `milk_records` acompaña a `scc_over_limit` porque aquí el conteo sale de un
    `aggregate()`, que siempre devuelve fila: sin el denominador, "cero fuera de
    límite" no se distinguiría de "ningún control".
    """
    window = date_window(date_from, date_to)
    yields = _batch_records(DailyYield.objects.all(), batch, window)
    records = _batch_records(MilkRecord.objects.all(), batch, window)

    return {
        "active_animals": batch.memberships.filter(date_to__isnull=True).count(),
        **yields.aggregate(
            total_liters=Sum("liters"),
            avg_daily_liters=Avg("liters"),
        ),
        **records.aggregate(
            milk_records=Count("pk"),
            avg_fat_pct=Avg("fat_pct"),
            avg_protein_pct=Avg("protein_pct"),
            scc_over_limit=Count(
                "pk",
                filter=Q(somatic_cell_count__gt=MilkRecord.LEGAL_SCC_LIMIT),
            ),
        ),
        "milk_analytes": batch_milk_analytes(batch, date_from, date_to),
        "milk_analytes_notice": SYNTHETIC_MILK_NOTICE,
    }
