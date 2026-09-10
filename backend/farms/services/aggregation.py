"""Servicios de agregación de la API.

Totales, medias y conteos se resuelven aquí con el ORM y viajan ya calculados:
el cliente pinta, no cruza series. Cada función devuelve un QuerySet sin
evaluar, para que la vista pueda seguir filtrando, ordenando y paginando encima.
"""

from datetime import date
from decimal import Decimal

from django.db.models import (
    Aggregate,
    Avg,
    Count,
    DateField,
    F,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Greatest, Least

from farms.models import (
    AnalysisResult,
    AnimalBatch,
    BatchMilkSample,
    BatchRation,
    DailyYield,
    Farm,
    MilkRecord,
    TargetProfile,
    TargetRange,
)

# La relación entre la composición de la ración y estos analitos está plantada a
# propósito por el generador (`services/milk_quality.py`). Viaja con la respuesta
# para que ningún consumidor pueda leerla como un hallazgo.
SYNTHETIC_MILK_NOTICE = (
    "Los analitos de leche proceden de datos sintéticos: el generador planta a "
    "propósito la relación entre la composición de la ración y su valor. Es una "
    "construcción para poder recorrer la cadena completa, no un hallazgo."
)

# El veredicto de un perfil no es una propiedad del lote, sino del lote *en una
# ventana*: la ración cambia a lo largo del año y la composición de la leche con
# ella, así que un "cumple" sin fechas promedia regímenes distintos.
TARGET_CHECK_NOTICE = (
    "El resultado es relativo a la ventana consultada: la ración de un lote "
    "cambia a lo largo del año y la composición de su leche con ella. Los "
    "umbrales de cada perfil se derivan del rango publicado de cada analito y "
    "son una interpretación de este proyecto, no la exigencia de un comprador."
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


def batch_daily_yields(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet:
    """Producción del lote día a día, con cuántos animales la sostienen.

    `animals` no es decoración: el total de un lote sube y baja con su censo, y
    sin ese denominador una caída por bajas se leería como una caída de
    rendimiento. Es la misma razón por la que el resumen lleva `milk_records`.

    El `order_by("date")` final no es cosmético. `DailyYield` ordena por defecto
    por `["-date", "animal"]`, y los campos del orden por defecto entran en el
    `GROUP BY` de un `values().annotate()`: sin reemplazarlo, la serie saldría
    agrupada por día *y animal*, con una fila por vaca en lugar de una por día.
    """
    return (
        _batch_records(DailyYield.objects.all(), batch, date_window(date_from, date_to))
        .values("date")
        .annotate(
            total_liters=Sum("liters"),
            avg_liters=Avg("liters"),
            animals=Count("animal", distinct=True),
        )
        .order_by("date")
    )


def batch_milk_samples(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[BatchMilkSample]:
    """Muestras de leche del lote en la ventana, cada una con sus analitos.

    Va por muestra y no por analito porque una muestra es un hecho único con
    varios resultados: aplanarla obligaría al cliente a reagruparla para pintar.
    El `Prefetch` con `select_related` trae los resultados y sus analitos en una
    segunda consulta, no en una por muestra ni en una por analito.
    """
    return (
        BatchMilkSample.objects.filter(date_window(date_from, date_to), batch=batch)
        .prefetch_related(
            Prefetch("results", queryset=AnalysisResult.objects.select_related("analyte"))
        )
        .order_by("date")
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


def batch_ration_periods(
    batch: AnimalBatch,
    window_from: date,
    window_to: date,
) -> QuerySet[BatchRation]:
    """Periodos de ración que solapan la ventana, con sus fechas recortadas a ella.

    Los dos extremos son obligatorios, a diferencia del resto del módulo: pintar
    un periodo como banda exige dos fechas dentro del dominio del eje, y no las
    tiene ni el que empezó antes de la ventana ni el que sigue vigente, cuyo
    `date_to` es nulo. Recortarlos aquí es lo que evita que los calcule el
    cliente.

    `date_from` y `date_to` siguen viajando sin tocar: lo recortado son campos
    aparte, para no hacer pasar por dato del periodo lo que es del encuadre.
    """
    window_end = Value(window_to, output_field=DateField())
    return (
        BatchRation.objects.filter(
            Q(date_to__isnull=True) | Q(date_to__gte=window_from),
            batch=batch,
            date_from__lte=window_to,
        )
        .select_related("ration")
        .annotate(
            starts_on=Greatest(F("date_from"), Value(window_from, output_field=DateField())),
            ends_on=Least(Coalesce(F("date_to"), window_end), window_end),
        )
        .order_by("starts_on")
    )


def batch_timeline(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Todo lo que pinta la gráfica de un lote, casado aquí y no en el cliente.

    Tres series de grano distinto —producción diaria, muestras de leche y
    periodos de ración— sobre un mismo eje, más la ventana efectiva a la que se
    han recortado los periodos. Que viajen juntas es el objetivo del endpoint:
    el cliente superpone capas sin tener que cruzar fechas.

    La ventana efectiva sale de la serie de producción ya traída, sin consulta
    extra, porque viene ordenada. Un lote sin producción en el rango no tiene
    eje sobre el que dibujar bandas, así que los periodos salen vacíos en vez de
    salir sin recortar.
    """
    yields = list(batch_daily_yields(batch, date_from, date_to))
    window_from = yields[0]["date"] if yields else date_from
    window_to = yields[-1]["date"] if yields else date_to

    periods: QuerySet[BatchRation] | list = []
    if window_from is not None and window_to is not None:
        periods = batch_ration_periods(batch, window_from, window_to)

    return {
        "window": {"date_from": window_from, "date_to": window_to},
        "daily_yields": yields,
        "milk_samples": batch_milk_samples(batch, date_from, date_to),
        "ration_periods": periods,
        "milk_analytes_notice": SYNTHETIC_MILK_NOTICE,
    }


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


def _range_status(value: Decimal | None, minimum: Decimal | None, maximum: Decimal | None) -> str:
    """Sitúa un valor medido respecto a un rango objetivo.

    Sin dato se responde `no_data` y nunca `below`: no haber medido no es
    incumplir, igual que en el resto del proyecto un hueco no es un cero.
    """
    if value is None:
        return "no_data"
    if minimum is not None and value < minimum:
        return "below"
    if maximum is not None and value > maximum:
        return "above"
    return "within"


def batch_target_check(
    batch: AnimalBatch,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Compara la leche del lote con cada perfil de destino del catálogo.

    Devuelve todos los perfiles y no solo los que se cumplen: la pregunta útil
    es a qué destinos puede orientarse un lote, y para eso hace falta ver
    también de cuánto se queda corto en los que no.

    No se emite un veredicto global de apto: con datos sintéticos, un booleano
    en pantalla afirma más de lo que estos datos sostienen. Viajan el conteo y
    el detalle por analito, y la lectura la hace quien mira.

    La media sale del ORM; lo que se hace aquí es aplicarle un criterio, que no
    es agregación.
    """
    measured = {row["analyte__code"]: row for row in batch_milk_analytes(batch, date_from, date_to)}
    profiles = []
    for profile in TargetProfile.objects.prefetch_related(
        Prefetch("ranges", queryset=TargetRange.objects.select_related("analyte"))
    ):
        analytes = []
        for target in profile.ranges.all():
            row = measured.get(target.analyte.code)
            value = row["avg_value"] if row else None
            analytes.append(
                {
                    "code": target.analyte.code,
                    "name": target.analyte.name,
                    "unit": target.analyte.unit,
                    "avg_value": value,
                    "samples": row["samples"] if row else 0,
                    "min_value": target.min_value,
                    "max_value": target.max_value,
                    "status": _range_status(value, target.min_value, target.max_value),
                }
            )
        profiles.append(
            {
                "code": profile.code,
                "name": profile.name,
                "description": profile.description,
                "analytes": analytes,
                "within_range": sum(1 for a in analytes if a["status"] == "within"),
                "measured": sum(1 for a in analytes if a["status"] != "no_data"),
            }
        )

    return {
        "profiles": profiles,
        "milk_analytes_notice": SYNTHETIC_MILK_NOTICE,
        "target_check_notice": TARGET_CHECK_NOTICE,
    }
