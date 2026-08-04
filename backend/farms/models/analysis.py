"""Analítica multiparamétrica y perfiles de destino comercial.

El mismo par muestra/resultado sirve para el forraje y para la leche: `Analyte`
identifica qué se mide y `AnalysisResult` guarda un valor colgado de un análisis
NIR o de una muestra de leche de lote, nunca de ambos.
"""

from django.db import models

from farms.models.agronomy import NIRAnalysis
from farms.models.batch import AnimalBatch


class Analyte(models.Model):
    """Parámetro analítico medible, con su unidad.

    Es un catálogo de identidad, no de criterio: no guarda rangos de referencia
    porque qué valor es deseable depende del destino comercial, y eso vive en
    `TargetRange`.
    """

    code = models.SlugField("código", max_length=40, unique=True)
    name = models.CharField("nombre", max_length=120)
    unit = models.CharField("unidad", max_length=20)

    class Meta:
        verbose_name = "analito"
        verbose_name_plural = "analitos"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.unit})"


class BatchMilkSample(models.Model):
    """Muestra compuesta de leche de un lote.

    El lote es la unidad a la que se asigna la ración, así que muestrear por lote
    deja tratamiento y respuesta en la misma unidad. Convive con el control
    lechero individual, que responde a otra pregunta: qué vaca se desvía del suyo.
    """

    batch = models.ForeignKey(
        AnimalBatch,
        verbose_name="lote",
        on_delete=models.CASCADE,
        related_name="milk_samples",
    )
    date = models.DateField("fecha de la muestra")
    laboratory = models.CharField("laboratorio", max_length=120, blank=True)

    class Meta:
        verbose_name = "muestra de leche del lote"
        verbose_name_plural = "muestras de leche del lote"
        ordering = ["-date", "batch"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "date"],
                name="farms_batchmilksample_unique_batch_date",
            ),
        ]
        indexes = [
            models.Index(fields=["date"], name="farms_batchmilksample_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.batch.name} · muestra {self.date}"


class AnalysisResult(models.Model):
    """Valor de un analito en una muestra, sea de forraje o de leche.

    Cuelga de un análisis NIR o de una muestra de leche, nunca de los dos ni de
    ninguno. Se usan dos claves ajenas excluyentes en vez de una relación
    genérica, por el mismo motivo que en los ingredientes de la ración: así la
    integridad la sostiene la base y los JOIN siguen siendo posibles.
    """

    nir_analysis = models.ForeignKey(
        NIRAnalysis,
        verbose_name="análisis NIR",
        on_delete=models.CASCADE,
        related_name="results",
        null=True,
        blank=True,
    )
    milk_sample = models.ForeignKey(
        BatchMilkSample,
        verbose_name="muestra de leche",
        on_delete=models.CASCADE,
        related_name="results",
        null=True,
        blank=True,
    )
    analyte = models.ForeignKey(
        Analyte,
        verbose_name="analito",
        on_delete=models.PROTECT,
        related_name="results",
    )
    value = models.DecimalField("valor", max_digits=12, decimal_places=4)

    class Meta:
        verbose_name = "resultado analítico"
        verbose_name_plural = "resultados analíticos"
        ordering = ["analyte"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(nir_analysis__isnull=True, milk_sample__isnull=False)
                | models.Q(nir_analysis__isnull=False, milk_sample__isnull=True),
                name="farms_analysisresult_exactly_one_sample",
            ),
            models.UniqueConstraint(
                fields=["nir_analysis", "analyte"],
                name="farms_analysisresult_unique_nir_analyte",
            ),
            models.UniqueConstraint(
                fields=["milk_sample", "analyte"],
                name="farms_analysisresult_unique_sample_analyte",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.analyte.name}: {self.value} {self.analyte.unit}"


class TargetProfile(models.Model):
    """Perfil de destino comercial: qué leche pide un comprador concreto.

    Es catálogo global, no de una explotación: lo que quiere un quesero es un
    hecho de mercado, y cada ganadería o lote lo cumple o no lo cumple.
    """

    code = models.SlugField("código", max_length=40, unique=True)
    name = models.CharField("nombre", max_length=120)
    description = models.TextField("descripción", blank=True)

    class Meta:
        verbose_name = "perfil de destino"
        verbose_name_plural = "perfiles de destino"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class TargetRange(models.Model):
    """Rango objetivo de un analito dentro de un perfil de destino.

    Los extremos son opcionales por separado: un destino puede exigir un mínimo
    de grasa, un máximo de células somáticas, o ambos.
    """

    profile = models.ForeignKey(
        TargetProfile,
        verbose_name="perfil de destino",
        on_delete=models.CASCADE,
        related_name="ranges",
    )
    analyte = models.ForeignKey(
        Analyte,
        verbose_name="analito",
        on_delete=models.PROTECT,
        related_name="target_ranges",
    )
    min_value = models.DecimalField(
        "mínimo", max_digits=12, decimal_places=4, null=True, blank=True
    )
    max_value = models.DecimalField(
        "máximo", max_digits=12, decimal_places=4, null=True, blank=True
    )

    class Meta:
        verbose_name = "rango objetivo"
        verbose_name_plural = "rangos objetivo"
        ordering = ["profile", "analyte"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "analyte"],
                name="farms_targetrange_unique_profile_analyte",
            ),
            models.CheckConstraint(
                condition=models.Q(min_value__isnull=False) | models.Q(max_value__isnull=False),
                name="farms_targetrange_at_least_one_bound",
            ),
            models.CheckConstraint(
                condition=models.Q(min_value__isnull=True)
                | models.Q(max_value__isnull=True)
                | models.Q(max_value__gte=models.F("min_value")),
                name="farms_targetrange_max_above_min",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.analyte.name}: {self.min_value or '—'} … {self.max_value or '—'}"
