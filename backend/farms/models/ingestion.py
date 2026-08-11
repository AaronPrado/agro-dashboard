"""Registro de las cargas de datos y traza de procedencia.

Una fila de este proyecto no vale lo mismo si no se sabe de dónde salió. Cada
entrega de una fuente queda registrada como una carga, y cada fila cargada
apunta a la suya; lo que no se pudo interpretar queda igualmente registrado, con
su motivo, en vez de desaparecer en silencio.
"""

from django.db import models


class SourceSystem(models.TextChoices):
    """Sistemas de los que entra dato en la plataforma."""

    MILKING_ROBOT = "milking_robot", "Robot o sala de ordeño"
    MILK_RECORDING = "milk_recording", "Núcleo de control lechero"
    NIR_LAB = "nir_lab", "Laboratorio de análisis NIR"
    MILK_LAB = "milk_lab", "Laboratorio de análisis de leche"
    FIELD_NOTEBOOK = "field_notebook", "Cuaderno de campo"


class IngestionRun(models.Model):
    """Una entrega concreta de una fuente, cargada en un momento concreto."""

    source = models.CharField("fuente", max_length=20, choices=SourceSystem)
    reference = models.CharField("referencia de origen", max_length=200, blank=True)
    ingested_at = models.DateTimeField("fecha de ingesta", auto_now_add=True)
    records_loaded = models.PositiveIntegerField("registros cargados", default=0)
    records_rejected = models.PositiveIntegerField("registros rechazados", default=0)

    class Meta:
        verbose_name = "carga de datos"
        verbose_name_plural = "cargas de datos"
        ordering = ["-ingested_at"]
        indexes = [
            models.Index(fields=["source", "ingested_at"], name="farms_ingestionrun_src_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_source_display()} · {self.ingested_at:%Y-%m-%d %H:%M}"


class IngestionReject(models.Model):
    """Registro que no se pudo interpretar, conservado con su motivo.

    Se guarda el contenido original para que quien tenga que corregir el fichero
    de origen sepa qué corregir: un contador de errores sin las filas es
    inservible.
    """

    run = models.ForeignKey(
        IngestionRun,
        verbose_name="carga",
        on_delete=models.CASCADE,
        related_name="rejects",
    )
    line_number = models.PositiveIntegerField("línea")
    raw = models.TextField("contenido original")
    reason = models.CharField("motivo", max_length=200)

    class Meta:
        verbose_name = "registro rechazado"
        verbose_name_plural = "registros rechazados"
        ordering = ["run", "line_number"]

    def __str__(self) -> str:
        return f"línea {self.line_number}: {self.reason}"


class Sourced(models.Model):
    """Base de todo lo que entra por una fuente: de qué carga vino esta fila.

    El campo admite nulo porque hay filas anteriores a que existiera este
    registro, y porque una carga puede fallar después de haber escrito.
    """

    ingestion_run = models.ForeignKey(
        IngestionRun,
        verbose_name="carga de origen",
        on_delete=models.PROTECT,
        related_name="%(class)ss",
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True
